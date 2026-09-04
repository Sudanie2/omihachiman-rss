#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
近江八幡市公式観光サイト(omi8.com) 新着監視スクリプト

ご指定の9つのカテゴリ一覧ページ(ハブページ)を毎日巡回し、
新しく出現した詳細記事(detail_数字.html等)のタイトル・URLを検出する。
市サイト向けの watch_hubs_and_generate_rss.py と同じ設計方針。
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

BASE_URL = "https://www.omi8.com"

FIXED_HUBS = [
    f"{BASE_URL}/stories/index.html",
    f"{BASE_URL}/course/index.html",
    f"{BASE_URL}/spot/index.html",
    f"{BASE_URL}/event/index.html",
    f"{BASE_URL}/restaurant/index.html",
    f"{BASE_URL}/souvenir/index.html",
    f"{BASE_URL}/stay/index.html",
    f"{BASE_URL}/access/index.html",
    f"{BASE_URL}/favorite/index.html",
]

# 新着として検出する対象は「詳細記事ページ」のみに絞る
# (detail_123.html / detail.html?xxx=1 のようなパターン)
DETAIL_PATTERN = re.compile(r"/detail[_.]")

USER_AGENT = "OmihachimanRSSBot/1.0 (+personal monitoring; contact: TS/KURA)"
REQUEST_INTERVAL_SEC = 1.0
REQUEST_TIMEOUT_SEC = 15
MAX_NEW_PAGE_FETCH_PER_RUN = 60

KNOWN_LINKS_FILE = Path("known_links.json")
FEED_ITEMS_FILE = Path("rss_items.json")
FEED_FILE = Path("rss.xml")
FEED_MAX_ITEMS = 200

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
    return bool(DETAIL_PATTERN.search(parsed.path + ("?" + parsed.query if parsed.query else "")))


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
    <title>近江八幡市 くらし更新だより(非公式・複数ソース統合)</title>
    <link>https://www.city.omihachiman.lg.jp/index.html</link>
    <description>近江八幡市関連の複数サイトの新着をまとめた非公式RSSです。</description>
    <lastBuildDate>{now}</lastBuildDate>
{chr(10).join(entries_xml)}
  </channel>
</rss>
"""


def main():
    rp = urllib.robotparser.RobotFileParser()
    try:
        robots_resp = requests.get(
            f"{BASE_URL}/robots.txt",
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT_SEC,
        )
        if robots_resp.status_code == 200:
            rp.parse(robots_resp.text.splitlines())
        else:
            print(f"robots.txt取得: status={robots_resp.status_code}。全ページ許可として続行します。")
            rp.parse([])
    except Exception as e:
        print(f"robots.txtの取得に失敗しました({e})。全ページ許可として続行します。")
        rp.parse([])

    known_links = load_json(KNOWN_LINKS_FILE, {})
    session = requests.Session()

    now_iso = datetime.now(timezone.utc).isoformat()
    now_rfc822 = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S %z")

    candidate_new_links = set()

    for hub_url in FIXED_HUBS:
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
                "description": f"新着記事を検出しました: {url}",
                "pubDate": now_rfc822,
            }
        )

    existing_items = load_json(FEED_ITEMS_FILE, [])
    combined = new_items + existing_items
    combined = combined[:FEED_MAX_ITEMS]

    save_json(FEED_ITEMS_FILE, combined)
    save_json(KNOWN_LINKS_FILE, known_links)
    FEED_FILE.write_text(build_rss(combined), encoding="utf-8")

    print(f"omi8.com: ハブページ巡回 {len(FIXED_HUBS)}件 / 新着検出 {len(new_items)}件")


if __name__ == "__main__":
    main()
