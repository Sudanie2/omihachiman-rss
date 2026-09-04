#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
共通処理モジュール

全ての収集スクリプトが使う処理をここに集約する。
文字コード・XML補正・重複管理などの修正は、このファイル1箇所で済む。
"""

import json
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse
import urllib.robotparser

import requests

# ---- 定数 ----
USER_AGENT = "OmihachimanRSSBot/1.0 (+personal monitoring; contact: TS/KURA)"
REQUEST_TIMEOUT_SEC = 15
REQUEST_INTERVAL_SEC = 1.0
JST = timezone(timedelta(hours=9))

KNOWN_LINKS_FILE = Path("known_links.json")
FEED_ITEMS_FILE = Path("rss_items.json")
FEED_FILE = Path("rss.xml")
FEED_MAX_ITEMS = 200

# URLのドメインから出典名を引くための対応表
SOURCE_BY_HOST = {
    "www.city.omihachiman.lg.jp": "近江八幡市公式サイト",
    "omihachiman.keizai.biz": "近江八幡経済新聞",
    "higashiomi-omihachiman.goguynet.jp": "号外NET",
    "www.omi8.com": "近江八幡市観光サイト",
    "www.kenkou1.com": "近江八幡市立総合医療センター",
    "www.pref.shiga.lg.jp": "近江八幡警察署(滋賀県警)",
    "library.city.omihachiman.shiga.jp": "近江八幡市立図書館",
    "bungei.or.jp": "安土文芸の郷",
    "8cci.com": "近江八幡商工会議所",
    "www.8cci.com": "近江八幡商工会議所",
    "www.bungei.or.jp": "安土文芸の郷",
}


# ---- ファイル入出力 ----
def load_json(path: Path, default):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path: Path, data, compact: bool = False):
    """
    JSONを保存する。
    compact=True の場合は改行・空白を省いて保存する。
    件数が増え続けるファイル(known_links.json)はGit履歴の肥大を抑えるため
    compactで保存する。
    """
    with open(path, "w", encoding="utf-8") as f:
        if compact:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(data, f, ensure_ascii=False, indent=2)


# ---- 時刻 ----
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def now_rfc822() -> str:
    return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S %z")


def parse_pubdate(text):
    """
    日時文字列をdatetimeに変換する。
    RSS 2.0のRFC822形式("Thu, 11 Sep 2025 00:00:00 +0900")と、
    RSS 1.0/AtomのISO8601形式("2025-09-11T00:00:00+09:00")の両方に対応。
    失敗時は現在時刻を返す。
    """
    if not text:
        return datetime.now(timezone.utc)
    text = text.strip()

    try:
        dt = parsedate_to_datetime(text)
        if dt is not None:
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        pass

    try:
        iso = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        pass

    return datetime.now(timezone.utc)


# ---- HTTP ----
# 一部の自治体サイト等は、ブラウザが必ず送るヘッダー(Accept等)が無いアクセスを
# 機械的に遮断することがあるため、標準的なヘッダーを補って送信する。
DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.7,en;q=0.3",
}


def fetch_bytes(url: str, session=None):
    getter = session.get if session else requests.get
    resp = getter(url, headers=DEFAULT_HEADERS, timeout=REQUEST_TIMEOUT_SEC)
    resp.raise_for_status()
    return resp


# Pythonが直接扱えない文字コード名の読み替え表
ENCODING_ALIASES = {
    "cp51932": "euc_jp",
    "x-sjis": "cp932",
    "shift-jis": "shift_jis",
    "x-euc-jp": "euc_jp",
    "windows-31j": "cp932",
}


def _normalize_encoding(enc):
    if not enc:
        return None
    return ENCODING_ALIASES.get(enc.strip().lower(), enc)


def decode_response(resp) -> str:
    """
    文字コードを正しく判定してテキスト化する。

    注意: requestsは、応答ヘッダーに文字コードの指定が無いHTMLを
    一律「ISO-8859-1(欧文用)」とみなすため、resp.encodingをそのまま
    信用すると日本語が文字化けする。そこで以下の順に候補を試す。
      1. 応答ヘッダーで文字コードが明示されている場合のみ、その指定
      2. HTML/XML内の <meta charset> 等の宣言
      3. 中身から推定した文字コード
      4. utf-8
    """
    candidates = []

    content_type = resp.headers.get("Content-Type", "").lower()
    if "charset=" in content_type:
        candidates.append(resp.encoding)

    # HTML/XMLの冒頭にある文字コード宣言を読む
    head = resp.content[:4096]
    m = re.search(rb"""charset=["']?([\w\-]+)""", head, re.IGNORECASE)
    if m:
        candidates.append(m.group(1).decode("ascii", errors="ignore"))

    candidates.append(resp.apparent_encoding)
    candidates.append("utf-8")

    for enc in candidates:
        enc = _normalize_encoding(enc)
        if not enc:
            continue
        try:
            return resp.content.decode(enc, errors="replace")
        except (LookupError, TypeError):
            continue

    return resp.content.decode("utf-8", errors="replace")


def fetch_text(url: str, session=None) -> str:
    resp = fetch_bytes(url, session)
    return decode_response(resp)


# ---- XML補正 ----
def sanitize_xml_text(text: str) -> str:
    """RSS配信元の不正なXML(制御文字・未エスケープの&等)を補正する"""
    text = re.sub(r"[^\x09\x0A\x0D\x20-\uD7FF\uE000-\uFFFD]", "", text)
    text = re.sub(r"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)", "&amp;", text)
    return text


# ---- robots.txt ----
def get_robot_parser(base_url: str):
    """
    robots.txtを取得する。Pythonの標準機能はUser-Agentを名乗らず
    アクセスしてサイト側に弾かれることがあるため、requestsで明示的に取得する。
    取得できない(404等)場合は「制限なし」として扱う。
    """
    rp = urllib.robotparser.RobotFileParser()
    try:
        resp = requests.get(
            f"{base_url}/robots.txt",
            headers=DEFAULT_HEADERS,
            timeout=REQUEST_TIMEOUT_SEC,
        )
        if resp.status_code == 200:
            rp.parse(decode_response(resp).splitlines())
        else:
            rp.parse([])
    except Exception:
        rp.parse([])
    return rp


# ---- ページタイトルの抽出 ----
# タイトル末尾に付くサイト名を除去するパターン
TITLE_STRIP_PATTERNS = [
    r"\s*[|｜\-–—/／]\s*【公式】近江八幡市観光情報サイト\s*$",
    r"\s*[|｜\-–—/／]\s*近江八幡市観光情報サイト\s*$",
    r"\s*[|｜\-–—/／]\s*近江八幡市立図書館\s*$",
    r"\s*[|｜\-–—/／]\s*滋賀県警\s*$",
    r"\s*[|｜\-–—/／]\s*近江八幡市立総合医療センター\s*$",
    r"\s*[|｜\-–—/／]\s*近江八幡市\s*$",
    r"\s*[|｜\-–—/／]\s*新着情報\s*$",
    # 「記事名｜カテゴリ｜サイト名」形式のカテゴリ部分
    r"\s*[|｜]\s*(イベント|スポット・体験|スポット体験|グルメ|特集|モデルコース|土産|お土産|宿泊|アクセス|お気に入り|観光情報)\s*$",
]

# これ自体が出てきた場合は「記事名ではなくサイト名」とみなし、次の候補を探す
REJECT_TITLES = {
    "近江八幡市公式観光サイト",
    "【公式】近江八幡市観光情報サイト",
    "近江八幡市観光情報サイト",
    "近江八幡市立図書館",
    "近江八幡市",
    "滋賀県警",
    "近江八幡市立総合医療センター",
    "新着情報",
    "",
}


def _clean_title(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    # サイト名の除去は繰り返し適用する(「記事名｜カテゴリ｜サイト名」への対応)
    for _ in range(3):
        before = text
        for pattern in TITLE_STRIP_PATTERNS:
            text = re.sub(pattern, "", text).strip()
        if text == before:
            break
    return text


def extract_page_title(soup) -> str:
    """
    ページから記事タイトルを取り出す。

    サイトによって記事名の置き場所が異なる(h1がサイトロゴになっている等)ため、
    og:title → title → h1 → h2 の順に候補を試し、
    サイト名そのものだった場合は次の候補へ進む。
    """
    candidates = []

    for prop in ("og:title", "twitter:title"):
        el = soup.find("meta", attrs={"property": prop}) or soup.find(
            "meta", attrs={"name": prop}
        )
        if el and el.get("content"):
            candidates.append(el["content"])

    if soup.title and soup.title.string:
        candidates.append(soup.title.string)

    for sel in ("h1", "h2"):
        el = soup.select_one(sel)
        if el:
            candidates.append(el.get_text(strip=True))

    for raw in candidates:
        cleaned = _clean_title(raw)
        if cleaned and cleaned not in REJECT_TITLES:
            return cleaned

    return "(タイトル不明)"
# ---- URL ----
def normalize_url(url: str) -> str:
    return url.split("#")[0]


def source_from_url(url: str) -> str:
    host = urlparse(url).netloc
    return SOURCE_BY_HOST.get(host, host or "不明")


# ---- 記事の登録 ----
def merge_new_items(new_items, known_updates):
    """
    新着記事(new_items)を rss_items.json の先頭に追加し、
    known_links.json に既知キー(known_updates)を追記する。

    new_items: [{"title","link","source","pubDate","description"}, ...]
    known_updates: {キー文字列: {"title":..., "first_seen":...}, ...}
    """
    if not new_items and not known_updates:
        return

    known = load_json(KNOWN_LINKS_FILE, {})
    known.update(known_updates)
    save_json(KNOWN_LINKS_FILE, known, compact=True)

    if new_items:
        items = load_json(FEED_ITEMS_FILE, [])
        combined = new_items + items
        combined = combined[:FEED_MAX_ITEMS]
        save_json(FEED_ITEMS_FILE, combined)


def is_known(key: str) -> bool:
    known = load_json(KNOWN_LINKS_FILE, {})
    return key in known
