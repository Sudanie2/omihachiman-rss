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
        "tag_filter": ["お知らせ", "補助金"],
        # 記事リンクと判定するURLパターン(Noneならタグで判定)
        "link_pattern": None,
        # URLから取り除くクエリ(同じ記事が別URL扱いになるのを防ぐ)
        "drop_query": [],
    },
    {
        "name": "ボーダレス・アートミュージアムNO-MA",
        "base": "https://no-ma.jp",
        "url": "https://no-ma.jp/news/",
        "tags": [],
        "tag_filter": None,
        "link_pattern": r"^/20\d{2}/\d{2}/\d{2}/",
        "drop_query": [],
    },
    {
        "name": "近江八幡音楽祭",
        "base": "https://omihachiman-classicfes.jp",
        "url": "https://omihachiman-classicfes.jp/news",
        "tags": [],
        "tag_filter": None,
        "link_pattern": r"/news/\d+\.html",
        "drop_query": [],
    },
    {
        "name": "近江八幡地域勤労者福祉サービスセンター",
        "base": "https://www.workpia-omi-hachiman.jp",
        "url": "https://www.workpia-omi-hachiman.jp/info",
        "tags": [],
        "tag_filter": None,
        "link_pattern": r"/info/detail\?id=\d+",
        "drop_query": [],
    },
    # 八幡山ロープウェー(近江鉄道)
    # 記事URLの形式が一定でない(/ropeway/info/… /file.jsp?id=… 外部リンク)ため、
    # URLの形ではなく「近くに日付があるリンク」を記事とみなす(require_date)。
    {
        "name": "八幡山ロープウェー",
        "base": "https://www.ohmitetudo.co.jp",
        "url": "https://www.ohmitetudo.co.jp/icoico/event/list/?business=%E5%85%AB%E5%B9%A1%E5%B1%B1%E3%83%AD%E3%83%BC%E3%83%97%E3%82%A6%E3%82%A7%E3%83%BC",
        "tags": [],
        "tag_filter": None,
        "link_pattern": None,
        "drop_query": [],
        "require_date": True,
    },
    {
        "name": "八幡山ロープウェー",
        "base": "https://www.ohmitetudo.co.jp",
        "url": "https://www.ohmitetudo.co.jp/info/index.html?office-category-name=%E5%85%AB%E5%B9%A1%E5%B1%B1%E3%83%AD%E3%83%BC%E3%83%97%E3%82%A6%E3%82%A7%E3%83%BC",
        "tags": [],
        "tag_filter": None,
        "link_pattern": None,
        "drop_query": [],
        "require_date": True,
    },
    {
        "name": "八幡山ロープウェー",
        "base": "https://www.ohmitetudo.co.jp",
        "url": "https://www.ohmitetudo.co.jp/news/index.html?office-category-name=%E5%85%AB%E5%B9%A1%E5%B1%B1%E3%83%AD%E3%83%BC%E3%83%97%E3%82%A6%E3%82%A7%E3%83%BC",
        "tags": [],
        "tag_filter": None,
        "link_pattern": None,
        "drop_query": [],
        "require_date": True,
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
    # web滋賀プラスワン(滋賀県の広報サイト)の「近江八幡市」検索結果。
    # 一覧に日付は無いため、初めて見つけた日を掲載日とする。
    # 1つのリンクの中にタイトルと本文の冒頭が両方入っているので、
    # タイトルは title_selector で指定した要素の文字だけを使う。
    {
        "name": "web滋賀プラスワン",
        "base": "https://shigaplusone.jp",
        "url": "https://shigaplusone.jp/?s=%E8%BF%91%E6%B1%9F%E5%85%AB%E5%B9%A1%E5%B8%82",
        "tags": [],
        "tag_filter": None,
        "link_pattern": r"/(?:information/\d{6}_\d+|post/[^/]+)/",
        "drop_query": [],
        "title_selector": "p.result-list-textBlock-title",
        # 初回登録時に日付を指定する記事(一覧に日付が無いため手動で指定)
        "date_overrides": {
            "https://shigaplusone.jp/information/202608_112/": "2026-09-02",  # 「幻の安土城」復元プロジェクト・歴史セミナー
            "https://shigaplusone.jp/information/202608_102/": "2026-09-03",  # VRで安土城を探検しよう!
            "https://shigaplusone.jp/information/202609_015/": "2026-09-18",  # 滋賀で一緒に保育しよ!保育のしごと相談会
        },
        # 8月以前の記事のため登録しない
        "ignore_urls": [
            "https://shigaplusone.jp/information/202608_108/",
            "https://shigaplusone.jp/post/biwapochi/",
            "https://shigaplusone.jp/information/202606_120/",
            "https://shigaplusone.jp/post/shiga-locarion-ofice/",
            "https://shigaplusone.jp/information/202605_111/",
            "https://shigaplusone.jp/post/kokyo_sakamai/",
            "https://shigaplusone.jp/information/202604_208/",
        ],
    },
    # 広報おうみはちまん(マイ広報紙 mykoho.jp)のバックナンバー一覧。
    # ページ上部の「最新号の記事を全部見る」も同じURLを指すため、
    # container_selector でバックナンバーの一覧の中だけを見る。
    # 一覧に日付は無く、タイトルが「広報おうみはちまん 2026年10月号」の形なので、
    # 「年・月」から掲載日(その月の1日)を決める(title_date_pattern)。
    # min_date より前の号は登録しない(過去の号を大量に登録しないため)。
    {
        "name": "広報おうみはちまん",
        "base": "https://mykoho.jp",
        "url": "https://mykoho.jp/lg/252042/577029",
        "tags": [],
        "tag_filter": None,
        "link_pattern": r"/koho/252042/\d+",
        "drop_query": [],
        "container_selector": "#jichitaiBacknum",
        "title_selector": "p",
        "title_date_pattern": r"(20\d{2})年\s*(\d{1,2})月号",
        "min_date": "2026-09-01",
    },
    # webアミンチュ(びわ湖放送のウェブメディア)のタグ「近江八幡市」の記事一覧。
    # 1件ごとの枠(article)の中に、サムネイル用・カテゴリ用・タイトル用など
    # 複数のリンクが入っている。文字のあるタイトルのリンクだけを記事とみなし、
    # 日付は同じ枠の中の日付(2026/08/04 形式)から取る(item_selector / date_selector)。
    # タイトルと日付だけを載せ、要約は載せない。
    {
        "name": "webアミンチュ",
        "base": "https://www.webaminchu.jp",
        "url": "https://www.webaminchu.jp/tag/hachiman/",
        "tags": [],
        "tag_filter": None,
        "link_pattern": r"/news/\d+/",
        "drop_query": [],
        "item_selector": "article.p-entries-item",
        "date_selector": "span.p-entries-day",
        "min_date": "2026-09-01",
    },
]

DATE_PATTERN = re.compile(r"(20\d{2})\s*[.\-/年]\s*(\d{1,2})\s*[.\-/月]\s*(\d{1,2})")
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


def process_source(source, known, seen, session):
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
    try:
        main()
    except Exception as e:
        print(f"[ERROR] 予期しないエラー: {e}")
        sys.exit(0)
