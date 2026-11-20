from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup

import common

JST = timezone(timedelta(hours=9))


def soup(html):
    return BeautifulSoup(html, "html.parser")


# ---- 日付 ----
def test_parse_pubdate_rfc822():
    dt = common.parse_pubdate_or_none("Thu, 11 Sep 2025 00:00:00 +0900")
    assert dt == datetime(2025, 9, 11, tzinfo=JST)


def test_parse_pubdate_iso_with_z():
    assert common.parse_pubdate_or_none("2025-09-11T00:00:00Z") == datetime(2025, 9, 11, tzinfo=timezone.utc)


def test_parse_pubdate_invalid_returns_none():
    assert common.parse_pubdate_or_none("") is None
    assert common.parse_pubdate_or_none(None) is None
    assert common.parse_pubdate_or_none("日付ではない") is None


def test_parse_pubdate_legacy_falls_back_to_now():
    assert abs((common.parse_pubdate("x") - datetime.now(timezone.utc)).total_seconds()) < 5


def test_extract_page_date_from_body():
    s = soup("<body><p>更新日：2026年9月15日</p></body>")
    assert common.extract_page_date(s) == datetime(2026, 9, 15, tzinfo=JST)


def test_extract_page_date_none_when_missing():
    assert common.extract_page_date(soup("<body><p>日付なし</p></body>")) is None


def test_extract_page_date_ignores_period_range():
    # 「2027年1-3月期」は日付ではない(DATE_PATTERN側の仕様。本文の更新日表記のみ対象)
    assert common.extract_page_date(soup("<body>2027年1-3月期の募集</body>")) is None


# ---- タイトル ----
def test_clean_title_strips_site_suffix():
    assert common._clean_title("記事名｜近江八幡市立図書館") == "記事名"


def test_extract_page_title_skips_site_name():
    s = soup('<head><meta property="og:title" content="近江八幡市"><title>本当の記事名 | 近江八幡市</title></head>')
    assert common.extract_page_title(s) == "本当の記事名"


def test_extract_page_title_unknown():
    assert common.extract_page_title(soup("<body></body>")) == "(タイトル不明)"


# ---- 要約 ----
def test_trim_summary_cuts_at_sentence_end():
    text = "あ" * 120 + "。" + "い" * 100
    out = common._trim_summary(text)
    assert out.endswith("。") and len(out) <= common.SUMMARY_MAX_LENGTH


def test_suppress_if_duplicates_title():
    assert common._suppress_if_duplicates_title("お知らせです", "お知らせです") == ""
    assert common._suppress_if_duplicates_title("全く違う長い説明文がここに入ります。", "お知らせ") != ""


# ---- URL ----
def test_normalize_url_https_upgrade_and_fragment():
    assert common.normalize_url("http://www.omi8.com/a.html#top") == "https://www.omi8.com/a.html"


def test_normalize_url_keeps_unconfirmed_http():
    assert common.normalize_url("http://bungei.or.jp/x") == "http://bungei.or.jp/x"


def test_source_from_url():
    assert common.source_from_url("https://omihachiman.keizai.biz/a") == "近江八幡経済新聞"


# ---- 要約を公開してよい出典 ----
def test_description_allowed():
    assert common.description_allowed("食べログ(新規オープン)")
    assert not common.description_allowed("近江八幡市公式サイト")


# ---- 日付なしサイトの過去記事 ----
def test_dateless_backlog():
    known = {
        "https://www.omi8.com/a": {"first_seen": "2026-09-08T01:00:00+00:00"},
        "https://www.omi8.com/b": {"first_seen": "2026-09-20T01:00:00+00:00"},
    }
    base = common.dateless_baselines(known)
    assert common.is_dateless_backlog("https://www.omi8.com/a", known, base) is True
    assert common.is_dateless_backlog("https://www.omi8.com/b", known, base) is False
    assert common.is_dateless_backlog("https://example.com/x", known, base) is False


# ---- 通信のやり直し ----
class FakeResp:
    def __init__(self, code):
        self.status_code = code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)


class FakeSession:
    def __init__(self, results):
        self.results = list(results)
        self.calls = 0

    def get(self, *a, **k):
        self.calls += 1
        r = self.results.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def test_fetch_retries_on_503_then_succeeds(monkeypatch):
    monkeypatch.setattr(common.time, "sleep", lambda s: None)
    s = FakeSession([FakeResp(503), FakeResp(200)])
    assert common.fetch_bytes("http://x", s).status_code == 200
    assert s.calls == 2


def test_fetch_retries_on_timeout_then_gives_up(monkeypatch):
    monkeypatch.setattr(common.time, "sleep", lambda s: None)
    s = FakeSession([requests.Timeout()] * 3)
    try:
        common.fetch_bytes("http://x", s)
        assert False, "例外が出るはず"
    except requests.Timeout:
        pass
    assert s.calls == 3


def test_fetch_does_not_retry_404(monkeypatch):
    monkeypatch.setattr(common.time, "sleep", lambda s: None)
    s = FakeSession([FakeResp(404), FakeResp(200)])
    try:
        common.fetch_bytes("http://x", s)
        assert False
    except requests.HTTPError:
        pass
    assert s.calls == 1


# ---- 失敗の記録 ----
def test_run_main_records_failure(tmp_path, monkeypatch):
    log = tmp_path / "failures.log"
    monkeypatch.setattr(common, "FAILURES_FILE", log)

    def boom():
        raise ValueError("だめ")

    common.run_main(boom, "x.py")  # 例外を外に出さない
    assert "x.py: ValueError: だめ" in log.read_text(encoding="utf-8")


def test_run_main_success_writes_nothing(tmp_path, monkeypatch):
    log = tmp_path / "failures.log"
    monkeypatch.setattr(common, "FAILURES_FILE", log)
    common.run_main(lambda: None, "ok.py")
    assert not log.exists()
