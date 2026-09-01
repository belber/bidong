from app.schemas import MediaAvailability, ParseResult, VideoStats


def test_parse_result_defaults():
    r = ParseResult(
        id=1,
        bvid="BV1xx411c7mD",
        title="t",
        up_name="u",
        partition="p",
        duration=1,
        pubdate=1,
        cover_url="c",
        desc="",
        source_url="s",
        source="local",
        tags=[],
        collected_at=1,
        month="2026-09",
    )
    assert r.stats == VideoStats()
    assert r.danmaku_count == 0
    assert r.media == MediaAvailability()
