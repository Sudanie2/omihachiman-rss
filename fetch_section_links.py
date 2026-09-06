#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ページ内の特定範囲にあるリンクを新着として取得する(統合版)

「一覧」の体裁になっておらず、ページの一区画にイベント告知(PDF・画像・別ページ)が
並べられているタイプのサイトを扱う。

対象:
  - 安土学区まちづくり協議会
      index.html の「まち協．お知らせ」〜「連絡事項2」の間に置かれた
      イベント情報(PDF・画像・リンク)を新着として拾う。

設計方針:
  - クラス名(auto-style93等)やファイル名を直接指定しない。
    これらはページ編集や年度替わりで変わるため、指定すると動かなくなる。
  - 範囲内に「新しいリンクが出現したか」だけを見る(本文の変更は追わない)。
    広報誌は 2026-09-wa.pdf のように毎月ファイル名が変わるので確実に検知できる。
  - タイトルはリンク文字→画像の代替テキスト→近くの文字→ファイル名 の順に探す。
"""

import re
import sys
from datetime import datetime
from urllib.parse import urljoin, urlparse, unquote

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

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

SECTION_SOURCES = [
    {
        "name": "安土学区まちづくり協議会",
        "base": "https://www.zd.ztv.ne.jp",
        "url": "https://www.zd.ztv.ne.jp/azuchi-cc/index.html",
        # この文字列の間にあるリンクを対象にする(表記ゆれに備え候補を複数持つ)
        "start_markers": ["まち協．お知らせ", "まち協.お知らせ", "まち協お知らせ"],
        "end_markers": ["連絡事項2", "連絡事項２"],
        # 対象とする拡張子(イベント告知は画像やPDFの場合もある)
        "allowed_ext": [".pdf", ".html", ".htm", ".jpg", ".jpeg", ".png", ".gif", ""],
    },
]

# タイトルが取れない時にファイル名から作る際、除去する記号
FILENAME_CLEAN = re.compile(r"[-_]+")


def compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def find_section_links(soup, source):
    """
    開始・終了の目印の間にあるリンクを、文書の並び順に沿って集める。
    目印がタグで分割されていても拾えるよう、空白を除いた文字列で判定する。
    """
    start_pos = None
    end_pos = None
    links = []  # (出現位置, aタグ)

    starts = [compact(m) for m in source["start_markers"]]
    ends = [compact(m) for m in source["end_markers"]]

    buffer = ""  # ここまでに現れた文字(空白除去)
    for pos, node in enumerate(soup.descendants):
        if isinstance(node, NavigableString):
            buffer += compact(str(node))
            if start_pos is None and any(m and m in buffer for m in starts):
                start_pos = pos
                buffer = ""
            elif start_pos is not None and end_pos is None and any(m and m in buffer for m in ends):
                end_pos = pos
                break
        elif isinstance(node, Tag) and node.name == "a" and node.get("href"):
            if start_pos is not None and end_pos is None:
                links.append(node)

    if start_pos is None:
        print(f"[{source['name']}] 開始の目印が見つかりません。ページ構造が変わった可能性があります。")
        return []
    if end_pos is None:
        print(f"[{source['name']}] 終了の目印が見つかりませんでした。開始位置以降を対象にします。")

    return links


def title_from_filename(url: str) -> str:
    """
    文字情報が一切ないリンク(画像だけの告知など)の見出しをファイル名から作る。
    中身は分からないので、リンク先を開いて確認してもらう前提の表記にする。
    """
    name = unquote(urlparse(url).path.rsplit("/", 1)[-1])
    return f"お知らせ（{name}）" if name else "お知らせ"


def extract_title(a_tag, url: str) -> str:
    """リンク文字 → 画像の代替テキスト → 近くの文字 → ファイル名 の順に探す"""
    text = a_tag.get_text(" ", strip=True)
    if text:
        return re.sub(r"\s+", " ", text).strip()

    for img in a_tag.find_all("img"):
        for attr in ("alt", "title"):
            value = (img.get(attr) or "").strip()
            if value:
                return value

    # 同じ表のマス目など、近い範囲にある文字を探す
    node = a_tag
    for _ in range(3):
        node = node.parent
        if node is None:
            break
        # 他のリンクを含む要素まで遡ると、別の告知の文字を拾ってしまう
        if len(node.find_all("a")) > 1:
            break
        near = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
        if near and len(near) <= 60:
            return near

    return title_from_filename(url)


def process_source(source, known, seen):
    rp = get_robot_parser(source["base"])
    if not rp.can_fetch(USER_AGENT, source["url"]):
        print(f"[{source['name']}] robots.txtでブロックされているため中止します。")
        return [], {}

    resp = fetch_bytes(source["url"])
    html = decode_response(resp)
    soup = BeautifulSoup(html, "html.parser")

    links = find_section_links(soup, source)
    ts = now_iso()
    ts_rfc822 = datetime.now(JST).strftime("%a, %d %b %Y %H:%M:%S %z")

    new_items = []
    known_updates = {}
    found = 0

    for a in links:
        url = normalize_url(urljoin(source["url"], a["href"]))
        ext = re.search(r"(\.[a-zA-Z0-9]+)$", urlparse(url).path)
        ext = ext.group(1).lower() if ext else ""
        if ext not in source["allowed_ext"]:
            continue

        found += 1
        if url in known or url in seen:
            continue
        seen.add(url)

        title = extract_title(a, url)
        known_updates[url] = {"title": title, "first_seen": ts}
        new_items.append(
            {
                "title": title,
                "link": url,
                "source": source["name"],
                "pubDate": ts_rfc822,
            }
        )

    print(f"[{source['name']}] 範囲内のリンク {found}件 / 新着 {len(new_items)}件")
    return new_items, known_updates


def main():
    known = load_json(KNOWN_LINKS_FILE, {})
    all_new = []
    all_known_updates = {}
    seen = set()

    for source in SECTION_SOURCES:
        try:
            new_items, known_updates = process_source(source, known, seen)
            all_new.extend(new_items)
            all_known_updates.update(known_updates)
        except Exception as e:
            print(f"[{source['name']}] 取得失敗: {e}")

    merge_new_items(all_new, all_known_updates)
    print(f"範囲指定ソース合計: 新着 {len(all_new)}件")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[ERROR] 予期しないエラー: {e}")
        sys.exit(0)
