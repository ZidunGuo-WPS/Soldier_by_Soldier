from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from sbs.equipment import Gear
from sbs.scaling import enemy_morale_from_training, high_morale_damage_factor
from sbs.wounds import Wound, aggregate_wound_multiplier, leg_mobility_mult


@dataclass
class Soldier:
    """Single soldier: unbounded core stats + per-stat exp pools + fatigue + wounds."""

    id: str
    name: str
    faction: str  # "player" | "enemy" | future factions
    is_elite_name: bool = False  # named officer path
    is_protagonist: bool = False  # 玩家主角：与士卒同属性/成长，由玩家下达近战/远程等指令
    zone_key: Optional[str] = None  # optional legacy 5-zone UI (前左中右后)

    # Core attributes (float, unbounded); growth via exp pools
    strength: float = 10.0
    agility: float = 10.0
    endurance: float = 10.0
    vitality: float = 10.0
    wits: float = 8.0

    exp_strength: float = 0.0
    exp_agility: float = 0.0
    exp_endurance: float = 0.0
    exp_vitality: float = 0.0
    exp_wits: float = 0.0

    # Proficiencies (weapon categories), unbounded
    prof: Dict[str, float] = field(
        default_factory=lambda: {
            "one_handed": 5.0,
            "polearm": 0.0,
            "two_handed": 0.0,
            "bow": 0.0,
            "crossbow": 0.0,
            "throwing": 0.0,
        }
    )
    exp_prof: Dict[str, float] = field(default_factory=dict)

    hp: float = 100.0
    hp_max: float = 100.0
    fatigue: float = 0.0

    battles_fought: float = 0.0
    training_hours: float = 0.0

    # FM-style match factor in [-0.15, 0.15] roughly
    form_bias: float = 0.0

    wounds: List[Wound] = field(default_factory=list)
    gear: List[Gear] = field(default_factory=list)

    alive: bool = True

    def fatigue_max(self) -> float:
        return 40.0 + self.endurance * 2.5

    def sync_hp_cap(self) -> None:
        self.hp_max = 60.0 + self.vitality * 3.0
        self.hp = min(self.hp, self.hp_max)

    def enemy_morale_score(self) -> float:
        if self.faction == "player":
            return 0.0
        return enemy_morale_from_training(self.battles_fought, self.training_hours)

    def damage_multiplier(self, officer_morale_bonus: float) -> float:
        """Player: high morale from officers adds damage; fatigue + wounds reduce."""
        from sbs.scaling import effect_bonus, fatigue_penalty_ratio

        base = 1.0 + 0.01 * effect_bonus(self.strength, 35.0)
        prof = 1.0 + 0.008 * effect_bonus(self.prof.get("one_handed", 0.0), 30.0)
        fat = fatigue_penalty_ratio(self.fatigue, self.fatigue_max())
        wnd = aggregate_wound_multiplier(self.wounds)
        form = 1.0 + self.form_bias
        moral = high_morale_damage_factor(officer_morale_bonus) if self.faction == "player" else 1.0
        return max(0.15, base * prof * fat * wnd * form * moral)

    def received_damage_multiplier(self) -> float:
        from sbs.scaling import effect_bonus, fatigue_penalty_ratio

        vit = 1.0 / (1.0 + 0.012 * effect_bonus(self.vitality, 40.0))
        agi = 1.0 / (1.0 + 0.010 * effect_bonus(self.agility, 35.0))
        fat = 0.85 + 0.15 * fatigue_penalty_ratio(self.fatigue, self.fatigue_max())
        wnd = aggregate_wound_multiplier(self.wounds)
        return max(0.2, vit * agi * fat * wnd)

    def mobility_mult(self) -> float:
        return leg_mobility_mult(self.wounds)

    def add_fatigue(self, amount: float) -> None:
        self.fatigue = min(self.fatigue_max() * 1.2, self.fatigue + amount)

    def gear_by_slot(self) -> dict[str, Gear]:
        return {g.slot: g for g in self.gear}
