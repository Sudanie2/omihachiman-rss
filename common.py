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
}


# ---- ファイル入出力 ----
def load_json(path: Path, default):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---- 時刻 ----
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def now_rfc822() -> str:
    return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S %z")


def parse_pubdate(text):
    """RFC822形式の日時文字列をdatetimeに変換。失敗時は現在時刻。"""
    try:
        dt = parsedate_to_datetime(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
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


def decode_response(resp) -> str:
    """
    文字コードを頑健に判定してテキスト化する。
    サーバー申告の文字コード名がPythonで認識できない場合(例: cp51932)は
    次の候補へ順に切り替える。
    """
    for enc in (resp.encoding, resp.apparent_encoding, "utf-8"):
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
    save_json(KNOWN_LINKS_FILE, known)

    if new_items:
        items = load_json(FEED_ITEMS_FILE, [])
        combined = new_items + items
        combined = combined[:FEED_MAX_ITEMS]
        save_json(FEED_ITEMS_FILE, combined)


def is_known(key: str) -> bool:
    known = load_json(KNOWN_LINKS_FILE, {})
    return key in known
