import watch_hubs_and_generate_rss as w


def test_chunks_cover_all_hubs_in_one_day(monkeypatch):
    monkeypatch.delenv("HUB_SLOT", raising=False)
    hubs = [f"h{i}" for i in range(1144)]
    # 実際の実行時刻(UTC 22,0,2,...,12時)を再現して、1日8回で全ハブが回るか確認
    day = 1_800_000_000 // 86400 * 86400
    seen = set()
    for hour in (22, 0, 2, 4, 6, 8, 10, 12):
        t = day + hour * 3600
        target, slot, chunks = w.select_hub_chunk(hubs, now=t)
        seen.update(target)
    assert seen == set(hubs)


def test_forced_slot(monkeypatch):
    monkeypatch.setenv("HUB_SLOT", "1")
    hubs = [f"h{i}" for i in range(700)]
    target, slot, chunks = w.select_hub_chunk(hubs)
    assert slot == 1 and target == hubs[300:600] and chunks == 3


def test_small_hub_list_single_chunk():
    target, slot, chunks = w.select_hub_chunk(["a", "b"], now=0)
    assert target == ["a", "b"] and chunks == 1
