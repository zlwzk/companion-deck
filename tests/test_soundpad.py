"""Soundpad 适配器测试：分类树解析、声音列表、容错回退。"""

from deck.adapters.soundpad import SoundpadAdapter


def _adapter() -> SoundpadAdapter:
    return SoundpadAdapter({})


# ---------- GetSoundlist 扁平解析 ----------

def test_parse_soundlist_flat():
    xml = (
        '<Soundlist>'
        '<Sound index="3" url="C:/sounds/a.mp3" artist="X" title="A" duration="00:02" playCount="7"/>'
        '<Sound index="4" url="C:/sounds/b.mp3" title="B" duration="01:30" playCount="0"/>'
        "</Soundlist>"
    )
    tracks = _adapter()._parse_soundlist(xml)
    assert len(tracks) == 2
    assert tracks[0].index == 3
    assert tracks[0].name == "A"
    assert tracks[0].title == "A"
    assert tracks[0].artist == "X"
    assert tracks[0].duration == "00:02"
    assert tracks[0].play_count == 7
    assert tracks[0].category is None  # 扁平列表不带分类


def test_parse_soundlist_empty_and_error_response():
    assert _adapter()._parse_soundlist("") == []
    assert _adapter()._parse_soundlist("R-500 error") == []


def test_parse_soundlist_regex_fallback():
    bad_xml = '<Soundlist><Sound name=broken><Sound name=broken2 path=xxx></Soundlist>'
    tracks = _adapter()._parse_soundlist(bad_xml)
    assert isinstance(tracks, list)


# ---------- GetCategories 分类树解析 ----------

def test_parse_categories_simple():
    xml = (
        "<Categories>"
        '<Category index="0" type="1" name="All sounds" hidden="true">'
        '<Sound index="3" url="a.mp3" title="A" artist="X" duration="00:02" playCount="7"/>'
        '<Sound index="4" url="b.mp3" title="B" duration="01:30" playCount="0"/>'
        "</Category>"
        '<Category index="1" type="0" name="我的分类">'
        '<Sound index="5" url="c.mp3" title="C" duration="00:05" playCount="2"/>'
        "</Category>"
        "</Categories>"
    )
    cats = _adapter()._parse_categories(xml)
    assert len(cats) == 2
    assert cats[0].index == 0
    assert cats[0].name == "All sounds"
    assert cats[0].hidden is True
    assert cats[0].type == 1
    assert len(cats[0].sounds) == 2
    assert cats[0].sounds[0].index == 3
    assert cats[0].sounds[0].title == "A"
    assert cats[0].sounds[0].category_index == 0
    assert cats[0].sounds[0].position_in_category == 1
    assert cats[0].sounds[1].position_in_category == 2
    assert cats[1].name == "我的分类"
    assert cats[1].sounds[0].index == 5


def test_parse_categories_nested():
    xml = (
        "<Categories>"
        '<Category index="1" name="父分类">'
        '<Category index="2" name="子分类">'
        '<Sound index="6" url="d.mp3" title="D"/>'
        "</Category>"
        "</Category>"
        "</Categories>"
    )
    cats = _adapter()._parse_categories(xml)
    assert len(cats) == 1
    assert cats[0].name == "父分类"
    assert len(cats[0].subcategories) == 1
    assert cats[0].subcategories[0].name == "子分类"
    assert cats[0].subcategories[0].sounds[0].index == 6
    assert cats[0].subcategories[0].sounds[0].category_index == 2


def test_parse_categories_empty_and_error():
    assert _adapter()._parse_categories("") == []
    assert _adapter()._parse_categories("R-500 error") == []


# ---------- 按钮生成（含分类信息） ----------

def test_build_sounds_with_categories_carries_category_info():
    adapter = _adapter()
    xml = (
        "<Categories>"
        '<Category index="0" type="1" name="All sounds" hidden="true">'
        '<Sound index="3" title="A"/>'
        "</Category>"
        '<Category index="1" name="BGM">'
        '<Sound index="4" title="B"/>'
        '<Sound index="5" title="C"/>'
        "</Category>"
        "</Categories>"
    )
    cats = adapter._parse_categories(xml)
    buttons = adapter._build_sounds([], cats)
    assert len(buttons) == 3
    # 第一个按钮属 All sounds 分类
    assert buttons[0].category == "All sounds"
    assert buttons[0].category_index == 0
    assert buttons[0].position_in_category == 1
    assert buttons[0].kind == "category_sound"
    # 后两个按钮属 BGM 分类，position 递增
    assert buttons[1].category == "BGM"
    assert buttons[1].position_in_category == 1
    assert buttons[2].category == "BGM"
    assert buttons[2].position_in_category == 2


def test_build_sounds_configured_overrides_auto():
    adapter = SoundpadAdapter({"sounds": [{"name": "大笑", "kind": "hotkey", "hotkey": ["ctrl", "1"]}]})
    buttons = adapter._build_sounds([], [])
    assert len(buttons) == 1
    assert buttons[0].name == "大笑"
    assert buttons[0].category is None


# ---------- 时长解析 ----------

def test_parse_duration_minutes():
    assert SoundpadAdapter._parse_duration("00:02") == 2.0
    assert SoundpadAdapter._parse_duration("01:30") == 90.0
    assert SoundpadAdapter._parse_duration("01:02:03") == 3723.0


def test_parse_duration_invalid():
    assert SoundpadAdapter._parse_duration(None) is None
    assert SoundpadAdapter._parse_duration("") is None
    assert SoundpadAdapter._parse_duration("abc") is None
