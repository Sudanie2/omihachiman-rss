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
TOP_PAGE_URL = f"{BASE_URL}/index.html"        # トップページ(分野別の入口)

# 全体の一覧ページ(常にハブに含める)
FIXED_HUBS = [
    f"{BASE_URL}/juyo_info/index.html",  # 重要なお知らせ
    f"{BASE_URL}/news/index.html",       # お知らせ
    f"{BASE_URL}/bosyu/index.html",      # 募集情報
    f"{BASE_URL}/event/index.html",      # イベント情報
]

# サイト内のあらゆる一覧ページ(/index.html で終わるページ)をハブとみなす。
# 組織別(/soshiki/)だけでなく、分野別(/gyosei/ 行政情報、/kurashi/ くらし 等)も対象。
INDEX_PATTERN = re.compile(r"^/.+/index\.html$")

# 何段下まで一覧ページを探すか
MAX_DEPTH = 3
# 1回の実行で取得するページ数の上限(サーバー負荷への配慮)
MAX_FETCH = 500

HUBS_FILE = Path("hubs.json")
DEPT_NAMES_FILE = Path("dept_names.json")

# 部署トップ: /soshiki/xxxx/index.html (課名の対応表を作るために使う)
DEPT_TOP_PATTERN = re.compile(r"^/soshiki/([^/]+)/index\.html$")


fetch_count = 0


def collect_index_links(url, session, rp, pattern):
    global fetch_count
    if fetch_count >= MAX_FETCH:
        return []
    """指定ページ内から、パターンに一致する一覧ページのURLを集める"""
    if not rp.can_fetch(USER_AGENT, url):
        return []
    try:
        resp = fetch_bytes(url, session)
        html = decode_response(resp)
    except Exception as e:
        print(f"  [SKIP] {url}: {e}")
        return []
    fetch_count += 1
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


def collect_department_names(url, session, rp):
    """
    「各課の窓口」ページから、URLの部署名(slug)と実際の課名の対応表を作る。
    例: "suidou_sisetsu" -> "上下水道課 施設グループ"
    記事の出典表示で「各課」ではなく実際の課名を出すために使う。
    """
    global fetch_count
    if not rp.can_fetch(USER_AGENT, url):
        return {}
    try:
        resp = fetch_bytes(url, session)
        html = decode_response(resp)
    except Exception as e:
        print(f"  [SKIP] {url}: {e}")
        return {}
    fetch_count += 1
    time.sleep(REQUEST_INTERVAL_SEC)

    soup = BeautifulSoup(html, "html.parser")
    names = {}
    for a in soup.find_all("a", href=True):
        abs_url = normalize_url(urljoin(url, a["href"]))
        m = DEPT_TOP_PATTERN.match(urlparse(abs_url).path)
        if not m:
            continue
        text = re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip()
        if text and len(text) <= 30:
            names[m.group(1)] = text
    return names


def main():
    session = requests.Session()
    rp = get_robot_parser(BASE_URL)

    # 1. 出発点(トップページ・各課の窓口)から一覧ページを集める
    all_hubs = set(FIXED_HUBS)
    frontier = set()
    for seed in (TOP_PAGE_URL, DEPARTMENT_LIST_URL):
        frontier |= set(collect_index_links(seed, session, rp, INDEX_PATTERN))
    frontier -= all_hubs
    all_hubs |= frontier
    print(f"第1階層で見つかった一覧ページ: {len(frontier)}件")

    # 2. さらに下の階層の一覧ページを順に探す
    frontier = sorted(frontier)
    for depth in range(2, MAX_DEPTH + 1):
        newly_found = set()
        for i, url in enumerate(frontier, 1):
            for s in collect_index_links(url, session, rp, INDEX_PATTERN):
                if s not in all_hubs:
                    newly_found.add(s)
            if i % 25 == 0:
                print(f"  第{depth}階層: {i}/{len(frontier)}ページ確認済み(取得 {fetch_count}件)")

        print(f"第{depth}階層で新たに見つかった一覧ページ: {len(newly_found)}件")
        if not newly_found or fetch_count >= MAX_FETCH:
            break
        all_hubs |= newly_found
        frontier = sorted(newly_found)

    if fetch_count >= MAX_FETCH:
        print(f"取得上限({MAX_FETCH}件)に達しました。未探索の階層は日々の巡回時に自動で追加されます。")

    # 3. 課名の対応表を作る
    dept_names = collect_department_names(DEPARTMENT_LIST_URL, session, rp)
    DEPT_NAMES_FILE.write_text(
        json.dumps(dept_names, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"課名の対応表: {len(dept_names)}件を dept_names.json に保存しました。")

    hubs = sorted(all_hubs)
    HUBS_FILE.write_text(json.dumps(hubs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nハブページ 合計{len(hubs)}件を hubs.json に保存しました。(取得ページ数 {fetch_count}件)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[ERROR] 予期しないエラー: {e}")
        sys.exit(1)
