from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from sbs.officer import Officer


@dataclass
class Army:
    id: str
    name: str
    faction: str
    soldier_ids: List[str] = field(default_factory=list)
    commander: Optional[Officer] = None
    # Player doctrine
    fight_to_death: bool = False
    allow_fatigue_rotation: bool = True

    def officer_morale_bonus_for_troops(self) -> float:
        if self.commander is None:
            return 0.0
        return self.commander.morale_aura()

    def retreat_speed_mult(self) -> float:
        if self.commander is None:
            return 1.0
        return self.commander.retreat_execution_factor()
