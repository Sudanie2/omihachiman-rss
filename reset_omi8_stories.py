#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
観光サイト(omi8.com)記事のリセット(1回限りの手動実行用)

特集・モデルコース・スポット・イベントの記事は日付の記載が無く、
新着順一覧ページ(index_1_0____0___.html)を導入する前は
アルファベット順・同時刻で登録されており、公開順とかけ離れていた。

このスクリプトは、omi8.com配下の既存記事を rss_items.json と
known_links.json の両方から削除する。削除後の次回実行で、
watch_hub_sources.py が新着順一覧から正しい順序で登録し直す。

実行は1回きりでよい(既存の並び順の問題を解消した後は不要)。
"""

import sys
from urllib.parse import urlparse

from common import (
    load_json,
    save_json,
    FEED_ITEMS_FILE,
    KNOWN_LINKS_FILE,
)

TARGET_HOST = "www.omi8.com"


def main():
    items = load_json(FEED_ITEMS_FILE, [])
    before_items = len(items)
    items = [it for it in items if urlparse(it.get("link", "")).netloc != TARGET_HOST]
    removed_items = before_items - len(items)

    known = load_json(KNOWN_LINKS_FILE, {})
    before_known = len(known)
    known = {k: v for k, v in known.items() if urlparse(k).netloc != TARGET_HOST}
    removed_known = before_known - len(known)

    save_json(FEED_ITEMS_FILE, items)
    save_json(KNOWN_LINKS_FILE, known, compact=True)

    print(f"rss_items.json: {removed_items}件を削除しました。")
    print(f"known_links.json: {removed_known}件を削除しました。")
    print("次回のワークフロー実行時に、新着順一覧から取り直されます。")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[ERROR] 予期しないエラー: {e}")
        sys.exit(1)
