#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
既存記事のタイトル・日付・要約の修復スクリプト(必要な時だけ実行)

ページを開き直して、以下を修正・補完する。
  - サイト名などが記事名として保存されてしまったタイトル
  - 取得日が入っている日付を、ページに書かれた本来の更新日・公開日に置き換え
  - 未設定の要約(記事内容の100〜150字程度の紹介文)

対象は、ページを直接解析して集めたサイト(市公式サイト・観光サイト・図書館)のみ。
RSSから取得したサイトは配信元の日付をそのまま使っているため対象外。

ワークフローの手動実行で repair_titles にチェックを入れた時だけ動く。
"""

import sys
import time
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from common import (
    fetch_bytes,
    decode_response,
    extract_page_date,
    extract_page_summary,
    extract_page_title,
    load_json,
    save_json,
    REJECT_TITLES,
    FEED_ITEMS_FILE,
    KNOWN_LINKS_FILE,
    REQUEST_INTERVAL_SEC,
)

# ページを解析して収集しているサイト(ここだけが修復対象)
TARGET_HOSTS = {
    "www.city.omihachiman.lg.jp",
    "www.omi8.com",
    "library.city.omihachiman.shiga.jp",
}

# 修復対象とみなすタイトル(サイト名や不明表記)
BAD_TITLES = set(REJECT_TITLES) | {"(タイトル不明)"}

MAX_REPAIR_PER_RUN = 200


def main():
    items = load_json(FEED_ITEMS_FILE, [])
    known = load_json(KNOWN_LINKS_FILE, {})

    targets = [
        it for it in items
        if urlparse(it.get("link", "")).netloc in TARGET_HOSTS
    ]
    if not targets:
        print("修復対象の記事はありませんでした。")
        return

    print(f"確認対象: {len(targets)}件(上限{MAX_REPAIR_PER_RUN}件)")
    session = requests.Session()
    fixed_title = 0
    fixed_date = 0
    fixed_summary = 0

    for it in targets[:MAX_REPAIR_PER_RUN]:
        url = it.get("link")
        try:
            resp = fetch_bytes(url, session)
            html = decode_response(resp)
        except Exception as e:
            print(f"  [SKIP] {url}: {e}")
            continue
        time.sleep(REQUEST_INTERVAL_SEC)

        soup = BeautifulSoup(html, "html.parser")

        # タイトルの修復
        if (it.get("title") or "").strip() in BAD_TITLES:
            new_title = extract_page_title(soup)
            if new_title not in BAD_TITLES:
                print(f"  タイトル修復: 「{it.get('title')}」 -> 「{new_title}」")
                it["title"] = new_title
                if url in known:
                    known[url]["title"] = new_title
                fixed_title += 1

        # 日付の修復(ページに書かれた更新日を優先)
        page_date = extract_page_date(soup)
        if page_date:
            new_pub = page_date.strftime("%a, %d %b %Y %H:%M:%S %z")
            try:
                same = parsedate_to_datetime(it.get("pubDate", "")).date() == page_date.date()
            except Exception:
                same = False
            if not same:
                print(f"  日付修復: {page_date.strftime('%Y-%m-%d')}  {it.get('title', '')[:30]}")
                it["pubDate"] = new_pub
                fixed_date += 1

        # 要約の補完
        if not (it.get("description") or "").strip():
            summary = extract_page_summary(soup)
            if summary:
                it["description"] = summary
                fixed_summary += 1

    save_json(FEED_ITEMS_FILE, items)
    save_json(KNOWN_LINKS_FILE, known, compact=True)
    print(f"タイトル {fixed_title}件 / 日付 {fixed_date}件 / 要約 {fixed_summary}件 を修復しました。")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[ERROR] 予期しないエラー: {e}")
        sys.exit(0)
