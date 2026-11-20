#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一覧ページ解析型の新着取得(統合版)

RSS配信がなく、「日付 + タイトルリンク」が並ぶ一覧ページを持つサイトを扱う。

対象:
  - 近江八幡商工会議所           : カテゴリタグ「お知らせ」「補助金」の記事のみ
  - 近江八幡市立健康ふれあい公園 : 新着情報の全記事
  - ボーダレス・アートミュージアムNO-MA : お知らせ一覧の全記事
  - 近江八幡音楽祭                 : お知らせの全記事
  - 近江八幡地域勤労者福祉サービスセンター(ワークピア近江八幡) : お知らせの全記事
  - 八幡山ロープウェー(近江鉄道) : イベント・キャンペーン / お知らせ / ニュースリリース
  - web滋賀プラスワン(滋賀県広報) : サイト内検索「近江八幡市」の検索結果(1ページ目)
  - 広報おうみはちまん(マイ広報紙) : 広報紙バックナンバー一覧
  - webアミンチュ(びわ湖放送) : タグ「近江八幡市」の記事一覧(1ページ目)
  - 近江八幡市立図書館(2026年10月のサイト刷新後) : トップページの
      重要なお知らせ / お知らせ / イベント / コーナー展示(おはなし会は対象外)

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

from sources import LIST_SOURCES
from common import (
    run_main,
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


# 「2027年1-3月期」のように、日付ではなく期間を表す表記(日の直後に「月」が続く)は除く
DATE_PATTERN = re.compile(r"(20\d{2})\s*[.\-/年]\s*(\d{1,2})\s*[.\-/月]\s*(\d{1,2})(?!\d|\s*月)")
# 記事ではない案内リンク(ボタン・ページ送り等)の文言
NAVIGATION_TEXTS = {
    "一覧をみる", "一覧を見る", "もっと見る", "詳細はこちら", "こちら",
    "次へ", "前へ", "最初", "最後", "トップ", "もっと読む", "過去一覧を見る",
}

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


def process_issue_page(source, known, seen):
    """
    広報紙の号ごとに見出し(h2)とPDFリンクが並ぶページ用。
    見出し「広報おうみはちまん11月号」ごとに1件とし、リンクは各号の先頭のPDF(全ページ版)にする。
    掲載日は、PDFのファイル名(例: 202611allmihiraki.pdf)の「年・月」から、その月の1日とする。
    """
    rp = get_robot_parser(source["base"])
    if not rp.can_fetch(USER_AGENT, source["url"]):
        print(f"[{source['name']}] robots.txtでブロックされているため中止します。")
        return [], {}

    soup = BeautifulSoup(decode_response(fetch_bytes(source["url"])), "html.parser")
    head_re = re.compile(source["heading_pattern"])
    ts = now_iso()
    new_items = []
    known_updates = {}
    matched = 0

    for h in soup.find_all("h2"):
        title = h.get_text("", strip=True)
        if not head_re.search(title):
            continue
        # 見出しの次に現れる最初のPDFリンクを、その号のリンクとする
        a = None
        for sib in h.find_all_next():
            if sib.name == "h2" and sib is not h:
                break
            if sib.name == "a" and sib.get("href", "").lower().endswith(".pdf"):
                a = sib
                break
        if a is None:
            continue
        matched += 1
        url = urljoin(source["url"], a["href"])
        m = re.search(r"(20\d{2})(0[1-9]|1[0-2])", url.rsplit("/", 1)[-1])
        if not m:
            continue
        pub_dt = datetime(int(m.group(1)), int(m.group(2)), 1, tzinfo=JST)
        if source.get("min_date"):
            y, mo, d = (int(x) for x in source["min_date"].split("-"))
            if pub_dt < datetime(y, mo, d, tzinfo=JST):
                continue
        if url in known or url in seen:
            continue
        seen.add(url)
        known_updates[url] = {"title": title, "first_seen": ts}
        new_items.append(
            {
                "title": title,
                "link": url,
                "source": source["name"],
                "description": "",
                "pubDate": pub_dt.strftime("%a, %d %b %Y %H:%M:%S %z"),
            }
        )

    if matched == 0:
        print(f"[{source['name']}] 対象の記事が見つかりません。ページ構造が変わった可能性があります。")
    return new_items, known_updates


def process_source(source, known, seen, session):
    if source.get("kind") == "issue_pdf":
        return process_issue_page(source, known, seen)
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

    # 一覧の部分だけを見たいサイトでは、その範囲を絞る
    root = soup
    if source.get("container_selector"):
        root = soup.select_one(source["container_selector"]) or soup

    # 記事1件ごとの枠(item_selector)がある場合は、その枠の中から日付を探す
    item_ids = set()
    if source.get("item_selector"):
        item_ids = {id(x) for x in root.select(source["item_selector"])}

    for a in root.find_all("a", href=True):
        url = urljoin(source["url"], a["href"])

        # 記事リンクかどうかの判定
        if link_re and not link_re.search(urlparse(url).path + "?" + (urlparse(url).query or "")):
            continue

        title_selector = source.get("title_selector")
        if title_selector:
            # タイトル専用の要素がある場合は、その文字だけを使う(本文の冒頭を混ぜない)
            title_el = a.select_one(title_selector)
            raw_text = title_el.get_text(" ", strip=True) if title_el else ""
        else:
            raw_text = a.get_text(" ", strip=True)
        if not raw_text:
            continue

        # 日付だけのリンクは、同じ記事のタイトルリンクが別にあるので飛ばす
        if DATE_ONLY_PATTERN.match(raw_text):
            continue
        # 「一覧をみる」等のボタンは記事ではない
        if re.sub(r"\s+", "", raw_text) in NAVIGATION_TEXTS:
            continue

        tag, title = split_tag_and_title(raw_text, source["tags"])
        tag_filter = source["tag_filter"]
        if tag_filter:
            # 単一指定・複数指定のどちらにも対応する
            allowed = [tag_filter] if isinstance(tag_filter, str) else tag_filter
            if tag not in allowed:
                continue
        if not title:
            continue

        matched += 1
        url = clean_url(url, source["drop_query"])
        if source.get("strip_fragment"):
            # 「#…」と末尾の「/」を除く(RSSで取得済みの同じ記事と同一のURLにそろえる)
            url = re.sub(r"/?(#.*)?$", "", url)
        if url in source.get("ignore_urls", []):
            continue
        if url in known or url in seen:
            continue
        seen.add(url)

        m = None
        if item_ids and source.get("date_selector"):
            for parent in a.parents:
                if id(parent) in item_ids:
                    date_el = parent.select_one(source["date_selector"])
                    if date_el:
                        m = DATE_PATTERN.search(date_el.get_text(" ", strip=True))
                    break
        if m is None:
            m = find_date_near(a)
        pub_dt = None
        override = source.get("date_overrides", {}).get(url)
        if override:
            y, mo, d = (int(x) for x in override.split("-"))
            pub_dt = datetime(y, mo, d, tzinfo=JST)
        elif source.get("title_date_pattern"):
            # タイトルの「年・月」から掲載日(その月の1日)を決める
            tm = re.search(source["title_date_pattern"], title)
            if tm:
                pub_dt = datetime(int(tm.group(1)), int(tm.group(2)), 1, tzinfo=JST)
        elif m:
            try:
                pub_dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=JST)
            except ValueError:
                pub_dt = None
        if pub_dt is None:
            # 日付が必須のサイトでは、日付の無いリンク(メニュー等)は記事とみなさない
            if source.get("require_date"):
                seen.discard(url)
                continue
            pub_dt = datetime.now(JST)

        # min_date より前の記事は登録しない
        if source.get("min_date"):
            y, mo, d = (int(x) for x in source["min_date"].split("-"))
            if pub_dt < datetime(y, mo, d, tzinfo=JST):
                continue

        known_updates[url] = {"title": title, "first_seen": ts}
        # 要約は公開しない方針(著作権上の配慮)のため、記事ページを開きに行かない。
        # (以前はここで要約を取得していたが、import漏れにより新着のたびに
        #  エラーとなり、新着が一切登録されない不具合の原因になっていた)
        new_items.append(
            {
                "title": title,
                "link": url,
                "source": source["name"],
                "description": "",
                "pubDate": pub_dt.strftime("%a, %d %b %Y %H:%M:%S %z"),
            }
        )

    if matched == 0:
        print(f"[{source['name']}] 対象の記事が見つかりません。ページ構造が変わった可能性があります。")

    return new_items, known_updates


def main():
    known = load_json(KNOWN_LINKS_FILE, {})
    session = requests.Session()
    all_new = []
    all_known_updates = {}
    seen = set()

    for source in LIST_SOURCES:
        try:
            new_items, known_updates = process_source(source, known, seen, session)
            all_new.extend(new_items)
            all_known_updates.update(known_updates)
            print(f"[{source['name']}] 新着 {len(new_items)}件")
        except Exception as e:
            print(f"[{source['name']}] 取得失敗: {e}")

    merge_new_items(all_new, all_known_updates)
    print(f"一覧ページ解析ソース合計: 新着 {len(all_new)}件")


if __name__ == "__main__":
    run_main(main, "fetch_list_sources.py")
