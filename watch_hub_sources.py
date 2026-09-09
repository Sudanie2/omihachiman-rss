#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ハブページ監視型の新着取得(統合版)

一覧ページ(ハブページ)を巡回し、新しく出現したリンクを新着記事として検出する。

対象:
  - 近江八幡市観光サイト(omi8.com): 9カテゴリの一覧ページ
  - 近江八幡市立図書館: トップページと図書館だより一覧

1つのサイトで取得に失敗しても、他のサイトの処理は続行する。
"""

import re
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from common import (
    fetch_bytes,
    decode_response,
    get_robot_parser,
    load_json,
    merge_new_items,
    extract_page_date,
    extract_page_summary,
    extract_page_title,
    normalize_url,
    now_iso,
    KNOWN_LINKS_FILE,
    REQUEST_INTERVAL_SEC,
    USER_AGENT,
)

HUB_SOURCES = [
    {
        "name": "近江八幡市観光サイト",
        "base": "https://www.omi8.com",
        # 公共性のある情報のみを対象にする。
        # グルメ・土産・宿泊は個別店舗の紹介で、更新日の記載もなく
        # 新着かどうかも判別できないため対象外とする(下のexclude_patternで除外)。
        # 特集・モデルコース・スポット・イベントは、記事ページに日付の記載が無い。
        # 新着順に並ぶ一覧ページ(index_1_0____0___.html)を先に巡回することで、
        # 一覧の並び順をそのまま公開順として保てるようにする。
        "hubs": [
            "/stories/index_1_0____0___.html",      # 特集(新着順)
            "/course/index_1_0____0___.html",       # モデルコース(新着順)
            "/spot/index_1_0____0___.html",         # スポット・体験(新着順)
            "/event/index_1_0____0___.html",        # イベント(新着順)
            "/news/index.html",                     # お知らせ
            "/stories/index_1_2__11__0___.html",    # はちまん観光ライター
            "/pamphlet/index.html",                 # パンフレット
            "/index.html",                          # トップ(Pick up!)
        ],
        # 個別記事とみなすURLパターン
        "detail_pattern": r"/detail[_.]",
        # 個別店舗の紹介は収集しない
        "exclude_pattern": r"^/(restaurant|souvenir|stay|access|favorite)/",
    },
    {
        "name": "近江八幡市立図書館",
        "base": "https://library.city.omihachiman.shiga.jp",
        "hubs": [
            "/",
            "/図書館だより・行事案内/図書館だより",
        ],
        "detail_pattern": r"active_action=bbs_view_main_post.*post_id=\d+",
        "exclude_pattern": None,
        # このサイトの記事詳細ページは、本文(タイトル含む)をJavaScriptで
        # 後から読み込む作りになっており、静的HTMLの時点では中身が空。
        # そのため詳細ページは開かず、一覧ページに表示されているリンクの
        # 文字列そのものを記事タイトルとして使う。
        "title_from_hub_link": True,
    },
]

MAX_NEW_PAGE_FETCH_PER_SOURCE = 60


def is_target_url(url: str, base: str, pattern: re.Pattern, exclude: re.Pattern = None) -> bool:
    parsed = urlparse(url)
    if parsed.netloc and parsed.netloc != urlparse(base).netloc:
        return False
    if exclude and exclude.search(parsed.path):
        return False
    full = parsed.path + ("?" + parsed.query if parsed.query else "")
    return bool(pattern.search(full))


def process_source(source, known, session):
    """1つのハブ監視ソースを処理し、新着itemsと既知キー更新を返す"""
    base = source["base"]
    pattern = re.compile(source["detail_pattern"])
    exclude = re.compile(source["exclude_pattern"]) if source.get("exclude_pattern") else None
    rp = get_robot_parser(base)

    candidate_new = []
    seen_in_run = set()
    hub_link_titles = {}  # url -> 一覧ページ上でのリンク文字列(title_from_hub_link用)

    # 1. ハブページを巡回して新出リンクを収集
    for hub_path in source["hubs"]:
        hub_url = base + hub_path if hub_path.startswith("/") else hub_path
        if not rp.can_fetch(USER_AGENT, hub_url):
            print(f"[{source['name']}] robots.txtでブロック: {hub_url}")
            continue
        try:
            resp = fetch_bytes(hub_url, session)
            html = decode_response(resp)
        except Exception as e:
            print(f"[{source['name']}] ハブページ取得失敗 {hub_url}: {e}")
            continue
        time.sleep(REQUEST_INTERVAL_SEC)

        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            abs_url = normalize_url(urljoin(hub_url, a["href"]))
            if not is_target_url(abs_url, base, pattern, exclude):
                continue
            if abs_url in known or abs_url in seen_in_run:
                continue
            seen_in_run.add(abs_url)
            candidate_new.append(abs_url)
            if source.get("title_from_hub_link"):
                text = re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip()
                if text:
                    hub_link_titles[abs_url] = text

    # 2. 新出リンクを1回だけ開いてタイトルを取得
    new_items = []
    known_updates = {}
    ts = now_iso()
    detected_at = datetime.now(timezone.utc)

    # 一覧ページに並んでいた順(新しい順)を保つ。
    # アルファベット順に並べ替えると、公開順の情報が失われてしまう。
    for i, url in enumerate(candidate_new):
        if i >= MAX_NEW_PAGE_FETCH_PER_SOURCE:
            print(f"[{source['name']}] 上限に達したため残りは次回に持ち越します。")
            break
        if not rp.can_fetch(USER_AGENT, url):
            continue

        if source.get("title_from_hub_link"):
            # 詳細ページはJavaScriptで本文を後から読み込む作りで、
            # 静的HTMLの時点では中身が空(タイトルも取得できない)。
            # 開いても無駄なので、一覧ページ上のリンク文字をそのままタイトルに使う。
            title = hub_link_titles.get(url) or "(タイトル不明)"
            pub = (detected_at - timedelta(seconds=i)).strftime("%a, %d %b %Y %H:%M:%S %z")
            summary = ""
        else:
            try:
                resp = fetch_bytes(url, session)
                html = decode_response(resp)
            except Exception as e:
                print(f"[{source['name']}] 記事取得失敗 {url}: {e}")
                continue
            time.sleep(REQUEST_INTERVAL_SEC)

            soup = BeautifulSoup(html, "html.parser")
            title = extract_page_title(soup)

            # ページに書かれた更新日を優先する。
            # 記載が無いサイト(観光サイトの特集など)は、掲載を確認した日を使う。
            # その際、一覧ページでの並び順(新しい順)を保てるよう、
            # 後ろの記事ほど少しずつ古い時刻にする。
            page_date = extract_page_date(soup)
            if page_date:
                pub = page_date.strftime("%a, %d %b %Y %H:%M:%S %z")
            else:
                pub = (detected_at - timedelta(seconds=i)).strftime("%a, %d %b %Y %H:%M:%S %z")
            summary = extract_page_summary(soup)

        known_updates[url] = {"title": title, "first_seen": ts}
        new_items.append(
            {
                "title": title,
                "link": url,
                "source": source["name"],
                "description": summary,
                "pubDate": pub,
            }
        )

    return new_items, known_updates


def main():
    known = load_json(KNOWN_LINKS_FILE, {})
    session = requests.Session()

    all_new = []
    all_known_updates = {}

    for source in HUB_SOURCES:
        try:
            new_items, known_updates = process_source(source, known, session)
            all_new.extend(new_items)
            all_known_updates.update(known_updates)
            print(f"[{source['name']}] 新着 {len(new_items)}件")
        except Exception as e:
            print(f"[{source['name']}] 取得失敗: {e}")

    merge_new_items(all_new, all_known_updates)
    print(f"ハブ監視ソース合計: 新着 {len(all_new)}件")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[ERROR] 予期しないエラー: {e}")
        sys.exit(0)
