#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
既存記事のタイトル修復スクリプト(必要な時だけ実行)

タイトル抽出の不具合により、記事名ではなくサイト名(例:「近江八幡市公式観光サイト」)
が保存されてしまった記事を洗い出し、ページを開き直して正しいタイトルに直す。

ワークフローの手動実行で repair_titles にチェックを入れた時だけ動く。
通常運転では実行されない。
"""

import sys
import time

import requests
from bs4 import BeautifulSoup

from common import (
    fetch_bytes,
    decode_response,
    extract_page_title,
    load_json,
    save_json,
    REJECT_TITLES,
    FEED_ITEMS_FILE,
    KNOWN_LINKS_FILE,
    REQUEST_INTERVAL_SEC,
)

# 修復対象とみなすタイトル(サイト名や不明表記)
BAD_TITLES = set(REJECT_TITLES) | {"(タイトル不明)"}

MAX_REPAIR_PER_RUN = 120


def main():
    items = load_json(FEED_ITEMS_FILE, [])
    known = load_json(KNOWN_LINKS_FILE, {})

    targets = [it for it in items if (it.get("title") or "").strip() in BAD_TITLES]
    if not targets:
        print("修復が必要な記事はありませんでした。")
        return

    print(f"修復対象: {len(targets)}件")
    session = requests.Session()
    repaired = 0

    for it in targets[:MAX_REPAIR_PER_RUN]:
        url = it.get("link")
        if not url:
            continue
        try:
            resp = fetch_bytes(url, session)
            html = decode_response(resp)
        except Exception as e:
            print(f"  [SKIP] {url}: {e}")
            continue
        time.sleep(REQUEST_INTERVAL_SEC)

        soup = BeautifulSoup(html, "html.parser")
        new_title = extract_page_title(soup)

        if new_title in BAD_TITLES:
            print(f"  [変化なし] {url}")
            continue

        old_title = it.get("title")
        it["title"] = new_title
        if url in known:
            known[url]["title"] = new_title
        repaired += 1
        print(f"  修復: 「{old_title}」 -> 「{new_title}」")

    save_json(FEED_ITEMS_FILE, items)
    save_json(KNOWN_LINKS_FILE, known, compact=True)
    print(f"{repaired}件のタイトルを修復しました。")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[ERROR] 予期しないエラー: {e}")
        sys.exit(0)
