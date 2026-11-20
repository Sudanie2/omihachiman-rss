#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rss.xml 生成スクリプト(最終ステップ)

各収集スクリプトが rss_items.json に貯めた記事を読み込み、
日付の新しい順に並べ替えて rss.xml を1回だけ生成する。

- 掲載対象外の記事の除去・日付の補正・重複の整理を行ってから出力する
- サイトマップ(sitemap.xml)も、記事が更新された時に作り直す
- 記事内容に変化がない場合は rss.xml を書き換えない(無駄なコミットを防ぐ)
"""

import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from exclusions import is_excluded_city_item
from common import (
    dateless_baselines,
    description_allowed,
    is_dateless_backlog,
    is_excluded_link,
    load_json,
    save_json,
    now_rfc822,
    parse_pubdate_or_none,
    FEED_ITEMS_FILE,
    FEED_FILE,
    KNOWN_LINKS_FILE,
    FEED_MAX_ITEMS,
    FEED_MIN_DATE,
)

FINGERPRINT_FILE = Path("feed_fingerprint.txt")
SITEMAP_FILE = Path("sitemap.xml")
SITE_URL = "https://sudanie2.github.io/omihachiman-rss/"
FEED_URL = SITE_URL + "rss.xml"
# rss.xml の書式(ヘッダー部分など)を変えたときに上げる。記事に変化が無くても
# 次回の実行で rss.xml を作り直すための印(記事の識別子・日付は変わらない)。
FEED_FORMAT_VERSION = "2"


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
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>近江八幡市.com</title>
    <link>https://www.city.omihachiman.lg.jp/index.html</link>
    <atom:link href="{FEED_URL}" rel="self" type="application/rss+xml"/>
    <description>近江八幡市に関する各種公式サイトの新着情報をまとめた非公式RSSです。</description>
    <language>ja</language>
    <lastBuildDate>{now_rfc822()}</lastBuildDate>
{chr(10).join(entries_xml)}
  </channel>
</rss>
"""


EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def item_date(it):
    """
    並べ替え用の日付。日付が無い・解釈できない記事は最も古い扱いにする
    (誤って最新記事として先頭に出るのを防ぐ)。
    """
    return parse_pubdate_or_none(it.get("pubDate")) or EPOCH


def clamp_future_dates(items, known):
    """
    未来の日付(明日より先)になっている記事の日付を、最初に見つけた日に直す。
    イベントの開催日や、年・月が混ざった題名を掲載日と取り違えた場合に、
    「2099年」のような日付が公開ページに出るのを防ぐ。
    最初に見つけた日(known_links.json の first_seen)が分からない場合は、今日の日付にする。
    直した日付は rss_items.json にも保存されるので、毎回変わることはない。
    """
    limit = datetime.now(timezone.utc) + timedelta(days=1)
    jst = timezone(timedelta(hours=9))
    fixed = 0
    for it in items:
        dt = parse_pubdate_or_none(it.get("pubDate"))
        if dt is None or dt <= limit:
            continue
        rec = known.get(it.get("guid") or "") or known.get(it.get("link") or "") or {}
        first_seen = rec.get("first_seen") if isinstance(rec, dict) else None
        try:
            base = datetime.fromisoformat(first_seen) if first_seen else datetime.now(timezone.utc)
        except ValueError:
            base = datetime.now(timezone.utc)
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)
        local = base.astimezone(jst)
        it["pubDate"] = datetime(local.year, local.month, local.day, tzinfo=jst).strftime(
            "%a, %d %b %Y %H:%M:%S %z"
        )
        fixed += 1
    return fixed


def dedupe(items, known=None):
    """
    同じ記事が複数のURLで掲載されている場合(市サイトは組織別・分野別・
    利用者別の複数の階層に、別々のページ番号で同じ内容を載せることがある)、
    1件にまとめる。タイトルと出典が同じものを同一とみなす。

    どのURLを残すかの規則:
      1. 日付が新しい方を残す(本当に更新された場合は、その更新を伝える)
      2. 日付が同じなら、当システムが先に検知した方(=既に読者へ届けた方)を残す

    2 が重要。以前は「短いURLを残す」規則だったため、後日になって同じ記事の
    別URL版が見つかると、代表URLが入れ替わってRSSの識別子(guid)が変わり、
    Feedly等では古い記事が「新着」として再配信されてしまっていた。
    (実例: 8月31日付の記事が、9月22日に分野別ページの複製が見つかった
     ことで、Feedlyに9月22日の新着として表示された)
    """
    known = known or {}

    def first_seen(it):
        rec = known.get(it.get("link", "")) or {}
        # 検知記録が無いものは最も遅く見つかった扱いにする
        return rec.get("first_seen") or "9999"

    best = {}
    order = []
    for it in items:
        key = (
            re.sub(r"\s+", "", it.get("title", "")),
            it.get("source", ""),
        )
        if key not in best:
            best[key] = it
            order.append(key)
            continue
        current = best[key]
        if item_date(it) > item_date(current):
            best[key] = it
        elif item_date(it) == item_date(current):
            if first_seen(it) < first_seen(current):
                best[key] = it
            elif first_seen(it) == first_seen(current) and len(it.get("link", "")) < len(current.get("link", "")):
                best[key] = it
    return [best[k] for k in order]


def build_sitemap(lastmod: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{SITE_URL}</loc>
    <lastmod>{lastmod}</lastmod>
    <priority>1.0</priority>
  </url>
</urlset>
"""


def report_sizes():
    """
    公開ファイルの容量を報告する。
    GitHub Pagesの制限(リポジトリ1GB)に対する余裕を毎回確認できるようにする。
    """
    targets = ["rss.xml", "rss_items.json", "known_links.json", "hubs.json", "index.html", "sitemap.xml"]
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
    known = load_json(KNOWN_LINKS_FILE, {})

    # 要約(description)は、許可された出典(事実情報を当サイトが書いたもの)以外は
    # 公開しない。データファイル自体もリポジトリで公開されているため、
    # rss_items.json からも取り除く。
    stripped = 0
    for it in items:
        if it.get("description") and not description_allowed(it.get("source", "")):
            it["description"] = ""
            stripped += 1

    # 掲載対象外のURL(個別店舗の紹介など)を取り除く
    items = [it for it in items if not is_excluded_link(it.get("link", ""))]
    # 市公式サイトの入札・調達/職員採用/任用職員に関する記事を取り除く
    items = [it for it in items if not is_excluded_city_item(it)]
    excluded = before - len(items)

    # 日付を持たないサイトの、初回巡回で見つかった過去記事(公開日不明)を取り除く
    baselines = dateless_baselines(known)
    kept = [it for it in items if not is_dateless_backlog(it.get("link", ""), known, baselines)]
    backlog = len(items) - len(kept)
    items = kept

    # 未来の日付になっている記事の日付を直す
    future_fixed = clamp_future_dates(items, known)
    if future_fixed:
        print(f"未来の日付の記事 {future_fixed}件 の日付を、最初に見つけた日に直しました。")

    # 掲載対象期間より古い記事(および日付不明の記事)を取り除く
    kept = [it for it in items if item_date(it) >= FEED_MIN_DATE]
    removed = len(items) - len(kept)
    items = kept

    # 同じ内容の重複をまとめる
    deduped = dedupe(items, known)
    duplicates = len(items) - len(deduped)
    items = deduped

    # 日付の新しい順に並べ替え
    items.sort(key=item_date, reverse=True)

    # 整理結果をデータ側にも反映する(次回以降の処理を軽くする)
    if before != len(items) or stripped or future_fixed:
        save_json(FEED_ITEMS_FILE, items)
        if stripped:
            print(f"要約(元記事の文章)を {stripped}件 取り除きました。")
        print(
            f"整理: 期間外 {removed}件 / 対象外 {excluded}件 / 日付不明の過去記事 {backlog}件 / 重複 {duplicates}件 "
            f"を除きました(残り {len(items)}件)。"
        )

    # 記事内容に変化がなければ書き換えない
    fingerprint = hashlib.sha256(
        (FEED_FORMAT_VERSION + json.dumps(items, ensure_ascii=False, sort_keys=True)).encode("utf-8")
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

    FEED_FILE.write_text(build_rss(items[:FEED_MAX_ITEMS]), encoding="utf-8")
    FINGERPRINT_FILE.write_text(fingerprint, encoding="utf-8")
    jst = timezone(timedelta(hours=9))
    SITEMAP_FILE.write_text(build_sitemap(datetime.now(jst).strftime("%Y-%m-%dT%H:%M:%S+09:00")), encoding="utf-8")
    print(f"rss.xml を更新しました({len(items)}件)。")
    report_sizes()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[ERROR] 予期しないエラー: {e}")
        sys.exit(1)  # RSS生成自体の失敗は検知できるようにエラーで落とす
