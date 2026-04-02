"""Equipment tiers map to display colors (no icons — text + color only)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

# Tier 1 = weakest ... higher = stronger (adjust names freely later)
TIER_COLORS: dict[int, Tuple[int, int, int]] = {
    1: (140, 140, 150),  # 灰 — 破烂 / 征发
    2: (200, 200, 210),  # 浅灰白 — 寻常
    3: (80, 180, 120),   # 绿 — 精良
    4: (100, 160, 255),  # 蓝 — 军械库好货
    5: (220, 160, 60),   # 金橙 — 稀罕
}


def tier_color(tier: int) -> Tuple[int, int, int]:
    return TIER_COLORS.get(max(1, min(tier, 5)), TIER_COLORS[2])


@dataclass
class Gear:
    slot: str  # weapon | body | head | accessory
    name: str
    tier: int = 2

    def color(self) -> Tuple[int, int, int]:
        return tier_color(self.tier)


SLOT_LABEL_ZH = {
    "weapon": "武器",
    "body": "身甲",
    "head": "盔",
    "accessory": "杂物",
}
