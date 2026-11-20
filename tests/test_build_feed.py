from datetime import datetime, timezone, timedelta

import build_feed as bf

JST = timezone(timedelta(hours=9))


def fmt(dt):
    return dt.strftime("%a, %d %b %Y %H:%M:%S %z")


def test_item_date_missing_or_broken_is_oldest():
    assert bf.item_date({}) == bf.EPOCH
    assert bf.item_date({"pubDate": "壊れた日付"}) == bf.EPOCH


def test_item_date_parses():
    assert bf.item_date({"pubDate": fmt(datetime(2026, 9, 1, tzinfo=JST))}) == datetime(2026, 9, 1, tzinfo=JST)


def test_dedupe_keeps_newer_date():
    a = {"title": "同じ", "source": "S", "link": "https://x/1", "pubDate": fmt(datetime(2026, 9, 1, tzinfo=JST))}
    b = {"title": "同じ", "source": "S", "link": "https://x/2", "pubDate": fmt(datetime(2026, 9, 5, tzinfo=JST))}
    assert bf.dedupe([a, b]) == [b]


def test_dedupe_same_date_prefers_first_seen():
    d = fmt(datetime(2026, 9, 1, tzinfo=JST))
    a = {"title": "同じ", "source": "S", "link": "https://x/long/1", "pubDate": d}
    b = {"title": "同じ", "source": "S", "link": "https://x/2", "pubDate": d}
    known = {a["link"]: {"first_seen": "2026-09-01T00:00:00+00:00"}, b["link"]: {"first_seen": "2026-09-10T00:00:00+00:00"}}
    # 短いURLではなく、先に検知した方(=読者へ届け済み)を残す
    assert bf.dedupe([b, a], known) == [a]


def test_dedupe_different_source_not_merged():
    d = fmt(datetime(2026, 9, 1, tzinfo=JST))
    a = {"title": "同じ", "source": "S1", "link": "https://x/1", "pubDate": d}
    b = {"title": "同じ", "source": "S2", "link": "https://x/2", "pubDate": d}
    assert len(bf.dedupe([a, b])) == 2


def test_clamp_future_dates_uses_first_seen():
    future = fmt(datetime.now(JST) + timedelta(days=400))
    it = {"link": "https://x/1", "pubDate": future}
    known = {"https://x/1": {"first_seen": "2026-09-10T03:00:00+00:00"}}
    assert bf.clamp_future_dates([it], known) == 1
    assert bf.item_date(it) == datetime(2026, 9, 10, tzinfo=JST)


def test_clamp_future_dates_ignores_past_and_missing():
    items = [{"link": "a", "pubDate": fmt(datetime(2026, 9, 1, tzinfo=JST))}, {"link": "b"}]
    assert bf.clamp_future_dates(items, {}) == 0


def test_build_rss_structure_and_escape():
    xml = bf.build_rss([{"title": "A & B <C>", "link": "https://x/?a=1&b=2", "pubDate": "Tue, 01 Sep 2026 00:00:00 +0900"}])
    assert "<language>ja</language>" in xml
    assert 'rel="self"' in xml
    assert "A &amp; B &lt;C&gt;" in xml
    assert "<description>" not in xml.split("<item>")[1]  # 要約が無ければ出力しない


def test_build_sitemap():
    assert "<lastmod>2026-11-20T00:00:00+09:00</lastmod>" in bf.build_sitemap("2026-11-20T00:00:00+09:00")
