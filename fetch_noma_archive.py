#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NO-MA ARCHIVE(no-maarchive.com) 展覧会情報の取得

各項目は以下のように、カテゴリ・会期・展覧会名がタグで明確に分かれた
構造になっている(ユーザー提供のページソースで確認済み)。

  <div class="cat">展覧会</div>
  <div class="date">2026.1.24~3.15</div>
  <dd><h5>第22回滋賀県施設・学校合同企画展 ing…</h5></dd>

会期は「開始日～終了日」(単一または複数期)の形式で、書式も複数ある
(例: "2026.1.24~3.15" / "2025年10月18日（土）－2026年1月12日（月・祝）" /
"第Ⅰ期 2025年5月24日（土）～7月21日（月・祝）/ 第Ⅱ期 …")。
そのため、会期テキスト中で最初に現れる日付(=開始日)を記事の日付として使う。
"""

import re
import sys
from datetime import datetime

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

BASE_URL = "https://no-maarchive.com"
PAGE_URL = f"{BASE_URL}/?contents=contents-exhibition"
SOURCE_NAME = "NO-MA ARCHIVE(展覧会情報)"

# 会期テキストから最初の日付(開始日)を取り出す
DATE_PATTERN = re.compile(r"(20\d{2})\s*[.\-/年]\s*(\d{1,2})\s*[.\-/月]\s*(\d{1,2})")


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
    total = 0
    skipped_no_date = 0

    seen = set()
    section = soup.select_one("section#ar_list") or soup
    # ナビゲーションタブ等、展覧会項目ではない<li>も同じ構造にマッチするため、
    # 実際の展覧会タイトル(dd > h5)を持つものだけに絞る
    items = [li for li in section.select("ul > li:has(a[href])") if li.select_one("dd h5")]

    for li in items:
        a = li.find("a", href=True)
        title_el = li.select_one("dd h5")

        total += 1
        url = normalize_url(a["href"])
        if url in known or url in seen:
            continue
        seen.add(url)

        title = re.sub(r"\s+", " ", title_el.get_text(" ", strip=True)).strip()
        if not title:
            continue

        date_el = li.select_one("div.date")
        date_text = date_el.get_text(" ", strip=True) if date_el else ""
        m = DATE_PATTERN.search(date_text)
        if not m:
            skipped_no_date += 1
            continue
        try:
            pub_dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=JST)
        except ValueError:
            skipped_no_date += 1
            continue

        cat_el = li.select_one("div.cat")
        category = cat_el.get_text(strip=True) if cat_el else ""
        summary = f"会期: {date_text}" if date_text else ""

        known_updates[url] = {"title": title, "first_seen": ts}
        new_items.append(
            {
                "title": title,
                "link": url,
                "source": f"{SOURCE_NAME}" + (f"・{category}" if category and category != "展覧会" else ""),
                "description": summary,
                "pubDate": pub_dt.strftime("%a, %d %b %Y %H:%M:%S %z"),
            }
        )

    if skipped_no_date:
        print(f"[{SOURCE_NAME}] 会期の日付が読めない項目 {skipped_no_date}件は掲載対象外としました。")

    print(f"[{SOURCE_NAME}] 掲載中 {total}件 / 新着 {len(new_items)}件")
    merge_new_items(new_items, known_updates)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[ERROR] 予期しないエラー: {e}")
        sys.exit(0)
