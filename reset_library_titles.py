#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
図書館だより記事のタイトル修復(1回限りの手動実行用)

図書館の記事詳細ページは本文をJavaScriptで後から読み込む作りのため、
タイトルを一覧ページのリンク文字列から取る方式に変更した(watch_hub_sources.py)。
この変更は「新しく見つかった記事」にしか効かないため、既に「既知」として
登録済みの記事(タイトルが「図書館だより」等の汎用名のままのもの)は
このスクリプトで一度取り除き、次回実行時に正しいタイトルで登録し直す。
"""

import sys

from common import (
    load_json,
    save_json,
    REJECT_TITLES,
    FEED_ITEMS_FILE,
    KNOWN_LINKS_FILE,
)

TARGET_HOST = "library.city.omihachiman.shiga.jp"
BAD_TITLES = set(REJECT_TITLES) | {"(タイトル不明)"}


def main():
    items = load_json(FEED_ITEMS_FILE, [])
    before_items = len(items)
    items = [
        it for it in items
        if not (TARGET_HOST in it.get("link", "") and (it.get("title") or "").strip() in BAD_TITLES)
    ]
    removed_items = before_items - len(items)

    known = load_json(KNOWN_LINKS_FILE, {})
    before_known = len(known)
    known = {
        k: v for k, v in known.items()
        if not (TARGET_HOST in k and (v.get("title") or "").strip() in BAD_TITLES)
    }
    removed_known = before_known - len(known)

    save_json(FEED_ITEMS_FILE, items)
    save_json(KNOWN_LINKS_FILE, known, compact=True)

    print(f"rss_items.json: {removed_items}件を削除しました。")
    print(f"known_links.json: {removed_known}件を削除しました。")
    print("次回のワークフロー実行時に、一覧ページのリンク文字を使った正しいタイトルで登録し直されます。")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[ERROR] 予期しないエラー: {e}")
        sys.exit(1)
