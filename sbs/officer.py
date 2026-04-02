from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from sbs.scaling import effect_bonus


class OfficerRank(str, Enum):
    NONE = "none"
    BAIHU = "baihu"  # 百户
    QIANHU = "qianhu"  # 千户
    GENERAL = "general"


RANK_LABEL_ZH = {
    OfficerRank.NONE: "无",
    OfficerRank.BAIHU: "百户",
    OfficerRank.QIANHU: "千户",
    OfficerRank.GENERAL: "将",
}


@dataclass
class Officer:
    """Commands a detachment; boosts morale (player) and command execution."""

    id: str
    name: str
    rank: OfficerRank = OfficerRank.NONE
    leadership: float = 15.0
    command: float = 12.0  # retreat / complex orders
    tactics: float = 10.0

    def morale_aura(self) -> float:
        """Feeds into player troop damage bonus (not rout checks)."""
        base = effect_bonus(self.leadership, 30.0)
        mult = 1.0
        if self.rank == OfficerRank.BAIHU:
            mult = 1.08
        elif self.rank == OfficerRank.QIANHU:
            mult = 1.15
        elif self.rank == OfficerRank.GENERAL:
            mult = 1.22
        return base * mult

    def retreat_execution_factor(self) -> float:
        """Higher -> faster/cleaner retreat when player orders pull-back."""
        return 0.5 + 0.02 * effect_bonus(self.command, 25.0) + 0.01 * effect_bonus(self.tactics, 30.0)
