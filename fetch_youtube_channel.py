#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
近江八幡市公式YouTubeチャンネルの新着動画取得

YouTube自身のRSS機能(/feeds/videos.xml)はrobots.txtで明示的に禁止されて
いるため使わない。代わりに公式に用意されているYouTube Data API v3を使う。

APIキーは環境変数 YOUTUBE_API_KEY から読む(GitHub Secretsに登録)。
キーが設定されていない場合は、エラーにせず静かにスキップする
(他のソースの収集を止めないため)。
"""

import os
import sys
from datetime import datetime

import requests

from common import (
    load_json,
    merge_new_items,
    normalize_url,
    now_iso,
    JST,
    KNOWN_LINKS_FILE,
)

CHANNEL_ID = "UCgmIt67Nqoxbv-yRa3BmyBg"  # 近江八幡市公式YouTubeチャンネル
SOURCE_NAME = "近江八幡市公式YouTubeチャンネル"
API_URL = "https://www.googleapis.com/youtube/v3/search"
MAX_RESULTS = 15  # 1回の実行で確認する最新本数


def main():
    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not api_key:
        print(f"[{SOURCE_NAME}] YOUTUBE_API_KEY が設定されていないため、収集をスキップします。")
        return

    params = {
        "key": api_key,
        "channelId": CHANNEL_ID,
        "part": "snippet",
        "order": "date",
        "maxResults": MAX_RESULTS,
        "type": "video",
    }
    resp = requests.get(API_URL, params=params, timeout=15)

    if resp.status_code != 200:
        # クォータ超過やキー設定ミス等。詳細を出しつつ、他の収集は止めない。
        print(f"[{SOURCE_NAME}] APIエラー(status={resp.status_code}): {resp.text[:200]}")
        return

    data = resp.json()
    known = load_json(KNOWN_LINKS_FILE, {})
    ts = now_iso()

    new_items = []
    known_updates = {}

    for entry in data.get("items", []):
        video_id = (entry.get("id") or {}).get("videoId")
        snippet = entry.get("snippet") or {}
        title = (snippet.get("title") or "").strip()
        published = snippet.get("publishedAt")  # 例: 2026-09-01T01:00:00Z
        if not video_id or not title:
            continue

        url = normalize_url(f"https://www.youtube.com/watch?v={video_id}")
        if url in known:
            continue

        try:
            pub_dt = datetime.fromisoformat(published.replace("Z", "+00:00")).astimezone(JST)
        except (TypeError, ValueError):
            pub_dt = datetime.now(JST)

        known_updates[url] = {"title": title, "first_seen": ts}
        new_items.append(
            {
                "title": title,
                "link": url,
                "source": SOURCE_NAME,
                "pubDate": pub_dt.strftime("%a, %d %b %Y %H:%M:%S %z"),
            }
        )

    merge_new_items(new_items, known_updates)
    print(f"[{SOURCE_NAME}] 新着 {len(new_items)}件")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[ERROR] 予期しないエラー: {e}")
        sys.exit(0)
