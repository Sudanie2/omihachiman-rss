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
from datetime import datetime, timezone
from pathlib import Path

from common import (
    load_json,
    save_json,
    now_rfc822,
    parse_pubdate,
    FEED_ITEMS_FILE,
    FEED_FILE,
    FEED_MAX_ITEMS,
    FEED_MIN_DATE,
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
        title = it["title"]
        guid = it.get("guid") or it["link"]
        is_permalink = "false" if it.get("guid") else "true"
        pubdate = it.get("pubDate") or now_rfc822()

        # 中身のある説明文がある場合のみ description を出力する
        desc = (it.get("description") or "").strip()
        desc_xml = f"\n      <description>{esc(desc)}</description>" if desc else ""

        entries_xml.append(
            f"""    <item>
      <title>{esc(title)}</title>
      <link>{esc(it['link'])}</link>
      <guid isPermaLink="{is_permalink}">{esc(guid)}</guid>
      <pubDate>{pubdate}</pubDate>{desc_xml}
    </item>"""
        )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>近江八幡市.com</title>
    <link>https://www.city.omihachiman.lg.jp/index.html</link>
    <description>近江八幡市に関する各種公式サイトの新着情報をまとめた非公式RSSです。</description>
    <lastBuildDate>{now_rfc822()}</lastBuildDate>
{chr(10).join(entries_xml)}
  </channel>
</rss>
"""


def item_date(it):
    """
    並べ替え用の日付。日付が無い・壊れている記事は現在時刻とみなさず、
    最も古い扱いにする(誤って最新記事として先頭に出るのを防ぐ)。
    """
    text = (it.get("pubDate") or "").strip()
    if not text:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    dt = parse_pubdate(text)
    # parse_pubdateは解釈できない場合に現在時刻を返すため、その場合も最古扱いにする
    if abs((dt - datetime.now(timezone.utc)).total_seconds()) < 5:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    return dt


def report_sizes():
    """
    公開ファイルの容量を報告する。
    GitHub Pagesの制限(リポジトリ1GB)に対する余裕を毎回確認できるようにする。
    """
    targets = ["rss.xml", "rss_items.json", "known_links.json", "hubs.json", "index.html"]
    total = 0
    parts = []
    for name in targets:
        path = Path(name)
        if path.exists():
            kb = path.stat().st_size / 1024
            total += kb
            parts.append(f"{name} {kb:.0f}KB")
    print("ファイル容量: " + " / ".join(parts) + f" (合計 {total/1024:.1f}MB)")

    # 目安として合計50MBを超えたら知らせる(1GB上限に対して十分手前)
    if total / 1024 > 50:
        print("【注意】公開ファイルの合計が50MBを超えました。GitHubの1GB上限に備え、"
              "known_links.jsonの整理を検討してください。")


def main():
    items = load_json(FEED_ITEMS_FILE, [])
    before = len(items)

    # 掲載対象期間より古い記事(および日付不明の記事)を取り除く
    items = [it for it in items if item_date(it) >= FEED_MIN_DATE]
    removed = before - len(items)

    # 日付の新しい順に並べ替え
    items.sort(key=item_date, reverse=True)
    items = items[:FEED_MAX_ITEMS]

    # 除外した分をデータ側にも反映する(次回以降の処理を軽くする)
    if removed or before > len(items):
        save_json(FEED_ITEMS_FILE, items)
        print(f"掲載対象外({FEED_MIN_DATE.strftime('%Y年%m月%d日')}より前)の記事 {removed}件を整理しました。")

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
        report_sizes()
        return

    FEED_FILE.write_text(build_rss(items), encoding="utf-8")
    FINGERPRINT_FILE.write_text(fingerprint, encoding="utf-8")
    print(f"rss.xml を更新しました({len(items)}件)。")
    report_sizes()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[ERROR] 予期しないエラー: {e}")
        sys.exit(1)  # RSS生成自体の失敗は検知できるようにエラーで落とす
