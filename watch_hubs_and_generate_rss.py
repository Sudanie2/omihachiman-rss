#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
近江八幡市公式サイト(city.omihachiman.lg.jp) 新着監視スクリプト

hubs.json に登録された一覧ページ(全体一覧・部署トップ・小区分ページ)を巡回し、
その配下にある個別記事のうち、新しく出現したものを検出する。

重要な区別:
  - 「/index.html」で終わるページ = 一覧ページ(ハブ)。記事としては扱わない。
  - それ以外のhtmlページ           = 個別記事。新着検出の対象。

巡回中に hubs.json に無い一覧ページを見つけた場合は hubs.json に追記し、
次回以降その配下も巡回対象になる。これにより、組織別(/soshiki/)だけでなく
分野別(/gyosei/ 行政情報、/kurashi/ くらし等)の階層も自動的に取り込まれ、
新しい分野やページが追加されても追従できる。

1回の実行で巡回するハブ数には上限を設け、続きは次回に持ち越す(サーバー負荷への配慮)。
"""

import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from common import (
    fetch_bytes,
    decode_response,
    extract_page_title,
    get_robot_parser,
    load_json,
    merge_new_items,
    normalize_url,
    now_iso,
    now_rfc822,
    save_json,
    KNOWN_LINKS_FILE,
    REQUEST_INTERVAL_SEC,
    USER_AGENT,
)

BASE_URL = "https://www.city.omihachiman.lg.jp"
SOURCE_NAME = "近江八幡市公式サイト"

HUBS_FILE = Path("hubs.json")
HUB_CURSOR_FILE = Path("hub_cursor.json")

# 1回の実行あたりの上限(サーバー負荷と実行時間の抑制)
MAX_HUBS_PER_RUN = 300
MAX_NEW_PAGE_FETCH_PER_RUN = 80

# 一覧ページ(ハブ)とみなすURL
HUB_PATH_PATTERN = re.compile(r"/index\.html$")
# 自動でハブに追加する一覧ページ。
# 組織別(/soshiki/)だけでなく分野別(/gyosei/ 行政情報、/kurashi/ くらし等)も対象にする。
AUTO_HUB_PATTERN = re.compile(r"^/.+/index\.html$")

EXCLUDE_PATTERNS = [
    r"^/cgi-bin/",
    r"\.(pdf|jpg|jpeg|png|gif|zip|docx?|xlsx?|pptx?)$",
]


def is_same_site(url):
    parsed = urlparse(url)
    return not parsed.netloc or parsed.netloc == urlparse(BASE_URL).netloc


def is_html_page(url):
    path = urlparse(url).path or "/"
    for pattern in EXCLUDE_PATTERNS:
        if re.search(pattern, path):
            return False
    last = path.rsplit("/", 1)[-1]
    if "." in last and not path.endswith((".html", ".htm")):
        return False
    return True


def is_hub_page(url):
    """一覧ページ(記事ではない)かどうか"""
    path = urlparse(url).path or "/"
    return bool(HUB_PATH_PATTERN.search(path)) or path.endswith("/")


def main():
    hubs = load_json(HUBS_FILE, None)
    if hubs is None:
        print("hubs.json が見つかりません。先に discover_hubs.py を実行してください。")
        return

    rp = get_robot_parser(BASE_URL)
    known = load_json(KNOWN_LINKS_FILE, {})
    session = requests.Session()

    # 前回の続きから巡回する(全ハブを数回に分けて回る)
    cursor = load_json(HUB_CURSOR_FILE, {}).get("index", 0)
    if cursor >= len(hubs):
        cursor = 0
    target_hubs = hubs[cursor:cursor + MAX_HUBS_PER_RUN]
    next_cursor = cursor + len(target_hubs)
    if next_cursor >= len(hubs):
        next_cursor = 0

    article_candidates = []
    seen_in_run = set()
    new_hubs = set()

    for hub_url in target_hubs:
        if not rp.can_fetch(USER_AGENT, hub_url):
            continue
        try:
            resp = fetch_bytes(hub_url, session)
            html = decode_response(resp)
        except Exception as e:
            print(f"[SKIP] {hub_url}: {e}")
            continue
        time.sleep(REQUEST_INTERVAL_SEC)

        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            abs_url = normalize_url(urljoin(hub_url, a["href"]))
            if not is_same_site(abs_url) or not is_html_page(abs_url):
                continue

            if is_hub_page(abs_url):
                # 一覧ページは記事ではない。未登録なら次回以降の巡回対象に加える。
                path = urlparse(abs_url).path
                if AUTO_HUB_PATTERN.match(path) and abs_url not in hubs:
                    new_hubs.add(abs_url)
                continue

            if abs_url in known or abs_url in seen_in_run:
                continue
            seen_in_run.add(abs_url)
            article_candidates.append(abs_url)

    # 新しく見つかった一覧ページをhubs.jsonに追記
    if new_hubs:
        hubs = sorted(set(hubs) | new_hubs)
        save_json(HUBS_FILE, hubs)
        print(f"新しい一覧ページ {len(new_hubs)}件を hubs.json に追加しました。")

    # 記事候補を開いてタイトルを取得
    new_items = []
    known_updates = {}
    ts = now_iso()
    ts_rfc822 = now_rfc822()

    for i, url in enumerate(sorted(article_candidates)):
        if i >= MAX_NEW_PAGE_FETCH_PER_RUN:
            print(f"記事取得の上限({MAX_NEW_PAGE_FETCH_PER_RUN}件)に達したため残りは次回に持ち越します。")
            break
        if not rp.can_fetch(USER_AGENT, url):
            continue
        try:
            resp = fetch_bytes(url, session)
            html = decode_response(resp)
        except Exception as e:
            print(f"[SKIP] {url}: {e}")
            continue
        time.sleep(REQUEST_INTERVAL_SEC)

        soup = BeautifulSoup(html, "html.parser")
        title = extract_page_title(soup)

        known_updates[url] = {"title": title, "first_seen": ts}
        new_items.append(
            {
                "title": title,
                "link": url,
                "source": SOURCE_NAME,
                "pubDate": ts_rfc822,
            }
        )

    merge_new_items(new_items, known_updates)
    save_json(HUB_CURSOR_FILE, {"index": next_cursor})

    print(
        f"[{SOURCE_NAME}] ハブ巡回 {len(target_hubs)}/{len(hubs)}件"
        f"(次回は{next_cursor}件目から) / 記事候補 {len(article_candidates)}件 / 新着 {len(new_items)}件"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[ERROR] 予期しないエラー: {e}")
        sys.exit(0)
