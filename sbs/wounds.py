from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List


class BodyPart(str, Enum):
    HEAD = "head"
    CHEST = "chest"
    LEFT_ARM = "left_arm"
    RIGHT_ARM = "right_arm"
    LEFT_LEG = "left_leg"
    RIGHT_LEG = "right_leg"


class WoundSeverity(str, Enum):
    LIGHT = "light"  # recovers over time / rest
    HEAVY = "heavy"  # long recovery
    PERMANENT = "permanent"  # lasting debuff, still can fight


PART_LABEL_ZH = {
    BodyPart.HEAD: "头",
    BodyPart.CHEST: "胸",
    BodyPart.LEFT_ARM: "左臂",
    BodyPart.RIGHT_ARM: "右臂",
    BodyPart.LEFT_LEG: "左腿",
    BodyPart.RIGHT_LEG: "右腿",
}


@dataclass
class Wound:
    part: BodyPart
    severity: WoundSeverity
    days_to_recover: float = 0.0  # LIGHT/HEAVY; 0 if permanent

    def attack_mult(self) -> float:
        if self.severity == WoundSeverity.LIGHT:
            return 0.92
        if self.severity == WoundSeverity.HEAVY:
            return 0.78
        return 0.65

    def defense_mult(self) -> float:
        if self.severity == WoundSeverity.LIGHT:
            return 0.94
        if self.severity == WoundSeverity.HEAVY:
            return 0.82
        return 0.68


def aggregate_wound_multiplier(wounds: List[Wound]) -> float:
    """Combine multipliers for attack (arms matter) or mobility (legs)."""
    atk = 1.0
    for w in wounds:
        if w.severity == WoundSeverity.PERMANENT and w.part in (
            BodyPart.LEFT_ARM,
            BodyPart.RIGHT_ARM,
        ):
            atk *= w.attack_mult()
        elif w.severity != WoundSeverity.PERMANENT and w.part in (
            BodyPart.LEFT_ARM,
            BodyPart.RIGHT_ARM,
        ):
            atk *= w.attack_mult()
    # crude: any head/chest wound hurts everything a bit
    for w in wounds:
        if w.part in (BodyPart.HEAD, BodyPart.CHEST):
            atk *= 0.97 if w.severity == WoundSeverity.LIGHT else 0.90 if w.severity == WoundSeverity.HEAVY else 0.82
    return max(0.25, atk)


def leg_mobility_mult(wounds: List[Wound]) -> float:
    m = 1.0
    for w in wounds:
        if w.part not in (BodyPart.LEFT_LEG, BodyPart.RIGHT_LEG):
            continue
        if w.severity == WoundSeverity.LIGHT:
            m *= 0.92
        elif w.severity == WoundSeverity.HEAVY:
            m *= 0.75
        else:
            m *= 0.55
    return max(0.2, m)


def tick_wound_recovery(wounds: List[Wound], days: float) -> List[Wound]:
    """Remove or downgrade LIGHT/HEAVY wounds as days pass."""
    out: List[Wound] = []
    for w in wounds:
        if w.severity == WoundSeverity.PERMANENT:
            out.append(w)
            continue
        left = w.days_to_recover - days
        if left <= 0:
            continue
        out.append(
            Wound(
                part=w.part,
                severity=w.severity,
                days_to_recover=left,
            )
        )
    return out
