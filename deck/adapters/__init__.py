"""内置适配器清单。新增适配器：在 adapters/ 下写一个类，加入本列表即可。"""

from __future__ import annotations

from deck.adapters.mediakeys import MediaKeysAdapter
from deck.adapters.profile import ProfileAdapter
from deck.adapters.soundpad import SoundpadAdapter

BUILTIN_ADAPTERS = [
    SoundpadAdapter,
    MediaKeysAdapter,
    ProfileAdapter,
]
