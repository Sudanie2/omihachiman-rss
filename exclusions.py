#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
近江八幡市公式サイトの記事のうち、市民向けの新着情報としては載せない分野を判定する。

除外する分野(サイト運営者の指定):
  - 入札・調達(入札予報・入札結果・業務委託・プロポーザル等)
  - 職員採用試験に関するもの
  - 任用職員(会計年度任用職員など)に関するもの

URLの形(ページの置き場所)とタイトルの言葉の両方で判定する。
除外する言葉を増減したい場合は、下の2つの一覧を書き換える。
"""

import re
from urllib.parse import urlparse

TARGET_SOURCE = "近江八幡市公式サイト"

# 記事の置き場所(URLの途中の文字列)で判定するもの
EXCLUDED_PATH_PATTERNS = [
    re.compile(r"/nyusatsu/"),         # 入札・契約(入札予報・入札結果・プロポーザル等)
    re.compile(r"/saiyou/"),           # 職員採用
    re.compile(r"/syokuin_bosyu/"),    # 職員募集
]

# タイトルの言葉で判定するもの
EXCLUDED_TITLE_PATTERNS = [
    # 入札・調達
    re.compile(r"入札|調達|落札|業務委託|プロポーザル"),
    # 職員採用試験
    re.compile(r"職員採用|採用試験|採用選考|採用候補者"),
    # 任用職員
    re.compile(r"任用|任期付|臨時職員|非常勤職員|嘱託職員|会計年度"),
]


def is_excluded_city_item(item: dict) -> bool:
    """市公式サイトの記事で、載せない分野(入札・調達/職員採用/任用職員)かどうか"""
    if (item.get("source") or "") != TARGET_SOURCE:
        return False
    path = urlparse(item.get("link") or "").path
    if any(p.search(path) for p in EXCLUDED_PATH_PATTERNS):
        return True
    title = item.get("title") or ""
    return any(p.search(title) for p in EXCLUDED_TITLE_PATTERNS)
