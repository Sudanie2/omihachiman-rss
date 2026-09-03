#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
近江八幡市サイト 軽量版・新着検知RSSジェネレーター

discover_hubs.py で作成した hubs.json(部署トップページ + 主要一覧ページ、
おおむね100ページ未満)だけを毎日巡回し、そこに新しく出現したリンクを
「新着ページ」としてRSS化します。

全ページのハッシュ比較は行わないため、負荷は非常に軽くなりますが、
部署トップページに直接リンクされていない深い階層の更新は拾えません
(要確認: どの程度の割合を拾えているかは運用しながら確認してください)。

処理の流れ:
  1. hubs.json のページを1つずつ取得(リクエスト間隔を空ける)
  2. 各ハブページ内のリンクを抽出
  3. known_links.json(既知リンク一覧)にないリンク = 新着
  4. 新着リンクは1回だけ取得してタイトルを取得し、RSSエントリ化
  5. known_links.json / rss.xml / rss_items.json を更新
"""

import json
import re
import time
import urllib.robotparser
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.city.omihachiman.lg.jp"

USER_AGENT = "OmihachimanRSSBot/1.0 (+personal monitoring; contact: TS/KURA)"
REQUEST_INTERVAL_SEC = 1.0
REQUEST_TIMEOUT_SEC = 15

# 新着として検出したページのうち、実際にタイトル取得のため
# 追加でアクセスしてよい件数の上限(1回の実行あたり)。
# 突発的に大量の新着が出た場合の負荷対策。
MAX_NEW_PAGE_FETCH_PER_RUN = 80

HUBS_FILE = Path("hubs.json")
KNOWN_LINKS_FILE = Path("known_links.json")
FEED_ITEMS_FILE = Path("rss_items.json")
FEED_FILE = Path("rss.xml")
FEED_MAX_ITEMS = 200

EXCLUDE_PATTERNS = [
    r"^/cgi-bin/",
    r"\.(pdf|jpg|jpeg|png|gif|zip|docx?|xlsx?|pptx?)$",
]

TITLE_SELECTORS = ["h1", "title"]


def load_json(path: Path, default):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def normalize_url(url: str) -> str:
    return url.split("#")[0]


def is_target_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.netloc and parsed.netloc != urlparse(BASE_URL).netloc:
        return False
    path = parsed.path or "/"
    for pattern in EXCLUDE_PATTERNS:
        if re.search(pattern, path):
            return False
    if "." in path.rsplit("/", 1)[-1] and not path.endswith((".html", ".htm")):
        return False
    return True


def fetch(url: str, session: requests.Session) -> str:
    headers = {"User-Agent": USER_AGENT}
    resp = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SEC)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding
    return resp.text


def extract_title(soup: BeautifulSoup) -> str:
    for sel in TITLE_SELECTORS:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            return el.get_text(strip=True)
    return "(タイトル不明)"


def extract_links(soup: BeautifulSoup, base_url: str):
    links = []
    for a in soup.find_all("a", href=True):
        abs_url = normalize_url(urljoin(base_url, a["href"]))
        if is_target_url(abs_url):
            links.append(abs_url)
    return links


def build_rss(items):
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S %z")

    def esc(s: str) -> str:
        return (
            s.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    entries_xml = []
    for it in items[:FEED_MAX_ITEMS]:
        entries_xml.append(
            f"""    <item>
      <title>{esc(it['title'])}</title>
      <link>{esc(it['link'])}</link>
      <guid isPermaLink="true">{esc(it['link'])}</guid>
      <pubDate>{it['pubDate']}</pubDate>
      <description>{esc(it['description'])}</description>
    </item>"""
        )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>近江八幡市公式サイト 新着ページ(非公式・ハブ監視方式)</title>
    <link>{BASE_URL}/index.html</link>
    <description>各課トップページ等のハブページを監視し、新しく出現したリンクを検出した非公式RSSです。</description>
    <lastBuildDate>{now}</lastBuildDate>
{chr(10).join(entries_xml)}
  </channel>
</rss>
"""


def main():
    hubs = load_json(HUBS_FILE, None)
    if hubs is None:
        print("hubs.json が見つかりません。先に discover_hubs.py を実行してください。")
        return

    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(f"{BASE_URL}/robots.txt")
    try:
        rp.read()
    except Exception:
        print("robots.txtの取得に失敗しました。安全のため今回は実行を中止します。")
        return

    known_links = load_json(KNOWN_LINKS_FILE, {})  # {url: {"title":..., "first_seen":...}}
    session = requests.Session()

    now_iso = datetime.now(timezone.utc).isoformat()
    now_rfc822 = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S %z")

    candidate_new_links = set()

    # 1. ハブページを巡回し、リンクを収集
    for hub_url in hubs:
        if not rp.can_fetch(USER_AGENT, hub_url):
            print(f"[robots.txtでブロック] {hub_url}")
            continue
        try:
            html = fetch(hub_url, session)
        except Exception as e:
            print(f"[SKIP] {hub_url}: {e}")
            continue
        time.sleep(REQUEST_INTERVAL_SEC)

        soup = BeautifulSoup(html, "html.parser")
        for link in extract_links(soup, hub_url):
            if link not in known_links:
                candidate_new_links.add(link)

    # 2. 新着リンクの中身を取得してタイトルを確認(上限あり)
    new_items = []
    for i, url in enumerate(sorted(candidate_new_links)):
        if i >= MAX_NEW_PAGE_FETCH_PER_RUN:
            print(f"上限({MAX_NEW_PAGE_FETCH_PER_RUN}件)に達したため、残りは次回に持ち越します。")
            break
        if not rp.can_fetch(USER_AGENT, url):
            continue
        try:
            html = fetch(url, session)
        except Exception as e:
            print(f"[SKIP] {url}: {e}")
            continue
        time.sleep(REQUEST_INTERVAL_SEC)

        soup = BeautifulSoup(html, "html.parser")
        title = extract_title(soup)

        known_links[url] = {"title": title, "first_seen": now_iso}
        new_items.append(
            {
                "title": title,
                "link": url,
                "description": f"新着ページを検出しました: {url}",
                "pubDate": now_rfc822,
            }
        )

    # 3. フィード更新
    existing_items = load_json(FEED_ITEMS_FILE, [])
    combined = new_items + existing_items
    combined = combined[:FEED_MAX_ITEMS]

    save_json(FEED_ITEMS_FILE, combined)
    save_json(KNOWN_LINKS_FILE, known_links)
    FEED_FILE.write_text(build_rss(combined), encoding="utf-8")

    print(f"ハブページ巡回: {len(hubs)}件 / 新着検出: {len(new_items)}件")


if __name__ == "__main__":
    main()
