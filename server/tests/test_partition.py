from app.services.partition import channel_from_tid_v2


def test_main_partition_id():
    assert channel_from_tid_v2(1003) == "音乐"
    assert channel_from_tid_v2(1010) == "知识"


def test_sub_partition_id_range():
    assert channel_from_tid_v2(2001) == "影视"
    assert channel_from_tid_v2(2008) == "影视"
    assert channel_from_tid_v2(2016) == "音乐"
    assert channel_from_tid_v2(2017) == "音乐"
    assert channel_from_tid_v2(2027) == "音乐"
    assert channel_from_tid_v2(2205) == "生活经验"


def test_unknown_id():
    assert channel_from_tid_v2(0) == ""
    assert channel_from_tid_v2(None) == ""
    assert channel_from_tid_v2(9999) == ""
