#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一覧ページ解析型の新着取得(統合版)

RSS配信がなく、「日付 + タイトルリンク」が並ぶ一覧ページを持つサイトを扱う。

対象:
  - 近江八幡商工会議所           : カテゴリタグ「お知らせ」の記事のみ
  - ラコリーナ近江八幡           : 新着情報の全記事
  - 近江八幡市立健康ふれあい公園 : 新着情報の全記事

注意: サイトによっては「日付」と「タイトル」が別々のリンクになっており、
どちらも同じ記事を指す。日付だけのリンクはタイトルとして採用しない。

1つのサイトで取得に失敗しても、他のサイトの処理は続行する。
"""

import re
import sys
from datetime import datetime
from urllib.parse import urljoin, urlparse, parse_qsl, urlencode, urlunparse

import requests
from bs4 import BeautifulSoup

from common import (
    fetch_bytes,
    decode_response,
    get_robot_parser,
    load_json,
    merge_new_items,
    now_iso,
    JST,
    KNOWN_LINKS_FILE,
    USER_AGENT,
)

LIST_SOURCES = [
    {
        "name": "近江八幡商工会議所",
        "base": "https://8cci.com",
        "url": "https://8cci.com/topics/",
        # 一覧に出てくるカテゴリタグ(タイトル先頭から取り除く)
        "tags": [
            "お知らせ", "販路開拓", "検定", "セミナー", "補助金",
            "相談会", "創業支援", "保険・共済", "支援金", "事業承継",
        ],
        # このタグの記事だけ採用する(Noneなら全件)
        "tag_filter": "お知らせ",
        # 記事リンクと判定するURLパターン(Noneならタグで判定)
        "link_pattern": None,
        # URLから取り除くクエリ(同じ記事が別URL扱いになるのを防ぐ)
        "drop_query": [],
    },
    {
        "name": "ラコリーナ近江八幡",
        "base": "https://taneya.jp",
        "url": "https://taneya.jp/la_collina/news/",
        "tags": [],
        "tag_filter": None,
        "link_pattern": r"/la_collina/news/detail/\d+",
        "drop_query": [],
    },
    {
        "name": "近江八幡市立健康ふれあい公園",
        "base": "https://www.omi8man-kenkofureai.jp",
        "url": "https://www.omi8man-kenkofureai.jp/news/index.html",
        "tags": [],
        "tag_filter": None,
        "link_pattern": r"/news/detail\.php",
        # ref=/news/index.html は遷移元を示すだけなので除去する
        "drop_query": ["ref"],
    },
]

DATE_PATTERN = re.compile(r"(20\d{2})[.\-/年](\d{1,2})[.\-/月](\d{1,2})")
# 「2026年9月1日」のように日付だけのリンク(タイトルではない)を判定する
DATE_ONLY_PATTERN = re.compile(r"^\s*20\d{2}[.\-/年]\s*\d{1,2}[.\-/月]\s*\d{1,2}\s*日?\s*$")


def clean_url(url: str, drop_query) -> str:
    """不要なクエリを取り除いてURLを正規化する"""
    if not drop_query:
        return url
    parsed = urlparse(url)
    kept = [(k, v) for k, v in parse_qsl(parsed.query) if k not in drop_query]
    return urlunparse(parsed._replace(query=urlencode(kept)))


def find_date_near(a_tag):
    """リンクの近くにある日付を探す(直前の要素 → 親要素の順)"""
    for sibling in a_tag.previous_siblings:
        text = sibling.get_text(" ", strip=True) if hasattr(sibling, "get_text") else str(sibling).strip()
        if text:
            m = DATE_PATTERN.search(text)
            if m:
                return m
            break

    node = a_tag
    for _ in range(4):
        node = node.parent
        if node is None:
            break
        # 複数の記事リンクを含む要素まで遡ると、別の記事の日付を拾ってしまう
        if len(node.find_all("a")) > 1:
            break
        text = node.get_text(" ", strip=True)
        if len(text) > 300:
            break
        m = DATE_PATTERN.search(text)
        if m:
            return m
    return None


def split_tag_and_title(text: str, tags):
    """「お知らせ ○○○」を (タグ, タイトル) に分ける"""
    text = re.sub(r"\s+", " ", text).strip()
    for tag in tags:
        if text.startswith(tag):
            return tag, text[len(tag):].strip()
    return None, text


def process_source(source, known, seen):
    rp = get_robot_parser(source["base"])
    if not rp.can_fetch(USER_AGENT, source["url"]):
        print(f"[{source['name']}] robots.txtでブロックされているため中止します。")
        return [], {}

    resp = fetch_bytes(source["url"])
    html = decode_response(resp)
    soup = BeautifulSoup(html, "html.parser")

    link_re = re.compile(source["link_pattern"]) if source["link_pattern"] else None
    ts = now_iso()

    new_items = []
    known_updates = {}
    matched = 0

    for a in soup.find_all("a", href=True):
        url = urljoin(source["url"], a["href"])

        # 記事リンクかどうかの判定
        if link_re and not link_re.search(urlparse(url).path + "?" + (urlparse(url).query or "")):
            continue

        raw_text = a.get_text(" ", strip=True)
        if not raw_text:
            continue

        # 日付だけのリンクは、同じ記事のタイトルリンクが別にあるので飛ばす
        if DATE_ONLY_PATTERN.match(raw_text):
            continue

        tag, title = split_tag_and_title(raw_text, source["tags"])
        if source["tag_filter"] and tag != source["tag_filter"]:
            continue
        if not title:
            continue

        matched += 1
        url = clean_url(url, source["drop_query"])
        if url in known or url in seen:
            continue
        seen.add(url)

        m = find_date_near(a)
        pub_dt = None
        if m:
            try:
                pub_dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=JST)
            except ValueError:
                pub_dt = None
        if pub_dt is None:
            pub_dt = datetime.now(JST)

        known_updates[url] = {"title": title, "first_seen": ts}
        new_items.append(
            {
                "title": title,
                "link": url,
                "source": source["name"],
                "pubDate": pub_dt.strftime("%a, %d %b %Y %H:%M:%S %z"),
            }
        )

    if matched == 0:
        print(f"[{source['name']}] 対象の記事が見つかりません。ページ構造が変わった可能性があります。")

    return new_items, known_updates


def main():
    known = load_json(KNOWN_LINKS_FILE, {})
    all_new = []
    all_known_updates = {}
    seen = set()

    for source in LIST_SOURCES:
        try:
            new_items, known_updates = process_source(source, known, seen)
            all_new.extend(new_items)
            all_known_updates.update(known_updates)
            print(f"[{source['name']}] 新着 {len(new_items)}件")
        except Exception as e:
            print(f"[{source['name']}] 取得失敗: {e}")

    merge_new_items(all_new, all_known_updates)
    print(f"一覧ページ解析ソース合計: 新着 {len(all_new)}件")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[ERROR] 予期しないエラー: {e}")
        sys.exit(0)
