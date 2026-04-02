"""
Grid battle: mixed cells, per-soldier resolution (capped pairs/tick for perf).
Movement pushes toward enemy; player fatigue rotation when allowed.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from sbs.army import Army
from sbs.scaling import apply_exp, effect_bonus
from sbs.soldier import Soldier
from sbs.wounds import BodyPart, Wound, WoundSeverity


class Terrain(str, Enum):
    PLAIN = "plain"
    RIVER = "river"
    HIGH = "high"


@dataclass
class UnitRef:
    army_id: str
    soldier_id: str


@dataclass
class Cell:
    terrain: Terrain = Terrain.PLAIN
    units: List[UnitRef] = field(default_factory=list)


def terrain_ranged_mult(t: Terrain) -> float:
    if t == Terrain.HIGH:
        return 1.12
    return 1.0


def terrain_fatigue_on_enter(t: Terrain) -> float:
    if t == Terrain.RIVER:
        return 6.0
    return 1.0


def terrain_move_mult(t: Terrain) -> float:
    if t == Terrain.RIVER:
        return 0.55
    return 1.0


@dataclass
class BattleState:
    width: int
    height: int
    cells: List[List[Cell]]
    soldiers: Dict[str, Soldier]
    armies: Dict[str, Army]
    positions: Dict[str, Tuple[int, int]]  # soldier_id -> (r,c)
    log: List[str] = field(default_factory=list)
    tick_index: int = 0

    def _cell(self, r: int, c: int) -> Cell:
        return self.cells[r][c]

    def _in_bounds(self, r: int, c: int) -> bool:
        return 0 <= r < self.height and 0 <= c < self.width

    def army_for_soldier(self, sid: str) -> Army:
        s = self.soldiers[sid]
        for a in self.armies.values():
            if sid in a.soldier_ids:
                return a
        raise KeyError(sid)

    def _remove_unit_at(self, r: int, c: int, ref: UnitRef) -> None:
        cell = self._cell(r, c)
        cell.units = [u for u in cell.units if not (u.army_id == ref.army_id and u.soldier_id == ref.soldier_id)]

    def _add_unit_at(self, r: int, c: int, ref: UnitRef) -> None:
        self._cell(r, c).units.append(ref)

    def _move_unit(self, sid: str, src: Tuple[int, int], dst: Tuple[int, int]) -> None:
        r0, c0 = src
        r1, c1 = dst
        ref = None
        for u in self._cell(r0, c0).units:
            if u.soldier_id == sid:
                ref = u
                break
        if ref is None:
            return
        self._remove_unit_at(r0, c0, ref)
        self._add_unit_at(r1, c1, ref)
        self.positions[sid] = (r1, c1)
        sol = self.soldiers[sid]
        sol.add_fatigue(terrain_fatigue_on_enter(self._cell(r1, c1).terrain) * 0.15)

    def _enemy_direction(self, faction: str) -> int:
        """Row delta toward enemy: player (south start) moves up (-1), enemy moves down (+1)."""
        return -1 if faction == "player" else 1

    def _home_direction(self, faction: str) -> int:
        """Toward own rear: opposite of toward enemy."""
        return 1 if faction == "player" else -1

    def setup_demo_skirmish(self, rng: random.Random) -> None:
        """Small battle for testing: 6x5 grid, river middle band."""
        self.cells = [[Cell(Terrain.PLAIN) for _ in range(self.width)] for _ in range(self.height)]
        mid = self.height // 2
        for r in range(self.height):
            for c in range(self.width):
                if r == mid:
                    self.cells[r][c].terrain = Terrain.RIVER
                elif r == mid - 1 or r == mid + 1:
                    if c % 2 == 0:
                        self.cells[r][c].terrain = Terrain.HIGH

        # clear units
        self.positions.clear()
        for row in self.cells:
            for cell in row:
                cell.units.clear()

        # place soldiers: armies must exist in self.armies / self.soldiers
        for aid, army in self.armies.items():
            for idx, sid in enumerate(army.soldier_ids):
                if army.faction == "enemy":
                    r, c = 0, min(self.width - 1, idx % self.width)
                else:
                    r, c = self.height - 1, min(self.width - 1, idx % self.width)
                ref = UnitRef(aid, sid)
                self._cell(r, c).units.append(ref)
                self.positions[sid] = (r, c)

    def _factions_in_cell(self, r: int, c: int) -> Tuple[bool, bool]:
        has_p = False
        has_e = False
        for u in self._cell(r, c).units:
            army = self.armies[u.army_id]
            if army.faction == "player":
                has_p = True
            elif army.faction == "enemy":
                has_e = True
        return has_p, has_e

    def movement_phase(self, rng: random.Random) -> None:
        refs: List[Tuple[UnitRef, int, int]] = []
        for r in range(self.height):
            for c in range(self.width):
                for u in self._cell(r, c).units:
                    refs.append((u, r, c))
        rng.shuffle(refs)

        for u, r, c in refs:
            sol = self.soldiers.get(u.soldier_id)
            if sol is None or not sol.alive:
                continue
            has_p, has_e = self._factions_in_cell(r, c)
            if has_p and has_e:
                continue
            army = self.armies[u.army_id]
            dr = self._enemy_direction(army.faction)
            # try advance
            nr, nc = r + dr, c
            if not self._in_bounds(nr, nc):
                continue
            move_roll = terrain_move_mult(self._cell(nr, nc).terrain) * sol.mobility_mult()
            if rng.random() > min(0.95, 0.55 + 0.25 * move_roll):
                continue
            # enter if not blocked by "only enemies and no allies" - can always enter to mix
            self._move_unit(u.soldier_id, (r, c), (nr, nc))

    def rotation_phase(self, rng: random.Random) -> None:
        """Player troops fall back when exhausted unless fight_to_death."""
        for aid, army in self.armies.items():
            if army.faction != "player":
                continue
            if army.fight_to_death or not army.allow_fatigue_rotation:
                continue
            for sid in list(army.soldier_ids):
                sol = self.soldiers.get(sid)
                if sol is None or not sol.alive:
                    continue
                pos = self.positions.get(sid)
                if pos is None:
                    continue
                r, c = pos
                has_p, has_e = self._factions_in_cell(r, c)
                if not has_e:
                    continue
                ratio = sol.fatigue / max(1.0, sol.fatigue_max())
                if ratio < 0.72:
                    continue
                if rng.random() > 0.35 * army.retreat_speed_mult():
                    continue
                back_dr = self._home_direction(army.faction)
                br, bc = r + back_dr, c
                if not self._in_bounds(br, bc):
                    continue
                bcell = self._cell(br, bc)
                _, benemy = self._factions_in_cell(br, bc)
                if benemy:
                    continue
                ref = UnitRef(aid, sid)
                self._remove_unit_at(r, c, ref)
                self._add_unit_at(br, bc, ref)
                self.positions[sid] = (br, bc)
                sol.add_fatigue(2.0)
                self.log.append(f"{sol.name} 后撤换气")

    def combat_phase(self, rng: random.Random) -> None:
        max_pairs = 14
        for r in range(self.height):
            for c in range(self.width):
                cell = self._cell(r, c)
                if not cell.units:
                    continue
                groups: Dict[str, List[Soldier]] = {"player": [], "enemy": []}
                owners: Dict[str, Tuple[str, str]] = {}  # sid -> (army_id, faction)
                for u in cell.units:
                    army = self.armies[u.army_id]
                    sol = self.soldiers[u.soldier_id]
                    if not sol.alive:
                        continue
                    fac = army.faction
                    if fac not in groups:
                        continue
                    groups[fac].append(sol)
                    owners[sol.id] = (u.army_id, fac)

                if not groups["player"] or not groups["enemy"]:
                    continue

                pa = groups["player"][:]
                eb = groups["enemy"][:]
                rng.shuffle(pa)
                rng.shuffle(eb)
                n = min(len(pa), len(eb), max_pairs)
                for i in range(n):
                    self._exchange_blows(pa[i], eb[i], cell.terrain, rng, owners)
                # extras chip in
                if len(pa) > n:
                    for sol in pa[n:]:
                        tgt = rng.choice(eb)
                        self._one_sided_strike(sol, tgt, cell.terrain, rng, owners)
                if len(eb) > n:
                    for sol in eb[n:]:
                        tgt = rng.choice(pa)
                        self._one_sided_strike(sol, tgt, cell.terrain, rng, owners)

    def _officer_bonus(self, army_id: str) -> float:
        army = self.armies[army_id]
        return army.officer_morale_bonus_for_troops()

    def _one_sided_strike(
        self,
        attacker: Soldier,
        defender: Soldier,
        terrain: Terrain,
        rng: random.Random,
        owners: Dict[str, Tuple[str, str]],
    ) -> None:
        if not attacker.alive or not defender.alive:
            return
        aid, _ = owners[attacker.id]
        dmg = self._roll_damage(attacker, defender, terrain, rng, self._officer_bonus(aid))
        self._apply_damage(defender, dmg, rng)
        attacker.add_fatigue(1.2)

    def _exchange_blows(
        self,
        a: Soldier,
        b: Soldier,
        terrain: Terrain,
        rng: random.Random,
        owners: Dict[str, Tuple[str, str]],
    ) -> None:
        if not a.alive or not b.alive:
            return
        a_army, _ = owners[a.id]
        b_army, _ = owners[b.id]
        da = self._roll_damage(a, b, terrain, rng, self._officer_bonus(a_army))
        db = self._roll_damage(b, a, terrain, rng, self._officer_bonus(b_army))
        self._apply_damage(b, da, rng)
        self._apply_damage(a, db, rng)
        a.add_fatigue(2.0)
        b.add_fatigue(2.0)
        self._grant_combat_exp(a, 0.6)
        self._grant_combat_exp(b, 0.6)

    def _roll_damage(
        self,
        attacker: Soldier,
        defender: Soldier,
        terrain: Terrain,
        rng: random.Random,
        officer_morale: float,
    ) -> float:
        spread = 0.85 + 0.3 * rng.random()
        base = 3.5 + 2.0 * rng.random()
        form_jitter = 1.0 + rng.uniform(-0.12, 0.12)
        high = terrain_ranged_mult(terrain)
        raw = base * spread * form_jitter * high
        raw *= attacker.damage_multiplier(officer_morale)
        raw *= defender.received_damage_multiplier()
        sk = effect_bonus(attacker.prof.get("one_handed", 0.0), 28.0)
        raw *= 1.0 + 0.035 * sk / (12.0 + sk)
        return max(0.5, raw)

    def _apply_damage(self, target: Soldier, dmg: float, rng: random.Random) -> None:
        target.hp -= dmg
        if target.hp <= 0:
            target.hp = 0
            target.alive = False
            self.log.append(f"{target.name} 阵亡")
            return
        if dmg > 12 and rng.random() < 0.12:
            target.wounds.append(
                Wound(
                    BodyPart.CHEST if rng.random() < 0.5 else BodyPart.LEFT_ARM,
                    WoundSeverity.LIGHT,
                    days_to_recover=3 + rng.random() * 4,
                )
            )
            self.log.append(f"{target.name} 负轻伤")
        elif dmg > 18 and rng.random() < 0.08:
            sev = WoundSeverity.HEAVY if rng.random() < 0.7 else WoundSeverity.PERMANENT
            part = rng.choice(list(BodyPart))
            target.wounds.append(
                Wound(
                    part,
                    sev,
                    days_to_recover=0.0 if sev == WoundSeverity.PERMANENT else 14.0,
                )
            )
            self.log.append(f"{target.name} 重伤" if sev != WoundSeverity.PERMANENT else f"{target.name} 致残")

    def _grant_combat_exp(self, sol: Soldier, amount: float) -> None:
        sol.strength, sol.exp_strength, _ = apply_exp(sol.strength, sol.exp_strength, amount * 0.35)
        sol.endurance, sol.exp_endurance, _ = apply_exp(sol.endurance, sol.exp_endurance, amount * 0.25)
        sol.vitality, sol.exp_vitality, _ = apply_exp(sol.vitality, sol.exp_vitality, amount * 0.2)
        sol.agility, sol.exp_agility, _ = apply_exp(sol.agility, sol.exp_agility, amount * 0.15)
        pkey = "one_handed"
        cur = sol.prof.get(pkey, 0.0)
        pool = sol.exp_prof.get(pkey, 0.0)
        cur, pool, _ = apply_exp(cur, pool, amount * 0.5)
        sol.prof[pkey] = cur
        sol.exp_prof[pkey] = pool
        sol.sync_hp_cap()

    def cleanup_dead(self) -> None:
        for r in range(self.height):
            for c in range(self.width):
                cell = self._cell(r, c)
                kept: List[UnitRef] = []
                for u in cell.units:
                    sol = self.soldiers.get(u.soldier_id)
                    if sol and sol.alive:
                        kept.append(u)
                    else:
                        self.positions.pop(u.soldier_id, None)
                cell.units = kept

    def tick(self, rng: random.Random) -> None:
        self.tick_index += 1
        self.log = self.log[-80:]
        self.movement_phase(rng)
        self.rotation_phase(rng)
        self.combat_phase(rng)
        self.cleanup_dead()

    def alive_counts(self) -> Tuple[int, int]:
        p = e = 0
        for s in self.soldiers.values():
            if not s.alive:
                continue
            a = self.army_for_soldier(s.id)
            if a.faction == "player":
                p += 1
            elif a.faction == "enemy":
                e += 1
        return p, e
