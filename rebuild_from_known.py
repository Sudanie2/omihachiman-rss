#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
既知記事の再収集(必要な時だけ実行)

過去に「収集済み」として記録されたものの、掲載枠の上限などで
公開ページから消えてしまった記事を、既知リスト(known_links.json)から
掲載対象期間内のものだけ選んで復元する。

known_links.json には収集日とタイトルしか残っていないため、
正確な日付・要約を得るにはページを開き直す必要がある。
そのため1回の実行で扱う件数に上限を設け、複数回に分けて処理する。

ワークフローの手動実行で rebuild_items にチェックを入れた時だけ動く。
"""

import sys
import time
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
    source_from_url,
    FEED_ITEMS_FILE,
    FEED_MIN_DATE,
    KNOWN_LINKS_FILE,
    REQUEST_INTERVAL_SEC,
    REJECT_TITLES,
)

MAX_PER_RUN = 250

# 日付の記載が無いサイトは、ページを開いても日付が得られないため、
# 既知リストの記録日(収集日)を使う。
NO_DATE_HOSTS = {
    "www.omi8.com",
    "www.zd.ztv.ne.jp",
    "azuchi-shiga.com",
}

BAD_TITLES = set(REJECT_TITLES) | {"(タイトル不明)"}


def main():
    known = load_json(KNOWN_LINKS_FILE, {})
    items = load_json(FEED_ITEMS_FILE, [])
    present = {it.get("link") for it in items}

    # 既知だが掲載されていないURL
    missing = [url for url in known if url not in present and url.startswith("http")]
    if not missing:
        print("復元が必要な記事はありません。")
        return

    print(f"掲載されていない既知記事: {len(missing)}件(今回は最大{MAX_PER_RUN}件を処理)")
    session = requests.Session()
    restored = 0
    skipped_old = 0
    skipped_nodate = 0

    for url in missing[:MAX_PER_RUN]:
        record = known.get(url) or {}
        if record.get("no_date"):
            skipped_nodate += 1
            continue

        try:
            resp = fetch_bytes(url, session)
            soup = BeautifulSoup(decode_response(resp), "html.parser")
        except Exception as e:
            print(f"  [SKIP] {url}: {e}")
            continue
        time.sleep(REQUEST_INTERVAL_SEC)

        host = urlparse(url).netloc
        page_date = extract_page_date(soup)

        if page_date is None:
            if host in NO_DATE_HOSTS:
                # 日付表記の無いサイトは収集日を使う
                from datetime import datetime
                from common import JST
                try:
                    page_date = datetime.fromisoformat(record.get("first_seen", "")).astimezone(JST)
                except Exception:
                    skipped_nodate += 1
                    continue
            else:
                # 市サイト等で更新日が無いページは中継ページなので復元しない
                known[url] = {**record, "no_date": True}
                skipped_nodate += 1
                continue

        if page_date < FEED_MIN_DATE:
            skipped_old += 1
            continue

        title = extract_page_title(soup)
        if title in BAD_TITLES:
            title = record.get("title") or title

        items.insert(0, {
            "title": title,
            "link": url,
            "source": source_from_url(url),
            "description": extract_page_summary(soup),
            "pubDate": page_date.strftime("%a, %d %b %Y %H:%M:%S %z"),
        })
        known[url] = {**record, "title": title}
        restored += 1
        print(f"  復元: [{page_date.strftime('%Y-%m-%d')}] {title[:36]}")

    save_json(FEED_ITEMS_FILE, items)
    save_json(KNOWN_LINKS_FILE, known, compact=True)
    print(
        f"復元 {restored}件 / 期間外のため見送り {skipped_old}件 / "
        f"日付なしのため対象外 {skipped_nodate}件"
    )
    remaining = len(missing) - MAX_PER_RUN
    if remaining > 0:
        print(f"未処理が{remaining}件あります。もう一度この処理を実行してください。")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[ERROR] 予期しないエラー: {e}")
        sys.exit(0)
