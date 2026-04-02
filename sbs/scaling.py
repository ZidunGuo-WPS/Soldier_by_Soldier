"""
Unbounded stats with diminishing *effect* (bonus saturates) and increasing *cost* to raise.
"""

from __future__ import annotations

import math
from typing import Tuple


def effect_bonus(value: float, scale: float = 40.0) -> float:
    """Marginal returns on how much `value` adds to rolls; no hard cap on value."""
    if value <= 0:
        return 0.0
    return scale * math.log1p(value / scale)


def fatigue_penalty_ratio(current: float, maximum: float) -> float:
    """1.0 = fresh, approaches 0.35 when exhausted."""
    if maximum <= 0:
        return 0.35
    r = min(1.0, max(0.0, current / maximum))
    # smooth curve: light tired ~0.9, dead tired ~0.4
    return 0.35 + 0.65 * math.cos((math.pi / 2) * r)


def exp_cost_for_step(current_level: float, base: float = 12.0, power: float = 1.35) -> float:
    """Experience points required to raise a stat from current_level -> current_level+1."""
    return base * ((1.0 + max(0.0, current_level)) ** power)


def apply_exp(
    current: float,
    pool: float,
    gain: float,
) -> Tuple[float, float, int]:
    """
    Add `gain` to pool, spend to increase `current` by whole steps if possible.
    Returns (new_current, new_pool, steps_gained).
    """
    pool += max(0.0, gain)
    steps = 0
    while pool >= exp_cost_for_step(current):
        cost = exp_cost_for_step(current)
        pool -= cost
        current += 1.0
        steps += 1
    return current, pool, steps


def high_morale_damage_factor(morale: float) -> float:
    """
    Player troops: no rout, but high morale adds up to ~+12% damage.
    `morale` is unbounded; use saturating curve.
    """
    # morale 0 -> 1.0, high morale -> ~1.12
    return 1.0 + 0.12 * (1.0 - math.exp(-morale / 80.0))


def enemy_morale_from_training(battles: float, train_hours: float) -> float:
    """Combines battle count and drill hours into a morale score (unbounded input, bounded-ish output)."""
    return 15.0 * math.log1p(battles) + 4.0 * math.log1p(train_hours / 10.0)
