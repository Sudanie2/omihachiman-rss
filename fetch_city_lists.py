#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
近江八幡市公式サイト トップページ掲載の一覧を取得

市サイトのトップページに並ぶ「重要なおしらせ」「お知らせ」「募集情報」
「イベント情報」は、画面表示時にJSONを読み込んで組み立てられている。
そのJSONを直接使う(公開日時・タイトル・URL・要約が入っている)。

重要: 市サイトは同じURLのページを更新して再掲載する運用がある
(例:「【9月分】コンビニ交付サービスの一時停止」を毎月同じページで更新)。
そのため、URLが既知でも公開日時が前回より新しければ「再掲載」として扱い、
改めて新着に載せる。この場合、RSSリーダーにも新着として届くよう、
記事の識別子(guid)に公開日を付けて区別する。
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
    save_json,
    FEED_ITEMS_FILE,
    JST,
    KNOWN_LINKS_FILE,
    REQUEST_INTERVAL_SEC,
)

BASE_URL = "https://www.city.omihachiman.lg.jp"
SOURCE_NAME = "近江八幡市公式サイト"

CITY_LISTS = [
    {"label": "重要なおしらせ", "url": f"{BASE_URL}/juyo_info/index.update.json"},
    {"label": "お知らせ",       "url": f"{BASE_URL}/news/index.update.json"},
    {"label": "募集情報",       "url": f"{BASE_URL}/bosyu/index.update.json"},
    {"label": "イベント情報",   "url": f"{BASE_URL}/event/index.update.json"},
]

MAX_SUMMARY_FETCH = 40


def parse_publish(text):
    try:
        dt = datetime.fromisoformat((text or "").strip())
        return dt if dt.tzinfo else dt.replace(tzinfo=JST)
    except ValueError:
        return None


def process_list(entry, known, current_links, seen, session, budget):
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
        url = url.replace("http://www.city.omihachiman.lg.jp", BASE_URL)
        if url in seen:
            continue

        pub_dt = parse_publish(row.get("publish_datetime"))
        pub_iso = pub_dt.isoformat() if pub_dt else ""

        # --- 新着・再掲載の判定 ---
        record = known.get(url) or known_updates.get(url)
        if record is None:
            reason = "新着"           # 初めて見るURL
        else:
            recorded_pub = record.get("pub", "")
            if pub_iso and recorded_pub and pub_iso > recorded_pub:
                reason = "再掲載"     # 同じURLだが公開日時が更新された
            elif not recorded_pub and url not in current_links:
                reason = "復元"       # 過去の不具合等で一覧から消えている
            else:
                continue              # 変化なし

        seen.add(url)

        if pub_dt is None:
            pub_dt = datetime.now(JST)

        summary = (row.get("description") or "").strip()
        if not summary and budget["left"] > 0:
            try:
                page = fetch_bytes(url, session)
                soup = BeautifulSoup(decode_response(page), "html.parser")
                summary = extract_page_summary(soup)
            except Exception as e:
                print(f"  [要約取得失敗] {url}: {e}")
            budget["left"] -= 1
            time.sleep(REQUEST_INTERVAL_SEC)

        item = {
            "title": title,
            "link": url,
            "source": SOURCE_NAME,
            "description": summary,
            "pubDate": pub_dt.strftime("%a, %d %b %Y %H:%M:%S %z"),
        }
        # 再掲載はRSSリーダー側でも新着として届くよう、識別子に公開日を付ける
        if reason == "再掲載":
            item["guid"] = f"{url}#{pub_dt.strftime('%Y%m%d')}"

        known_updates[url] = {"title": title, "first_seen": ts, "pub": pub_iso}
        new_items.append(item)
        if reason != "新着":
            print(f"  [{reason}] {title[:40]}")

    return new_items, known_updates


def drop_older_duplicates(new_items):
    """再掲載により、同じURLの古い掲載が残っている場合は取り除く"""
    items = load_json(FEED_ITEMS_FILE, [])
    new_links = {it["link"] for it in new_items}
    if not new_links:
        return
    kept = [it for it in items if it.get("link") not in new_links]
    if len(kept) != len(items):
        save_json(FEED_ITEMS_FILE, kept)


def main():
    known = load_json(KNOWN_LINKS_FILE, {})
    current_links = {it.get("link") for it in load_json(FEED_ITEMS_FILE, [])}
    session = requests.Session()

    all_new = []
    all_known_updates = {}
    seen = set()
    budget = {"left": MAX_SUMMARY_FETCH}

    for entry in CITY_LISTS:
        try:
            new_items, known_updates = process_list(
                entry, known, current_links, seen, session, budget
            )
            all_new.extend(new_items)
            all_known_updates.update(known_updates)
            print(f"[市サイト/{entry['label']}] 新着・再掲載 {len(new_items)}件")
        except Exception as e:
            print(f"[市サイト/{entry['label']}] 取得失敗: {e}")

    drop_older_duplicates(all_new)
    merge_new_items(all_new, all_known_updates)
    print(f"市サイト トップページ一覧 合計: {len(all_new)}件")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[ERROR] 予期しないエラー: {e}")
        sys.exit(0)
