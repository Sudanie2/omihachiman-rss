#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
近江八幡市議会 インターネット中継(録画)の取得

ページは「令和8年」のような年の見出しの下に、会期ごとの見出し
(例:令和８年第３回（９月）近江八幡市議会定例会)が並び、その下に
各日の録画へのリンク(例: 9月1日(火) 初日)が続く構成。

会期セクションをまたいでも、リンク先のID番号(list/332等)は
公開順に単調増加している。そのためID番号を「検知済みかどうか」の
判定にそのまま使えば、セクション内の見た目の並び順に振り回されずに
新着を正しく検出できる。

年の情報は各日付のリンク自体には含まれないため、ページを先頭から
順にたどりながら「令和8年」のような年見出しを見つけるたびに更新し、
以降の日付リンクにその年を適用する。

著作権表示は「映像」の複製・転用を禁じるものであり、映像や議事録
本文は一切取得しない。取得するのはタイトル(日付+項目)とURLのみ。
"""

import re
import sys
from datetime import datetime

from bs4 import BeautifulSoup, NavigableString, Tag

from common import (
    fetch_bytes,
    decode_response,
    get_robot_parser,
    load_json,
    merge_new_items,
    normalize_url,
    now_iso,
    JST,
    KNOWN_LINKS_FILE,
    USER_AGENT,
)

BASE_URL = "https://omihachiman.media-streaming.jp"
PAGE_URL = f"{BASE_URL}/recording/meeting/"
SOURCE_NAME = "近江八幡市議会 インターネット中継"

# 個別の録画ページのURL(会期セクションをまたいでもID順=公開順)
DETAIL_PATTERN = re.compile(r"^/recording/meeting/list/(\d+)/?$")

# 年の見出し(リンクテキストが「令和8年」等そのもの)
ERA_PATTERN = re.compile(r"^(令和|平成)(\d+|元)年$")

# 各日のリンクの文字列(例: "9月1日(火) 初日" / "5月20日(水)")
DATE_LABEL_PATTERN = re.compile(r"^(\d{1,2})月(\d{1,2})日[（(].[）)]\s*(.*)$")

# 会期名の見出し(例: 令和８年第３回（９月）近江八幡市議会定例会)
SESSION_PATTERN = re.compile(r"(定例会|臨時会)\s*$")


def era_to_year(era: str, num_text: str) -> int:
    num = 1 if num_text == "元" else int(num_text)
    if era == "令和":
        return 2018 + num
    if era == "平成":
        return 1988 + num
    raise ValueError(f"未対応の元号: {era}")


def main():
    rp = get_robot_parser(BASE_URL)
    if not rp.can_fetch(USER_AGENT, PAGE_URL):
        print(f"[{SOURCE_NAME}] robots.txtでブロックされているため中止します。")
        return

    resp = fetch_bytes(PAGE_URL)
    html = decode_response(resp)
    soup = BeautifulSoup(html, "html.parser")

    known = load_json(KNOWN_LINKS_FILE, {})
    ts = now_iso()

    new_items = []
    known_updates = {}
    seen = set()
    total = 0

    current_year = None
    current_session = ""

    for node in soup.descendants:
        if isinstance(node, Tag) and node.name == "a" and node.get("href"):
            text = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()

            # 年見出し(令和8年 等)
            m_era = ERA_PATTERN.match(text)
            if m_era:
                current_year = era_to_year(m_era.group(1), m_era.group(2))
                continue

            # 個別の録画リンク
            m_url = DETAIL_PATTERN.match(__import__("urllib.parse", fromlist=["urlparse"]).urlparse(
                normalize_url(node.get("href"))
            ).path)
            if not m_url:
                continue

            m_label = DATE_LABEL_PATTERN.match(text)
            if not m_label or current_year is None:
                # 年がまだ分からない、または日付として読めない場合はスキップ
                continue

            url = normalize_url(__import__("urllib.parse", fromlist=["urljoin"]).urljoin(PAGE_URL, node["href"]))
            total += 1
            if url in known or url in seen:
                continue
            seen.add(url)

            month, day = int(m_label.group(1)), int(m_label.group(2))
            try:
                pub_dt = datetime(current_year, month, day, tzinfo=JST)
            except ValueError:
                continue

            title = text  # 例: "9月1日(火) 初日"
            known_updates[url] = {"title": title, "first_seen": ts}
            new_items.append(
                {
                    "title": title,
                    "link": url,
                    "source": SOURCE_NAME,
                    "description": current_session,
                    "pubDate": pub_dt.strftime("%a, %d %b %Y %H:%M:%S %z"),
                }
            )

        elif isinstance(node, NavigableString):
            text = re.sub(r"\s+", "", str(node))
            if SESSION_PATTERN.search(text):
                current_session = re.sub(r"\s+", " ", str(node)).strip()

    print(f"[{SOURCE_NAME}] 掲載中のリンク {total}件 / 新着 {len(new_items)}件")
    merge_new_items(new_items, known_updates)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[ERROR] 予期しないエラー: {e}")
        sys.exit(0)
