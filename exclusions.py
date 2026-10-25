#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
市と市立病院の記事のうち、市民向けの新着情報としては載せない分野を判定する。

対象の出典:
  - 近江八幡市公式サイト
  - 近江八幡市立総合医療センター

除外する分野(サイト運営者の指定):
  - 入札・調達(入札予報・入札結果・業務委託・プロポーザル等)
  - 職員採用試験に関するもの(病院の看護職などの職員募集を含む)
  - 任用職員(会計年度任用職員など)に関するもの
  - 指定管理者・運営事業者などの事業者募集

URLの形(ページの置き場所)とタイトルの言葉の両方で判定する。
除外する言葉を増減したい場合は、下の一覧を書き換える。
(関数名の is_excluded_city_item は、build_feed.py から呼ばれているため変えていない)
"""

import re
from urllib.parse import urlparse

# 出典ごとの「記事の置き場所(URLの途中の文字列)」で判定するもの
EXCLUDED_PATH_PATTERNS = {
    "近江八幡市公式サイト": [
        re.compile(r"/nyusatsu/"),         # 入札・契約(入札予報・入札結果・プロポーザル等)
        re.compile(r"/saiyou/"),           # 職員採用
        re.compile(r"/syokuin_bosyu/"),    # 職員募集
    ],
    "近江八幡市立総合医療センター": [
        re.compile(r"/bid/"),              # 入札
        re.compile(r"/recruit/"),          # 職員募集(会計年度任用職員など)
        re.compile(r"/nurse/"),            # 看護職の職員募集
    ],
}

# タイトルの言葉で判定するもの(上記の出典すべてに共通)
EXCLUDED_TITLE_PATTERNS = [
    # 入札・調達
    re.compile(r"入札|調達|落札|業務委託|プロポーザル"),
    # 指定管理者・運営事業者などの事業者募集
    re.compile(r"指定管理者|運営事業者|運営法人|事業者.{0,8}(募集|公募)|(募集|公募).{0,8}事業者"),
    # 職員採用試験
    re.compile(r"職員採用|採用試験|採用選考|採用候補者|企業職員"),
    # 任用職員
    re.compile(r"任用|任期付|臨時職員|非常勤職員|嘱託職員|会計年度"),
]


def is_excluded_city_item(item: dict) -> bool:
    """市・市立病院の記事で、載せない分野(入札・調達/職員採用/任用職員)かどうか"""
    path_patterns = EXCLUDED_PATH_PATTERNS.get(item.get("source") or "")
    if path_patterns is None:
        return False
    path = urlparse(item.get("link") or "").path
    if any(p.search(path) for p in path_patterns):
        return True
    title = item.get("title") or ""
    return any(p.search(title) for p in EXCLUDED_TITLE_PATTERNS)
