#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
近江八幡市公式サイト(city.omihachiman.lg.jp) 新着監視スクリプト

discover_hubs.py で作成した hubs.json(部署トップページ+主要一覧ページ)を巡回し、
新しく出現したリンクを新着記事として検出する。
"""

import sys
import time
from urllib.parse import urljoin, urlparse
import re

import requests
from bs4 import BeautifulSoup

from common import (
    fetch_bytes,
    decode_response,
    get_robot_parser,
    load_json,
    merge_new_items,
    normalize_url,
    now_iso,
    now_rfc822,
    KNOWN_LINKS_FILE,
    REQUEST_INTERVAL_SEC,
    USER_AGENT,
)

BASE_URL = "https://www.city.omihachiman.lg.jp"
SOURCE_NAME = "近江八幡市公式サイト"
HUBS_FILE = "hubs.json"

MAX_NEW_PAGE_FETCH_PER_RUN = 80
TITLE_SELECTORS = ["h1", "title"]

EXCLUDE_PATTERNS = [
    r"^/cgi-bin/",
    r"\.(pdf|jpg|jpeg|png|gif|zip|docx?|xlsx?|pptx?)$",
]


def is_target_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.netloc and parsed.netloc != urlparse(BASE_URL).netloc:
        return False
    path = parsed.path or "/"
    for pattern in EXCLUDE_PATTERNS:
        if re.search(pattern, path):
            return False
    if "." in path.rsplit("/", 1)[-1] and not path.endswith((".html", ".htm")):
        return False
    return True


def extract_title(soup: BeautifulSoup) -> str:
    for sel in TITLE_SELECTORS:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            return el.get_text(strip=True)
    return "(タイトル不明)"


def main():
    from pathlib import Path

    hubs = load_json(Path(HUBS_FILE), None)
    if hubs is None:
        print("hubs.json が見つかりません。先に discover_hubs.py を実行してください。")
        return

    rp = get_robot_parser(BASE_URL)
    known = load_json(KNOWN_LINKS_FILE, {})
    session = requests.Session()

    candidate_new = []
    seen_in_run = set()

    for hub_url in hubs:
        if not rp.can_fetch(USER_AGENT, hub_url):
            print(f"[robots.txtでブロック] {hub_url}")
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
            if not is_target_url(abs_url):
                continue
            if abs_url in known or abs_url in seen_in_run:
                continue
            seen_in_run.add(abs_url)
            candidate_new.append(abs_url)

    new_items = []
    known_updates = {}
    ts = now_iso()
    ts_rfc822 = now_rfc822()

    for i, url in enumerate(sorted(candidate_new)):
        if i >= MAX_NEW_PAGE_FETCH_PER_RUN:
            print(f"上限({MAX_NEW_PAGE_FETCH_PER_RUN}件)に達したため残りは次回に持ち越します。")
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
        title = extract_title(soup)

        known_updates[url] = {"title": title, "first_seen": ts}
        new_items.append(
            {
                "title": title,
                "link": url,
                "source": SOURCE_NAME,
                "description": f"新着ページを検出しました: {url}",
                "pubDate": ts_rfc822,
            }
        )

    merge_new_items(new_items, known_updates)
    print(f"[{SOURCE_NAME}] ハブページ巡回 {len(hubs)}件 / 新着 {len(new_items)}件")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[ERROR] 予期しないエラー: {e}")
        sys.exit(0)
