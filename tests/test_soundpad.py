"""Soundpad 声音列表解析：分类归组、索引顺序、容错回退。"""

from deck.adapters.soundpad import SoundpadAdapter


def _adapter() -> SoundpadAdapter:
    return SoundpadAdapter({})


def test_parse_soundlist_with_categories():
    xml = (
        "<SoundList>"
        '<Category name="默认">'
        '<Sound name="笑声" path="C:/sounds/laugh.mp3"/>'
        '<Sound name="欢呼" path="C:/sounds/cheer.mp3"/>'
        "</Category>"
        '<Category name="BGM">'
        '<Sound name="轻音乐" path="C:/sounds/bgm1.mp3"/>'
        "</Category>"
        "</SoundList>"
    )
    tracks = _adapter()._parse_soundlist(xml)
    assert [(t.index, t.name, t.category) for t in tracks] == [
        (1, "笑声", "默认"),
        (2, "欢呼", "默认"),
        (3, "轻音乐", "BGM"),
    ]


def test_parse_soundlist_nested_categories():
    xml = (
        "<SoundList>"
        '<Category name="A">'
        '<SubCategory name="B">'
        '<Sound name="s1" path="p1.mp3"/>'
        "</SubCategory>"
        "</Category>"
        "</SoundList>"
    )
    tracks = _adapter()._parse_soundlist(xml)
    assert len(tracks) == 1
    assert tracks[0].name == "s1"
    assert tracks[0].category == "B"  # 内层分类覆盖外层


def test_parse_soundlist_flat_without_categories():
    xml = '<SoundList><Sound name="a" path="p1.mp3"/><Sound name="b" path="p2.mp3"/></SoundList>'
    tracks = _adapter()._parse_soundlist(xml)
    assert len(tracks) == 2
    assert tracks[0].category is None
    assert tracks[1].category is None


def test_parse_soundlist_regex_fallback():
    bad_xml = "<SoundList><Sound name=broken><Sound name=broken2 path=xxx></SoundList>"
    tracks = _adapter()._parse_soundlist(bad_xml)
    # 容错路径不崩溃且尽量解析
    assert isinstance(tracks, list)


def test_parse_soundlist_empty_and_error_response():
    assert _adapter()._parse_soundlist("") == []
    assert _adapter()._parse_soundlist("R-500 error") == []


def test_build_sounds_auto_keeps_category():
    adapter = _adapter()
    xml = (
        "<SoundList>"
        '<Category name="默认">'
        '<Sound name="笑声" path="a.mp3"/>'
        "</Category>"
        "</SoundList>"
    )
    buttons = adapter._build_sounds(adapter._parse_soundlist(xml))
    assert len(buttons) == 1
    assert buttons[0].name == "笑声"
    assert buttons[0].category == "默认"


def test_build_sounds_configured_has_no_category():
    adapter = SoundpadAdapter({"sounds": [{"name": "大笑", "kind": "hotkey", "hotkey": ["ctrl", "1"]}]})
    buttons = adapter._build_sounds([])
    assert len(buttons) == 1
    assert buttons[0].category is None
