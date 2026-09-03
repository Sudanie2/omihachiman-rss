#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ハブページ一覧の作成(初回・部署再編時のみ実行)

「各課の窓口」ページ(/2085.html)には全部署へのリンクが一覧化されているため、
これを起点に「部署トップページ(ハブページ)」の一覧を作成します。

このスクリプトは滅多に実行しません(部署の新設・統廃合があった時だけ再実行)。
毎日実行するのは watch_hubs_and_generate_rss.py の方です。

出力: hubs.json (ハブページURLのリスト)
"""

import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.city.omihachiman.lg.jp"
DEPARTMENT_LIST_URL = f"{BASE_URL}/2085.html"  # 各課の窓口

# 4つの主要な一覧ページ(citywide list)は必ずハブに含める
FIXED_HUBS = [
    f"{BASE_URL}/juyo_info/index.html",  # 重要なお知らせ
    f"{BASE_URL}/news/index.html",       # お知らせ
    f"{BASE_URL}/bosyu/index.html",      # 募集情報
    f"{BASE_URL}/event/index.html",      # イベント情報
]

USER_AGENT = "OmihachimanRSSBot/1.0 (+personal monitoring; contact: TS/KURA)"
REQUEST_TIMEOUT_SEC = 15

# 部署トップページのURLパターン: /soshiki/xxxx/index.html
DEPT_PAGE_PATTERN = re.compile(r"^/soshiki/[^/]+/index\.html$")


def main():
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(DEPARTMENT_LIST_URL, headers=headers, timeout=REQUEST_TIMEOUT_SEC)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding
    soup = BeautifulSoup(resp.text, "html.parser")

    dept_hubs = set()
    for a in soup.find_all("a", href=True):
        abs_url = urljoin(DEPARTMENT_LIST_URL, a["href"])
        path = urlparse(abs_url).path
        if DEPT_PAGE_PATTERN.match(path):
            dept_hubs.add(abs_url)

    hubs = sorted(set(FIXED_HUBS) | dept_hubs)

    Path("hubs.json").write_text(
        json.dumps(hubs, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"ハブページ {len(hubs)}件を hubs.json に保存しました。")
    print("内訳: 固定4ページ + 部署トップページ", len(dept_hubs), "件")


if __name__ == "__main__":
    main()
