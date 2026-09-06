#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
近江八幡市公式サイト トップページ掲載の一覧を取得

市サイトのトップページに並ぶ「重要なおしらせ」「お知らせ」「募集情報」
「イベント情報」は、画面表示時にJSONを読み込んで組み立てられている。
HTMLを読むだけでは取得できないため、そのJSONを直接使う。

JSONには公開日時・タイトル・URL・要約が入っているので、
ページを1件ずつ開かなくても正確な情報が得られる(サイトへの負荷も軽い)。
要約が空の記事だけ、ページを開いて補う。
"""

import json
import sys
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from common import (
    fetch_bytes,
    decode_response,
    extract_page_summary,
    load_json,
    merge_new_items,
    normalize_url,
    now_iso,
    parse_pubdate,
    JST,
    KNOWN_LINKS_FILE,
    REQUEST_INTERVAL_SEC,
)

BASE_URL = "https://www.city.omihachiman.lg.jp"
SOURCE_NAME = "近江八幡市公式サイト"

# トップページに掲載される4種類の一覧
CITY_LISTS = [
    {"label": "重要なおしらせ", "url": f"{BASE_URL}/juyo_info/index.update.json"},
    {"label": "お知らせ",       "url": f"{BASE_URL}/news/index.update.json"},
    {"label": "募集情報",       "url": f"{BASE_URL}/bosyu/index.update.json"},
    {"label": "イベント情報",   "url": f"{BASE_URL}/event/index.update.json"},
]

# 1回の実行で要約のために開くページ数の上限
MAX_SUMMARY_FETCH = 40


def process_list(entry, known, seen, session, budget):
    resp = fetch_bytes(entry["url"], session)
    data = json.loads(decode_response(resp))
    time.sleep(REQUEST_INTERVAL_SEC)

    new_items = []
    known_updates = {}
    ts = now_iso()

    for row in data:
        if not isinstance(row, dict) or row.get("is_category_index"):
            continue
        url = normalize_url((row.get("url") or "").strip())
        title = (row.get("page_name") or "").strip()
        if not url or not title:
            continue
        # httpとhttpsの表記ゆれを吸収する
        url = url.replace("http://www.city.omihachiman.lg.jp", BASE_URL)
        if url in known or url in seen:
            continue
        seen.add(url)

        # 公開日時(JSONに入っている正確な日付)
        published = (row.get("publish_datetime") or "").strip()
        try:
            dt = datetime.fromisoformat(published)
            dt = dt if dt.tzinfo else dt.replace(tzinfo=JST)
        except ValueError:
            dt = parse_pubdate(published)

        summary = (row.get("description") or "").strip()
        if not summary and budget["left"] > 0:
            # 要約が空の記事だけページを開いて補う
            try:
                page = fetch_bytes(url, session)
                soup = BeautifulSoup(decode_response(page), "html.parser")
                summary = extract_page_summary(soup)
            except Exception as e:
                print(f"  [要約取得失敗] {url}: {e}")
            budget["left"] -= 1
            time.sleep(REQUEST_INTERVAL_SEC)

        known_updates[url] = {"title": title, "first_seen": ts}
        new_items.append(
            {
                "title": title,
                "link": url,
                "source": SOURCE_NAME,
                "description": summary,
                "pubDate": dt.strftime("%a, %d %b %Y %H:%M:%S %z"),
            }
        )

    return new_items, known_updates


def main():
    known = load_json(KNOWN_LINKS_FILE, {})
    session = requests.Session()

    all_new = []
    all_known_updates = {}
    seen = set()
    budget = {"left": MAX_SUMMARY_FETCH}

    for entry in CITY_LISTS:
        try:
            new_items, known_updates = process_list(entry, known, seen, session, budget)
            all_new.extend(new_items)
            all_known_updates.update(known_updates)
            print(f"[市サイト/{entry['label']}] 新着 {len(new_items)}件")
        except Exception as e:
            print(f"[市サイト/{entry['label']}] 取得失敗: {e}")

    merge_new_items(all_new, all_known_updates)
    print(f"市サイト トップページ一覧 合計: 新着 {len(all_new)}件")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[ERROR] 予期しないエラー: {e}")
        sys.exit(0)
