#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rss.xml 生成スクリプト(最終ステップ)

各収集スクリプトが rss_items.json に貯めた記事を読み込み、
日付の新しい順に並べ替えて rss.xml を1回だけ生成する。

- RSSのタイトル末尾に「（出典：◯◯）」を付与する
- 記事内容に変化がない場合は rss.xml を書き換えない(無駄なコミットを防ぐ)
"""

import hashlib
import json
import sys
from pathlib import Path

from common import (
    load_json,
    now_rfc822,
    parse_pubdate,
    source_from_url,
    FEED_ITEMS_FILE,
    FEED_FILE,
    FEED_MAX_ITEMS,
)

FINGERPRINT_FILE = Path("feed_fingerprint.txt")


def esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_rss(items) -> str:
    entries_xml = []
    for it in items:
        source = it.get("source") or source_from_url(it.get("link", ""))
        title = f"{it['title']}（出典：{source}）"
        guid = it.get("guid") or it["link"]
        is_permalink = "false" if it.get("guid") else "true"
        pubdate = it.get("pubDate") or now_rfc822()

        entries_xml.append(
            f"""    <item>
      <title>{esc(title)}</title>
      <link>{esc(it['link'])}</link>
      <guid isPermaLink="{is_permalink}">{esc(guid)}</guid>
      <pubDate>{pubdate}</pubDate>
      <description>{esc(it.get('description', ''))}</description>
    </item>"""
        )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>近江八幡市 くらし更新だより(非公式・複数ソース統合)</title>
    <link>https://www.city.omihachiman.lg.jp/index.html</link>
    <description>近江八幡市関連の複数サイトの新着をまとめた非公式RSSです。</description>
    <lastBuildDate>{now_rfc822()}</lastBuildDate>
{chr(10).join(entries_xml)}
  </channel>
</rss>
"""


def main():
    items = load_json(FEED_ITEMS_FILE, [])

    # 日付の新しい順に並べ替え
    items.sort(key=lambda it: parse_pubdate(it.get("pubDate", "")), reverse=True)
    items = items[:FEED_MAX_ITEMS]

    # 記事内容に変化がなければ書き換えない
    fingerprint = hashlib.sha256(
        json.dumps(items, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    prev_fingerprint = (
        FINGERPRINT_FILE.read_text(encoding="utf-8").strip()
        if FINGERPRINT_FILE.exists()
        else ""
    )
    if fingerprint == prev_fingerprint and FEED_FILE.exists():
        print("記事に変化がないため rss.xml の更新をスキップします。")
        return

    FEED_FILE.write_text(build_rss(items), encoding="utf-8")
    FINGERPRINT_FILE.write_text(fingerprint, encoding="utf-8")
    print(f"rss.xml を更新しました({len(items)}件)。")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[ERROR] 予期しないエラー: {e}")
        sys.exit(1)  # RSS生成自体の失敗は検知できるようにエラーで落とす
