#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ハブページ一覧の作成(初回・部署再編時・月1回のみ実行)

近江八幡市公式サイトの「巡回すべき一覧ページ」を洗い出して hubs.json に保存する。

階層のイメージ:
  各課の窓口(/2085.html)
    └ 部署トップ        /soshiki/aduchikyouiku/index.html             ← ハブ
        └ 小区分(事業別) /soshiki/aduchikyouiku/setsumeikai/index.html ← ハブ(今回追加)
            └ 個別記事   /soshiki/aduchikyouiku/setsumeikai/25425.html ← 新着記事

従来は部署トップまでしか巡回していなかったため、小区分ページ自体が
「新着記事」として扱われ、その配下の個別記事を取りこぼしていた。
"""

import json
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
    get_robot_parser,
    normalize_url,
    REQUEST_INTERVAL_SEC,
    USER_AGENT,
)

BASE_URL = "https://www.city.omihachiman.lg.jp"
DEPARTMENT_LIST_URL = f"{BASE_URL}/2085.html"  # 各課の窓口

# 全体の一覧ページ(常にハブに含める)
FIXED_HUBS = [
    f"{BASE_URL}/juyo_info/index.html",  # 重要なお知らせ
    f"{BASE_URL}/news/index.html",       # お知らせ
    f"{BASE_URL}/bosyu/index.html",      # 募集情報
    f"{BASE_URL}/event/index.html",      # イベント情報
]

# 部署トップ: /soshiki/xxxx/index.html
DEPT_TOP_PATTERN = re.compile(r"^/soshiki/[^/]+/index\.html$")
# 部署配下の一覧ページ(小区分): /soshiki/xxxx/yyyy/index.html など
SUB_INDEX_PATTERN = re.compile(r"^/soshiki/[^/]+/.+/index\.html$")

# 部署トップから何段下まで一覧ページを探すか
MAX_DEPTH = 2

HUBS_FILE = Path("hubs.json")


def collect_index_links(url, session, rp, pattern):
    """指定ページ内から、パターンに一致する一覧ページのURLを集める"""
    if not rp.can_fetch(USER_AGENT, url):
        return []
    try:
        resp = fetch_bytes(url, session)
        html = decode_response(resp)
    except Exception as e:
        print(f"  [SKIP] {url}: {e}")
        return []
    time.sleep(REQUEST_INTERVAL_SEC)

    soup = BeautifulSoup(html, "html.parser")
    found = []
    for a in soup.find_all("a", href=True):
        abs_url = normalize_url(urljoin(url, a["href"]))
        parsed = urlparse(abs_url)
        if parsed.netloc and parsed.netloc != urlparse(BASE_URL).netloc:
            continue
        if pattern.match(parsed.path):
            found.append(abs_url)
    return found


def main():
    session = requests.Session()
    rp = get_robot_parser(BASE_URL)

    # 1. 各課の窓口ページから部署トップを集める
    dept_tops = sorted(set(collect_index_links(DEPARTMENT_LIST_URL, session, rp, DEPT_TOP_PATTERN)))
    print(f"部署トップページ: {len(dept_tops)}件")

    # 2. 部署トップから配下の一覧ページ(小区分)を集める。さらに1段下も探す。
    all_hubs = set(FIXED_HUBS) | set(dept_tops)
    frontier = list(dept_tops)
    sub_count = 0

    for depth in range(1, MAX_DEPTH + 1):
        newly_found = set()
        for i, url in enumerate(frontier, 1):
            for s in collect_index_links(url, session, rp, SUB_INDEX_PATTERN):
                if s not in all_hubs:
                    newly_found.add(s)
            if i % 20 == 0:
                print(f"  深さ{depth}: {i}/{len(frontier)}ページ確認済み")

        print(f"深さ{depth}で新たに見つかった一覧ページ: {len(newly_found)}件")
        if not newly_found:
            break
        all_hubs |= newly_found
        sub_count += len(newly_found)
        frontier = sorted(newly_found)

    hubs = sorted(all_hubs)
    HUBS_FILE.write_text(json.dumps(hubs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nハブページ 合計{len(hubs)}件を hubs.json に保存しました。")
    print(f"  内訳: 全体一覧{len(FIXED_HUBS)}件 / 部署トップ{len(dept_tops)}件 / 小区分{sub_count}件")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[ERROR] 予期しないエラー: {e}")
        sys.exit(1)
