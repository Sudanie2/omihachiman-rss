#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
近江八幡商工会議所(8cci.com) 最新情報の取得

RSS配信がないため、最新情報一覧ページ(https://8cci.com/topics/)を解析する。

一覧の各行は「日付 + カテゴリタグ + タイトル」の形式:
    2026.08.27  お知らせ はちまんフェスタ2026 9月26日 開催！
    2026.08.28  販路開拓 【募集期間延長のお知らせ】FOOD STYLE JAPAN2027 出展者募集中！

このうち「お知らせ」タグが付いた記事だけを取得する。
リンク先は自サイト内の他ページや外部サイトの場合もあるが、そのまま記事URLとして扱う。
"""

import re
import sys
from datetime import datetime

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
    JST,
    KNOWN_LINKS_FILE,
    USER_AGENT,
)
from urllib.parse import urljoin

BASE_URL = "https://8cci.com"
PAGE_URL = f"{BASE_URL}/topics/"
SOURCE_NAME = "近江八幡商工会議所"

# 取得対象のカテゴリタグ
TARGET_TAG = "お知らせ"

# 一覧に出てくるカテゴリタグ(タイトルから取り除くために使う)
ALL_TAGS = [
    "お知らせ", "販路開拓", "検定", "セミナー", "補助金",
    "相談会", "創業支援", "保険・共済", "支援金", "事業承継",
]

DATE_PATTERN = re.compile(r"(20\d{2})[.\-/年](\d{1,2})[.\-/月](\d{1,2})")


def find_date_near(a_tag):
    """
    リンクの近くにある日付(2026.08.27形式)を探す。
    リンクの前の要素 → 親要素の順に、範囲を限定して探索する。
    """
    # 直前の兄弟要素
    for sibling in a_tag.previous_siblings:
        text = sibling.get_text(" ", strip=True) if hasattr(sibling, "get_text") else str(sibling).strip()
        if text:
            m = DATE_PATTERN.search(text)
            if m:
                return m
            break  # 直前の非空要素に無ければ親を見る

    # 親をたどる(テキストが長すぎる要素は一覧全体なので除外)
    node = a_tag
    for _ in range(4):
        node = node.parent
        if node is None:
            break
        text = node.get_text(" ", strip=True)
        if len(text) > 300:
            break
        m = DATE_PATTERN.search(text)
        if m:
            return m
    return None


def split_tag_and_title(text: str):
    """「お知らせ ○○○」を (タグ, タイトル) に分ける"""
    text = re.sub(r"\s+", " ", text).strip()
    for tag in ALL_TAGS:
        if text.startswith(tag):
            return tag, text[len(tag):].strip()
    return None, text


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
    total_notices = 0

    for a in soup.find_all("a", href=True):
        raw_text = a.get_text(" ", strip=True)
        if not raw_text:
            continue

        tag, title = split_tag_and_title(raw_text)
        if tag != TARGET_TAG or not title:
            continue

        total_notices += 1
        url = normalize_url(urljoin(PAGE_URL, a["href"]))
        # ページ内リンク(#付き)は元のURLを保持したいのでアンカーを残す
        full_url = urljoin(PAGE_URL, a["href"])

        if full_url in known or full_url in seen:
            continue
        seen.add(full_url)

        m = find_date_near(a)
        if m:
            try:
                pub_dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=JST)
            except ValueError:
                pub_dt = datetime.now(JST)
        else:
            pub_dt = datetime.now(JST)

        known_updates[full_url] = {"title": title, "first_seen": ts}
        new_items.append(
            {
                "title": title,
                "link": full_url,
                "source": SOURCE_NAME,
                "pubDate": pub_dt.strftime("%a, %d %b %Y %H:%M:%S %z"),
            }
        )

    if total_notices == 0:
        print(f"[{SOURCE_NAME}] 「{TARGET_TAG}」の記事が見つかりません。ページ構造が変わった可能性があります。")

    merge_new_items(new_items, known_updates)
    print(f"[{SOURCE_NAME}] 「{TARGET_TAG}」記事 {total_notices}件 / 新着 {len(new_items)}件")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[ERROR] 予期しないエラー: {e}")
        sys.exit(0)
