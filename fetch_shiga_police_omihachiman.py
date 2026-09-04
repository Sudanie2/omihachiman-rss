#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
近江八幡警察署の活動(滋賀県警サイト)を取得するスクリプト

このページは「1枚のページの中に、日付を先頭にした短い記事が
上から新しい順に次々と追記されていく」形式で、個別記事URLが存在しない。
そのため、本文中の「○月○日（◯曜日）」という日付表記の出現位置を区切りとして、
その間のテキストを1件の記事として扱う。

年は明記されていないため、上(新しい)から下(古い)に向かって月の数字が
前の記事より大きくなった時点で年を1つ遡る、という前提で推定する。
(要確認: 記事が1年以上前まで遡って掲載されている場合、この推定がずれる可能性がある)
"""

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

PAGE_URL = "https://www.pref.shiga.lg.jp/police/sikumi/profile/303371/318537.html"
USER_AGENT = "OmihachimanRSSBot/1.0 (+personal monitoring; contact: TS/KURA)"
REQUEST_TIMEOUT_SEC = 15
JST = timezone(timedelta(hours=9))

# 記事本文の範囲を示す見出しテキスト(この間だけを対象にする)
SECTION_START_MARKER = "新着一覧"
SECTION_END_MARKER = "お問い合わせ"

# 「6月19日」「6月19日（金曜日）」のようなパターンにマッチ
DATE_PATTERN = re.compile(r"(\d{1,2})月(\d{1,2})日(?:\s*[（(][^）)]{1,4}曜日[）)])?")

KNOWN_LINKS_FILE = Path("known_links.json")
FEED_ITEMS_FILE = Path("rss_items.json")
FEED_FILE = Path("rss.xml")
FEED_MAX_ITEMS = 200


def load_json(path: Path, default):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def clean_text(text: str) -> str:
    text = text.replace("byけいたくん", "").replace("by けいたくん", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


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
      <guid isPermaLink="false">{esc(it['guid'])}</guid>
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
    headers = {"User-Agent": USER_AGENT}

    # robots.txt確認(取得できなければ許可扱いで続行)
    import urllib.robotparser
    rp = urllib.robotparser.RobotFileParser()
    try:
        robots_resp = requests.get(
            "https://www.pref.shiga.lg.jp/robots.txt", headers=headers, timeout=REQUEST_TIMEOUT_SEC
        )
        if robots_resp.status_code == 200:
            rp.parse(robots_resp.text.splitlines())
        else:
            rp.parse([])
    except Exception:
        rp.parse([])

    if not rp.can_fetch(USER_AGENT, PAGE_URL):
        print("robots.txtでブロックされているため中止します。")
        return

    resp = requests.get(PAGE_URL, headers=headers, timeout=REQUEST_TIMEOUT_SEC)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding

    soup = BeautifulSoup(resp.text, "html.parser")
    full_text = soup.get_text("\n")

    start_idx = full_text.find(SECTION_START_MARKER)
    end_idx = full_text.find(SECTION_END_MARKER, start_idx if start_idx >= 0 else 0)
    if start_idx == -1 or end_idx == -1:
        print("記事本文の範囲(新着一覧〜お問い合わせ)が見つかりませんでした。ページ構造が変わった可能性があります。")
        return

    content_blob = full_text[start_idx + len(SECTION_START_MARKER):end_idx]
    content_blob = re.sub(r"\s+", " ", content_blob).strip()

    matches = list(DATE_PATTERN.finditer(content_blob))
    if not matches:
        print("日付パターンが見つかりませんでした。")
        return

    known_links = load_json(KNOWN_LINKS_FILE, {})
    now_iso = datetime.now(timezone.utc).isoformat()

    current_year = datetime.now(JST).year
    prev_month = None
    year = current_year

    parsed_entries = []
    for i, m in enumerate(matches):
        month = int(m.group(1))
        day = int(m.group(2))

        if prev_month is not None and month > prev_month:
            year -= 1
        prev_month = month

        seg_start = m.start()
        seg_end = matches[i + 1].start() if i + 1 < len(matches) else len(content_blob)
        entry_text = clean_text(content_blob[seg_start:seg_end])

        parsed_entries.append((year, month, day, entry_text))

    new_items = []
    for year, month, day, entry_text in parsed_entries:
        key = f"{PAGE_URL}#{year:04d}-{month:02d}-{day:02d}"
        if key in known_links:
            continue

        try:
            pub_dt = datetime(year, month, day, tzinfo=JST)
        except ValueError:
            continue
        pub_rfc822 = pub_dt.strftime("%a, %d %b %Y %H:%M:%S %z")

        title = f"近江八幡警察署の活動（{month}月{day}日）"
        known_links[key] = {"title": title, "first_seen": now_iso}
        new_items.append(
            {
                "title": title,
                "link": PAGE_URL,
                "guid": key,
                "description": entry_text[:300],
                "pubDate": pub_rfc822,
            }
        )

    existing_items = load_json(FEED_ITEMS_FILE, [])
    combined = new_items + existing_items
    combined = combined[:FEED_MAX_ITEMS]

    save_json(FEED_ITEMS_FILE, combined)
    save_json(KNOWN_LINKS_FILE, known_links)
    FEED_FILE.write_text(build_rss(combined), encoding="utf-8")

    print(f"近江八幡警察署の活動: 検出した記事区切り {len(parsed_entries)}件 / 新着 {len(new_items)}件")


if __name__ == "__main__":
    main()
