#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
公式RSSを配信しているサイトからの新着取得(統合版)

対象:
  - 近江八幡経済新聞
  - 号外NET 東近江市・近江八幡市 (タイトルに「近江八幡」を含む記事のみ)
  - 近江八幡市立総合医療センター

1つのサイトで取得に失敗しても、他のサイトの処理は続行する。
"""

import sys
import xml.etree.ElementTree as ET

import requests

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
        # 注意: /rss.html は「RSSについて」の説明ページ(HTML)。
        # 実際のフィードは /rss.xml
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
]


def process_source(source, known):
    """1つのRSSソースを処理し、新着itemsと既知キー更新を返す"""
    resp = fetch_bytes(source["url"])
    raw_text = decode_response(resp)
    cleaned = sanitize_xml_text(raw_text)

    root = ET.fromstring(cleaned)
    channel = root.find("channel")
    if channel is None:
        print(f"[{source['name']}] RSSの形式が想定と異なります(channelなし)。スキップします。")
        return [], {}

    new_items = []
    known_updates = {}
    ts = now_iso()

    for item in channel.findall("item"):
        title_el = item.find("title")
        link_el = item.find("link")
        pubdate_el = item.find("pubDate")

        if title_el is None or link_el is None:
            continue

        title = (title_el.text or "").strip()
        link = (link_el.text or "").strip()

        if not link or link in known or link in known_updates:
            continue
        if source["title_filter"] and source["title_filter"] not in title:
            continue

        pub_dt = (
            parse_pubdate(pubdate_el.text)
            if pubdate_el is not None and pubdate_el.text
            else None
        )
        pub_rfc822 = (
            pub_dt.strftime("%a, %d %b %Y %H:%M:%S %z") if pub_dt else None
        )

        known_updates[link] = {"title": title, "first_seen": ts}
        new_items.append(
            {
                "title": title,
                "link": link,
                "source": source["name"],
                "pubDate": pub_rfc822,
            }
        )

    return new_items, known_updates


def main():
    known = load_json(KNOWN_LINKS_FILE, {})

    all_new = []
    all_known_updates = {}

    for source in RSS_SOURCES:
        try:
            new_items, known_updates = process_source(source, known)
            all_new.extend(new_items)
            all_known_updates.update(known_updates)
            print(f"[{source['name']}] 新着 {len(new_items)}件")
        except Exception as e:
            # 1ソースの失敗で全体を止めない
            print(f"[{source['name']}] 取得失敗: {e}")

    merge_new_items(all_new, all_known_updates)
    print(f"RSSソース合計: 新着 {len(all_new)}件")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[ERROR] 予期しないエラー: {e}")
        sys.exit(0)  # 後続のステップ(他の収集・RSS生成)を止めない
