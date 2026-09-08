#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
食べログ「近江八幡市のニューオープンのお店」の取得

地域の新規開店情報として、店名・URL・オープン日のみを収集する。

配慮している点:
  - robots.txtで許可された範囲のみ取得する(1回の実行で一覧1ページのみ)
  - 点数・口コミ・写真は取得しない(サイト側の資産であり「無断転載禁止」のため)
  - オープン日が読み取れない店舗は掲載しない(新着かどうか判断できないため)
"""

import re
import sys
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from common import (
    fetch_bytes,
    decode_response,
    get_robot_parser,
    load_json,
    merge_new_items,
    normalize_url,
    now_iso,
    JST,
    KNOWN_LINKS_FILE,
    USER_AGENT,
)

BASE_URL = "https://tabelog.com"
PAGE_URL = f"{BASE_URL}/shiga/C25204/rstLst/cond16-00-00/"
SOURCE_NAME = "食べログ(新規オープン)"

# 「2026年9月8日オープン」から日付を取り出す
OPEN_DATE_PATTERN = re.compile(r"(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日")


def main():
    rp = get_robot_parser(BASE_URL)
    if not rp.can_fetch(USER_AGENT, PAGE_URL):
        print(f"[{SOURCE_NAME}] robots.txtでブロックされているため中止します。")
        return

    resp = fetch_bytes(PAGE_URL)
    soup = BeautifulSoup(decode_response(resp), "html.parser")

    known = load_json(KNOWN_LINKS_FILE, {})
    ts = now_iso()

    new_items = []
    known_updates = {}
    found = 0
    skipped_no_date = 0

    # 店舗ごとの区画を取り出す
    for card in soup.select("div.list-rst"):
        url = (card.get("data-detail-url") or "").strip()
        if not url:
            link = card.select_one("a.list-rst__rst-name-target")
            url = link.get("href", "").strip() if link else ""
        if not url:
            continue
        url = normalize_url(url)

        name_el = card.select_one("a.list-rst__rst-name-target") or card.select_one("h3")
        name = name_el.get_text(" ", strip=True) if name_el else ""
        if not name:
            continue

        found += 1

        open_el = card.select_one(".list-rst__newopen")
        m = OPEN_DATE_PATTERN.search(open_el.get_text(" ", strip=True)) if open_el else None
        if not m:
            # オープン日が読めない店舗は「新着」と判断できないため掲載しない
            skipped_no_date += 1
            continue
        try:
            open_dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=JST)
        except ValueError:
            skipped_no_date += 1
            continue

        if url in known or url in known_updates:
            continue

        # 所在地とジャンル(事実情報のみ)
        genre_el = card.select_one(".list-rst__area-genre")
        genre = re.sub(r"\s+", " ", genre_el.get_text(" ", strip=True)) if genre_el else ""

        title = f"【新規オープン】{name}"
        description = f"{open_dt.strftime('%Y年%-m月%-d日')}オープン" + (f"／{genre}" if genre else "")

        known_updates[url] = {"title": title, "first_seen": ts}
        new_items.append(
            {
                "title": title,
                "link": url,
                "source": SOURCE_NAME,
                "description": description,
                "pubDate": open_dt.strftime("%a, %d %b %Y %H:%M:%S %z"),
            }
        )

    if found == 0:
        print(f"[{SOURCE_NAME}] 店舗情報が見つかりません。ページ構造が変わった可能性があります。")
    if skipped_no_date:
        print(f"[{SOURCE_NAME}] オープン日が読めない店舗 {skipped_no_date}件は掲載対象外としました。")

    merge_new_items(new_items, known_updates)
    print(f"[{SOURCE_NAME}] 掲載中の店舗 {found}件 / 新着 {len(new_items)}件")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[ERROR] 予期しないエラー: {e}")
        sys.exit(0)
