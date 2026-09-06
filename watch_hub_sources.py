#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ハブページ監視型の新着取得(統合版)

一覧ページ(ハブページ)を巡回し、新しく出現したリンクを新着記事として検出する。

対象:
  - 近江八幡市観光サイト(omi8.com): 9カテゴリの一覧ページ
  - 近江八幡市立図書館: トップページと図書館だより一覧

1つのサイトで取得に失敗しても、他のサイトの処理は続行する。
"""

import re
import sys
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from common import (
    fetch_bytes,
    decode_response,
    get_robot_parser,
    load_json,
    merge_new_items,
    extract_page_date,
    extract_page_title,
    normalize_url,
    now_iso,
    now_rfc822,
    KNOWN_LINKS_FILE,
    REQUEST_INTERVAL_SEC,
    USER_AGENT,
)

HUB_SOURCES = [
    {
        "name": "近江八幡市観光サイト",
        "base": "https://www.omi8.com",
        "hubs": [
            "/stories/index.html",
            "/course/index.html",
            "/spot/index.html",
            "/event/index.html",
            "/restaurant/index.html",
            "/souvenir/index.html",
            "/stay/index.html",
            "/access/index.html",
            "/favorite/index.html",
        ],
        # 個別記事とみなすURLパターン
        "detail_pattern": r"/detail[_.]",
    },
    {
        "name": "近江八幡市立図書館",
        "base": "https://library.city.omihachiman.shiga.jp",
        "hubs": [
            "/",
            "/図書館だより・行事案内/図書館だより",
        ],
        "detail_pattern": r"active_action=bbs_view_main_post.*post_id=\d+",
    },
]

MAX_NEW_PAGE_FETCH_PER_SOURCE = 60


def is_target_url(url: str, base: str, pattern: re.Pattern) -> bool:
    parsed = urlparse(url)
    if parsed.netloc and parsed.netloc != urlparse(base).netloc:
        return False
    full = parsed.path + ("?" + parsed.query if parsed.query else "")
    return bool(pattern.search(full))


def process_source(source, known, session):
    """1つのハブ監視ソースを処理し、新着itemsと既知キー更新を返す"""
    base = source["base"]
    pattern = re.compile(source["detail_pattern"])
    rp = get_robot_parser(base)

    candidate_new = []
    seen_in_run = set()

    # 1. ハブページを巡回して新出リンクを収集
    for hub_path in source["hubs"]:
        hub_url = base + hub_path if hub_path.startswith("/") else hub_path
        if not rp.can_fetch(USER_AGENT, hub_url):
            print(f"[{source['name']}] robots.txtでブロック: {hub_url}")
            continue
        try:
            resp = fetch_bytes(hub_url, session)
            html = decode_response(resp)
        except Exception as e:
            print(f"[{source['name']}] ハブページ取得失敗 {hub_url}: {e}")
            continue
        time.sleep(REQUEST_INTERVAL_SEC)

        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            abs_url = normalize_url(urljoin(hub_url, a["href"]))
            if not is_target_url(abs_url, base, pattern):
                continue
            if abs_url in known or abs_url in seen_in_run:
                continue
            seen_in_run.add(abs_url)
            candidate_new.append(abs_url)

    # 2. 新出リンクを1回だけ開いてタイトルを取得
    new_items = []
    known_updates = {}
    ts = now_iso()
    ts_rfc822 = now_rfc822()

    for i, url in enumerate(sorted(candidate_new)):
        if i >= MAX_NEW_PAGE_FETCH_PER_SOURCE:
            print(f"[{source['name']}] 上限に達したため残りは次回に持ち越します。")
            break
        if not rp.can_fetch(USER_AGENT, url):
            continue
        try:
            resp = fetch_bytes(url, session)
            html = decode_response(resp)
        except Exception as e:
            print(f"[{source['name']}] 記事取得失敗 {url}: {e}")
            continue
        time.sleep(REQUEST_INTERVAL_SEC)

        soup = BeautifulSoup(html, "html.parser")
        title = extract_page_title(soup)

        # ページに書かれた更新日を優先し、無ければ取得日を使う
        page_date = extract_page_date(soup)
        pub = page_date.strftime("%a, %d %b %Y %H:%M:%S %z") if page_date else ts_rfc822

        known_updates[url] = {"title": title, "first_seen": ts}
        new_items.append(
            {
                "title": title,
                "link": url,
                "source": source["name"],
                "pubDate": pub,
            }
        )

    return new_items, known_updates


def main():
    known = load_json(KNOWN_LINKS_FILE, {})
    session = requests.Session()

    all_new = []
    all_known_updates = {}

    for source in HUB_SOURCES:
        try:
            new_items, known_updates = process_source(source, known, session)
            all_new.extend(new_items)
            all_known_updates.update(known_updates)
            print(f"[{source['name']}] 新着 {len(new_items)}件")
        except Exception as e:
            print(f"[{source['name']}] 取得失敗: {e}")

    merge_new_items(all_new, all_known_updates)
    print(f"ハブ監視ソース合計: 新着 {len(all_new)}件")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[ERROR] 予期しないエラー: {e}")
        sys.exit(0)
