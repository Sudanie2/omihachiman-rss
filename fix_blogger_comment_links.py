#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Blogger(Blogspot)のコメント欄リンク誤登録の修正(1回限りの手動実行用)

fetch_rss_sources.py の以前のバージョンは、Bloggerが配信するAtomフィードで
1記事につき複数の<link>タグがある場合に、最初に見つかったものを機械的に
使っていた。Bloggerは「コメント欄へのリンク」を最初に出力する構成のため、
本来の記事ページではなく、以下のようなコメント欄のURLが誤って登録されていた。

    https://azuchi-museum.blogspot.com/feeds/1910634924120799529/comments/default

このスクリプトは、この形式のURLを rss_items.json と known_links.json から
削除する。削除後の次回実行で、修正済みの取得ロジックが正しい記事ページの
URLで登録し直す。
"""

import re
import sys

from common import (
    load_json,
    save_json,
    FEED_ITEMS_FILE,
    KNOWN_LINKS_FILE,
)

BAD_LINK_PATTERN = re.compile(r"blogspot\.com/feeds/\d+/comments/default")


def main():
    items = load_json(FEED_ITEMS_FILE, [])
    before_items = len(items)
    items = [it for it in items if not BAD_LINK_PATTERN.search(it.get("link", ""))]
    removed_items = before_items - len(items)

    known = load_json(KNOWN_LINKS_FILE, {})
    before_known = len(known)
    known = {k: v for k, v in known.items() if not BAD_LINK_PATTERN.search(k)}
    removed_known = before_known - len(known)

    save_json(FEED_ITEMS_FILE, items)
    save_json(KNOWN_LINKS_FILE, known, compact=True)

    print(f"rss_items.json: {removed_items}件を削除しました。")
    print(f"known_links.json: {removed_known}件を削除しました。")
    print("次回のワークフロー実行時に、正しい記事URLで登録し直されます。")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[ERROR] 予期しないエラー: {e}")
        sys.exit(1)
