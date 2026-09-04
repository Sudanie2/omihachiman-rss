#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
近江八幡経済新聞(みんなの経済新聞ネットワーク)の公式RSSを取得し、
市サイトの新着と同じ rss_items.json / rss.xml にマージするスクリプト。

このサイトは公式にRSSを配信しているため、市サイト向けスクリプトのような
ページ巡回やrobots.txt確認は不要。RSSを読んで、未知の記事だけ追加する。
"""

import json
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
import xml.etree.ElementTree as ET

import requests

SOURCE_RSS_URL = "https://omihachiman.keizai.biz/rss.html"
USER_AGENT = "OmihachimanRSSBot/1.0 (+personal monitoring; contact: TS/KURA)"
REQUEST_TIMEOUT_SEC = 15

KNOWN_LINKS_FILE = Path("known_links.json")
FEED_ITEMS_FILE = Path("rss_items.json")
FEED_FILE = Path("rss.xml")
FEED_MAX_ITEMS = 200



def sanitize_xml_text(text: str) -> str:
    """RSS配信元の不正なXML(制御文字・未エスケープの&等)を補正する"""
    # XML 1.0で許可されない制御文字を除去
    text = re.sub(r"[^\x09\x0A\x0D\x20-\uD7FF\uE000-\uFFFD]", "", text)
    # 実体参照でない生の "&" を "&amp;" にエスケープ
    text = re.sub(r"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)", "&amp;", text)
    return text

def load_json(path: Path, default):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def parse_pubdate(text):
    try:
        dt = parsedate_to_datetime(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.now(timezone.utc)


def build_rss(items):
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S %z")

    def esc(s: str) -> str:
        return (
            s.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    entries_xml = []
    for it in items[:FEED_MAX_ITEMS]:
        entries_xml.append(
            f"""    <item>
      <title>{esc(it['title'])}</title>
      <link>{esc(it['link'])}</link>
      <guid isPermaLink="true">{esc(it['link'])}</guid>
      <pubDate>{it['pubDate']}</pubDate>
      <description>{esc(it['description'])}</description>
    </item>"""
        )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>近江八幡市 くらし更新だより(非公式・複数ソース統合)</title>
    <link>https://www.city.omihachiman.lg.jp/index.html</link>
    <description>近江八幡市公式サイトと近江八幡経済新聞の新着をまとめた非公式RSSです。</description>
    <lastBuildDate>{now}</lastBuildDate>
{chr(10).join(entries_xml)}
  </channel>
</rss>
"""


def main():
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(SOURCE_RSS_URL, headers=headers, timeout=REQUEST_TIMEOUT_SEC)
    resp.raise_for_status()

    raw_text = resp.content.decode(resp.encoding or resp.apparent_encoding or "utf-8", errors="replace")
    cleaned_text = sanitize_xml_text(raw_text)
    try:
        root = ET.fromstring(cleaned_text)
    except ET.ParseError as e:
        print(f"RSSのXML解析に失敗しました: {e}")
        return
    channel = root.find("channel")
    if channel is None:
        print("RSSの形式が想定と異なります(channel要素が見つかりません)。中止します。")
        return

    known_links = load_json(KNOWN_LINKS_FILE, {})
    existing_items = load_json(FEED_ITEMS_FILE, [])

    now_iso = datetime.now(timezone.utc).isoformat()
    new_items = []

    for item in channel.findall("item"):
        title_el = item.find("title")
        link_el = item.find("link")
        pubdate_el = item.find("pubDate")

        if title_el is None or link_el is None:
            continue

        title = (title_el.text or "").strip()
        link = (link_el.text or "").strip()
        if not link or link in known_links:
            continue

        pub_dt = parse_pubdate(pubdate_el.text) if pubdate_el is not None and pubdate_el.text else datetime.now(timezone.utc)
        pub_rfc822 = pub_dt.strftime("%a, %d %b %Y %H:%M:%S %z")

        known_links[link] = {"title": title, "first_seen": now_iso}
        new_items.append(
            {
                "title": title,
                "link": link,
                "description": f"新着記事を検出しました: {link}",
                "pubDate": pub_rfc822,
            }
        )

    combined = new_items + existing_items
    combined = combined[:FEED_MAX_ITEMS]

    save_json(FEED_ITEMS_FILE, combined)
    save_json(KNOWN_LINKS_FILE, known_links)
    FEED_FILE.write_text(build_rss(combined), encoding="utf-8")

    print(f"近江八幡経済新聞: 新着 {len(new_items)}件")


if __name__ == "__main__":
    main()
