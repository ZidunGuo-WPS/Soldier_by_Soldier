"""Abstract five-zone UI (legacy / 参谋视图); grid battle uses battle_sim."""

from __future__ import annotations

from typing import List, Tuple

from sbs.equipment import Gear
from sbs.soldier import Soldier

POSITIONS: List[Tuple[str, str]] = [
    ("front", "前军"),
    ("left", "左军"),
    ("center", "中军"),
    ("right", "右军"),
    ("rear", "后军"),
]

POSITION_KEYS = [k for k, _ in POSITIONS]


def demo_armies() -> Tuple[List[Soldier], List[Soldier]]:
    ours: List[Soldier] = [
        Soldier(
            id="demo_p1",
            name="赵大",
            faction="player",
            zone_key="center",
            hp=100.0,
            fatigue=12.0,
            gear=[
                Gear("weapon", "环首刀", 3),
                Gear("body", "皮甲", 2),
                Gear("head", "无", 1),
            ],
        ),
        Soldier(
            id="demo_p2",
            name="钱二",
            faction="player",
            zone_key="left",
            hp=92.0,
            fatigue=40.0,
            gear=[
                Gear("weapon", "短矛", 2),
                Gear("body", "札甲", 4),
                Gear("head", "铁胄", 3),
            ],
        ),
        Soldier(
            id="demo_p3",
            name="孙三",
            faction="player",
            zone_key="front",
            hp=88.0,
            fatigue=55.0,
            gear=[
                Gear("weapon", "斩马刀", 5),
                Gear("body", "鳞甲", 4),
                Gear("head", "面甲盔", 4),
                Gear("accessory", "军牌", 2),
            ],
        ),
    ]
    theirs: List[Soldier] = [
        Soldier(
            id="demo_e1",
            name="敌甲",
            faction="enemy",
            zone_key="center",
            hp=100.0,
            fatigue=20.0,
            gear=[
                Gear("weapon", "木枪", 1),
                Gear("body", "布衣", 1),
            ],
        ),
        Soldier(
            id="demo_e2",
            name="敌乙",
            faction="enemy",
            zone_key="right",
            hp=95.0,
            fatigue=35.0,
            gear=[
                Gear("weapon", "环首刀", 2),
                Gear("body", "皮甲", 2),
                Gear("head", "皮帽", 1),
            ],
        ),
    ]
    for s in ours + theirs:
        s.sync_hp_cap()
    return ours, theirs


def soldiers_in_zone(army: List[Soldier], position_key: str) -> List[Soldier]:
    return [s for s in army if s.zone_key == position_key]
