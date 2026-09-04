#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
近江八幡警察署の活動(滋賀県警サイト) 取得スクリプト

1枚のページに日付付きの短い記事が追記されていく形式のため、
「○月○日(◯曜日)」の出現位置を区切りとして記事を切り出す。
年は「上から下へ月の数字が大きくなったら前年」という前提で推定する。
"""

import re
import sys
from datetime import datetime

from bs4 import BeautifulSoup

from common import (
    fetch_bytes,
    decode_response,
    get_robot_parser,
    load_json,
    merge_new_items,
    now_iso,
    JST,
    KNOWN_LINKS_FILE,
    USER_AGENT,
)

PAGE_URL = "https://www.pref.shiga.lg.jp/police/sikumi/profile/303371/318537.html"
BASE_URL = "https://www.pref.shiga.lg.jp"
SOURCE_NAME = "近江八幡警察署(滋賀県警)"

SECTION_START_MARKER = "新着一覧"
SECTION_END_MARKER = "お問い合わせ"
DATE_PATTERN = re.compile(r"(\d{1,2})月(\d{1,2})日(?:\s*[（(][^）)]{1,4}曜日[）)])?")


def clean_text(text: str) -> str:
    text = text.replace("byけいたくん", "").replace("by けいたくん", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def main():
    rp = get_robot_parser(BASE_URL)
    if not rp.can_fetch(USER_AGENT, PAGE_URL):
        print(f"[{SOURCE_NAME}] robots.txtでブロックされているため中止します。")
        return

    resp = fetch_bytes(PAGE_URL)
    html = decode_response(resp)

    soup = BeautifulSoup(html, "html.parser")
    full_text = soup.get_text("\n")

    start_idx = full_text.find(SECTION_START_MARKER)
    end_idx = full_text.find(SECTION_END_MARKER, start_idx if start_idx >= 0 else 0)
    if start_idx == -1 or end_idx == -1:
        print(f"[{SOURCE_NAME}] 記事本文の範囲が見つかりません。ページ構造が変わった可能性があります。")
        return

    content_blob = full_text[start_idx + len(SECTION_START_MARKER):end_idx]
    content_blob = re.sub(r"\s+", " ", content_blob).strip()

    matches = list(DATE_PATTERN.finditer(content_blob))
    if not matches:
        print(f"[{SOURCE_NAME}] 日付パターンが見つかりません。")
        return

    known = load_json(KNOWN_LINKS_FILE, {})
    ts = now_iso()

    current_year = datetime.now(JST).year
    prev_month = None
    year = current_year

    new_items = []
    known_updates = {}

    for i, m in enumerate(matches):
        month = int(m.group(1))
        day = int(m.group(2))

        if prev_month is not None and month > prev_month:
            year -= 1
        prev_month = month

        key = f"{PAGE_URL}#{year:04d}-{month:02d}-{day:02d}"
        if key in known or key in known_updates:
            continue

        try:
            pub_dt = datetime(year, month, day, tzinfo=JST)
        except ValueError:
            continue

        seg_start = m.start()
        seg_end = matches[i + 1].start() if i + 1 < len(matches) else len(content_blob)
        entry_text = clean_text(content_blob[seg_start:seg_end])

        title = f"近江八幡警察署の活動（{month}月{day}日）"
        known_updates[key] = {"title": title, "first_seen": ts}
        new_items.append(
            {
                "title": title,
                "link": PAGE_URL,
                "guid": key,
                "source": SOURCE_NAME,
                "description": entry_text[:300],
                "pubDate": pub_dt.strftime("%a, %d %b %Y %H:%M:%S %z"),
            }
        )

    merge_new_items(new_items, known_updates)
    print(f"[{SOURCE_NAME}] 記事区切り {len(matches)}件 / 新着 {len(new_items)}件")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[ERROR] 予期しないエラー: {e}")
        sys.exit(0)
