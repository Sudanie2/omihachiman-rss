#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
公式RSSを配信しているサイトからの新着取得(統合版)

対象:
  - 近江八幡経済新聞
  - 号外NET 東近江市・近江八幡市 (タイトルに「近江八幡」を含む記事のみ)
  - 近江八幡市立総合医療センター
  - 近江八幡市立資料館・かわらミュージアム
  - 近江八幡市社会福祉協議会
  - シガブンシンブン(近江八幡市で検索した結果のみ)
  - 安土城考古博物館
  - 安土城考古博物館長のつぶやき(Bloggerブログ / Atom形式)
  - 安土文芸の郷 ニュース＆お知らせ
  - 安土文芸の郷 事業・活動のご報告

配信形式はサイトによって異なる(RSS 2.0 / RSS 1.0(RDF) / Atom)ため、
形式を問わず記事を取り出せるようにしている。
1つのサイトで取得に失敗しても、他のサイトの処理は続行する。
"""

import re
import sys
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup

from common import (
    fetch_bytes,
    decode_response,
    sanitize_xml_text,
    load_json,
    merge_new_items,
    now_iso,
    parse_pubdate,
    KNOWN_LINKS_FILE,
)

RSS_SOURCES = [
    {
        "name": "近江八幡経済新聞",
        # 注意: /rss.html は「RSSについて」の説明ページ(HTML)。実際のフィードは /rss.xml
        "url": "https://omihachiman.keizai.biz/rss.xml",
        "title_filter": None,
    },
    {
        "name": "号外NET",
        "url": "https://higashiomi-omihachiman.goguynet.jp/feed/",
        "title_filter": "近江八幡",  # このキーワードを含むタイトルだけ採用
    },
    {
        "name": "近江八幡市立総合医療センター",
        "url": "https://www.kenkou1.com/news.xml",
        "title_filter": None,
    },
    {
        "name": "近江八幡市立資料館・かわらミュージアム",
        "url": "https://www.omihachiman-shiryoukan-kawara.jp/feed/",
        "title_filter": None,
    },
    {
        "name": "近江八幡市社会福祉協議会",
        "url": "https://ohshakyo.or.jp/files/rss/block614.xml",  # お知らせ
        "title_filter": None,
    },
    {
        "name": "シガブンシンブン(滋賀県文化財保護協会)",
        # 「近江八幡市」で検索した結果をRSS化したもの(WordPressの検索フィード)
        "url": "https://www.shiga-bunkazai.jp/shigabun-shinbun/?s=%E8%BF%91%E6%B1%9F%E5%85%AB%E5%B9%A1%E5%B8%82&feed=rss2",
        "title_filter": None,
    },
    {
        "name": "安土城考古博物館",
        "url": "https://azuchi-museum.or.jp/feed/",
        "title_filter": None,
    },
    {
        "name": "安土城考古博物館長のつぶやき",
        "url": "https://azuchi-museum.blogspot.com/feeds/posts/default",
        "title_filter": None,
    },
    {
        "name": "安土文芸の郷",
        "url": "http://bungei.or.jp/files/rss/block6.xml",  # ニュース＆お知らせ
        "title_filter": None,
    },
    {
        "name": "安土文芸の郷",
        "url": "http://bungei.or.jp/files/rss/block70.xml",  # 事業・活動のご報告
        "title_filter": None,
    },
]

# 記事1件を表す要素名(RSS 2.0/1.0は item、Atomは entry)
ITEM_TAGS = {"item", "entry"}
# 日付を表す要素名の候補
DATE_TAGS = ("pubdate", "date", "published", "updated")
# 本文を表す要素名の候補(タイトルが空の記事で見出しを作るために使う)
BODY_TAGS = ("description", "summary", "content", "encoded")
# 本文から作る見出しの長さ
FALLBACK_TITLE_LENGTH = 60


def local_name(tag) -> str:
    """名前空間付きのタグ名から要素名だけを取り出す({...}item -> item)"""
    return tag.split("}")[-1].lower() if isinstance(tag, str) else ""


def iter_items(root):
    """形式を問わず記事要素を列挙する"""
    for el in root.iter():
        if local_name(el.tag) in ITEM_TAGS:
            yield el


def child_text(item, names):
    for child in item:
        if local_name(child.tag) in names and child.text and child.text.strip():
            return child.text.strip()
    return None


def title_from_body(item) -> str:
    """
    タイトルが空の記事(ブログでよくある)で、本文の冒頭から見出しを作る。
    HTMLタグを取り除き、先頭の一定文字数を使う。
    """
    body = child_text(item, set(BODY_TAGS))
    if not body:
        return ""
    text = BeautifulSoup(body, "html.parser").get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    if len(text) > FALLBACK_TITLE_LENGTH:
        return text[:FALLBACK_TITLE_LENGTH].rstrip() + "…"
    return text


def extract_link(item):
    """リンクを取り出す(Atomは<link href=...>、RSSは<link>本文)"""
    for child in item:
        if local_name(child.tag) == "link":
            href = child.get("href")
            if href and href.strip():
                return href.strip()
            if child.text and child.text.strip():
                return child.text.strip()
    # 最後の手段として RDF の about 属性
    for key, value in item.attrib.items():
        if local_name(key) == "about" and value.strip():
            return value.strip()
    return None


def process_source(source, known, seen_links):
    """1つのRSSソースを処理し、新着itemsと既知キー更新を返す"""
    resp = fetch_bytes(source["url"])
    raw_text = decode_response(resp)
    cleaned = sanitize_xml_text(raw_text)

    root = ET.fromstring(cleaned)

    new_items = []
    known_updates = {}
    ts = now_iso()
    found = 0

    for item in iter_items(root):
        title = child_text(item, {"title"}) or title_from_body(item)
        link = extract_link(item)
        if not title or not link:
            continue
        found += 1

        if link in known or link in seen_links:
            continue
        if source["title_filter"] and source["title_filter"] not in title:
            continue

        date_text = child_text(item, set(DATE_TAGS))
        pub_rfc822 = (
            parse_pubdate(date_text).strftime("%a, %d %b %Y %H:%M:%S %z")
            if date_text
            else None
        )

        seen_links.add(link)
        known_updates[link] = {"title": title, "first_seen": ts}
        new_items.append(
            {
                "title": title,
                "link": link,
                "source": source["name"],
                "pubDate": pub_rfc822,
            }
        )

    if found == 0:
        print(f"[{source['name']}] 記事が見つかりません({source['url']})。配信形式が想定と異なる可能性があります。")

    return new_items, known_updates


def main():
    known = load_json(KNOWN_LINKS_FILE, {})

    all_new = []
    all_known_updates = {}
    seen_links = set()

    for source in RSS_SOURCES:
        try:
            new_items, known_updates = process_source(source, known, seen_links)
            all_new.extend(new_items)
            all_known_updates.update(known_updates)
            print(f"[{source['name']}] 新着 {len(new_items)}件 ({source['url']})")
        except Exception as e:
            # 1ソースの失敗で全体を止めない
            print(f"[{source['name']}] 取得失敗 ({source['url']}): {e}")

    merge_new_items(all_new, all_known_updates)
    print(f"RSSソース合計: 新着 {len(all_new)}件")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[ERROR] 予期しないエラー: {e}")
        sys.exit(0)
