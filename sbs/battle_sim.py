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


# Odd-r offset hex neighbors: same (row,col) storage as矩形底图，邻接为六向。
_HEX_DR_DC_EVEN = ((+1, 0), (+1, -1), (0, -1), (-1, -1), (-1, 0), (0, +1))
_HEX_DR_DC_ODD = ((+1, +1), (+1, 0), (0, -1), (-1, 0), (-1, +1), (0, +1))


def hex_neighbor_deltas(row: int) -> Tuple[Tuple[int, int], ...]:
    return _HEX_DR_DC_ODD if (row & 1) else _HEX_DR_DC_EVEN


def hex_neighbors(
    row: int, col: int, width: int, height: int
) -> List[Tuple[int, int]]:
    out: List[Tuple[int, int]] = []
    for dr, dc in hex_neighbor_deltas(row):
        nr, nc = row + dr, col + dc
        if 0 <= nr < height and 0 <= nc < width:
            out.append((nr, nc))
    return out


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

    def _protagonist(self) -> Optional[Soldier]:
        for s in self.soldiers.values():
            if s.is_protagonist and s.faction == "player":
                return s
        return None

    def movement_phase(self, rng: random.Random, siege_defense: bool) -> None:
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
            if sol.is_protagonist and siege_defense:
                continue
            has_p, has_e = self._factions_in_cell(r, c)
            if has_p and has_e:
                continue
            army = self.armies[u.army_id]
            nbrs = hex_neighbors(r, c, self.width, self.height)
            if army.faction == "player":
                best = min(nr for nr, _ in nbrs)
                candidates = [(nr, nc) for nr, nc in nbrs if nr == best]
            else:
                best = max(nr for nr, _ in nbrs)
                candidates = [(nr, nc) for nr, nc in nbrs if nr == best]
            rng.shuffle(candidates)
            moved = False
            for nr, nc in candidates:
                move_roll = terrain_move_mult(self._cell(nr, nc).terrain) * sol.mobility_mult()
                if rng.random() > min(0.95, 0.55 + 0.25 * move_roll):
                    continue
                self._move_unit(u.soldier_id, (r, c), (nr, nc))
                moved = True
                break
            if not moved:
                continue

    def rotation_phase(self, rng: random.Random, siege_defense: bool) -> None:
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
                if sol.is_protagonist and siege_defense:
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
                nbrs = hex_neighbors(r, c, self.width, self.height)
                if army.faction == "player":
                    back_best = max(nr for nr, _ in nbrs)
                    back_cands = [(nr, nc) for nr, nc in nbrs if nr == back_best]
                else:
                    back_best = min(nr for nr, _ in nbrs)
                    back_cands = [(nr, nc) for nr, nc in nbrs if nr == back_best]
                rng.shuffle(back_cands)
                ref = UnitRef(aid, sid)
                retreated = False
                for br, bc in back_cands:
                    _, benemy = self._factions_in_cell(br, bc)
                    if benemy:
                        continue
                    self._remove_unit_at(r, c, ref)
                    self._add_unit_at(br, bc, ref)
                    self.positions[sid] = (br, bc)
                    sol.add_fatigue(2.0)
                    self.log.append(f"{sol.name} 后撤换气")
                    retreated = True
                    break
                if not retreated:
                    continue

    def combat_phase(self, rng: random.Random) -> None:
        max_pairs = 14
        fight_summaries: List[Tuple[str, str, int, int]] = []
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
                rep_p = pa[0].name
                rep_e = eb[0].name
                np_, ne_ = len(pa), len(eb)
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
                fight_summaries.append((rep_p, rep_e, np_, ne_))

        if fight_summaries:
            rp, re, np_, ne_ = fight_summaries[0]
            if len(fight_summaries) == 1:
                self.log.append(f"士卒混战：{np_}我方↔{ne_}敌方同格（{rp}·{re}）")
            else:
                self.log.append(f"士卒混战：{len(fight_summaries)} 处同格交兵（如 {rp}↔{re} 等）")

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
        if attacker.id in owners:
            aid, _ = owners[attacker.id]
        else:
            aid = self.army_for_soldier(attacker.id).id
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

    def _roll_ranged_damage(
        self,
        attacker: Soldier,
        defender: Soldier,
        terrain: Terrain,
        rng: random.Random,
        siege_defense: bool,
    ) -> float:
        spread = 0.88 + 0.28 * rng.random()
        base = 4.2 + 2.5 * rng.random()
        form_jitter = 1.0 + rng.uniform(-0.1, 0.1)
        high = terrain_ranged_mult(terrain)
        raw = base * spread * form_jitter * high
        aid = self.army_for_soldier(attacker.id).id
        raw *= attacker.damage_multiplier(self._officer_bonus(aid))
        raw *= defender.received_damage_multiplier()
        sk = effect_bonus(attacker.prof.get("bow", 0.0), 26.0)
        raw *= 1.0 + 0.045 * sk / (10.0 + sk)
        if siege_defense:
            raw *= 1.16 + 0.14 * rng.random()
            raw *= 1.0 + 0.004 * effect_bonus(attacker.wits, 32.0)
        return max(0.8, raw)

    def _grant_ranged_exp(self, sol: Soldier, amount: float) -> None:
        sol.agility, sol.exp_agility, _ = apply_exp(sol.agility, sol.exp_agility, amount * 0.22)
        sol.wits, sol.exp_wits, _ = apply_exp(sol.wits, sol.exp_wits, amount * 0.18)
        pkey = "bow"
        cur = sol.prof.get(pkey, 0.0)
        pool = sol.exp_prof.get(pkey, 0.0)
        cur, pool, _ = apply_exp(cur, pool, amount * 0.9)
        sol.prof[pkey] = cur
        sol.exp_prof[pkey] = pool
        sol.sync_hp_cap()

    def protagonist_action_phase(
        self, rng: random.Random, action: str, siege_defense: bool
    ) -> None:
        if action not in ("melee", "ranged"):
            return
        hero = self._protagonist()
        if hero is None or not hero.alive:
            return
        if action == "melee":
            pos = self.positions.get(hero.id)
            if pos is None:
                return
            r, c = pos
            has_p, has_e = self._factions_in_cell(r, c)
            if not (has_p and has_e):
                self.log.append(
                    f"【主角】{hero.name} 未接战（近战需与敌在同一六角格；推进靠 tick 自动接敌）"
                )
                return
            enemies: List[Soldier] = []
            owners: Dict[str, Tuple[str, str]] = {}
            for u in self._cell(r, c).units:
                army = self.armies[u.army_id]
                sol = self.soldiers[u.soldier_id]
                if not sol.alive:
                    continue
                owners[sol.id] = (u.army_id, army.faction)
                if army.faction == "enemy":
                    enemies.append(sol)
            if not enemies:
                return
            tgt = rng.choice(enemies)
            terrain = self._cell(r, c).terrain
            aid = self.army_for_soldier(hero.id).id
            dmg = self._roll_damage(hero, tgt, terrain, rng, self._officer_bonus(aid)) * 1.12
            was_alive = tgt.alive
            self._apply_damage(tgt, dmg, rng, announce_death=False)
            hero.add_fatigue(1.8)
            self._grant_combat_exp(hero, 0.42)
            if was_alive and not tgt.alive:
                self.log.append(f"【主角】{hero.name} 斩杀 {tgt.name}！（近战）")
            else:
                self.log.append(f"【主角】{hero.name} 劈砍 {tgt.name}，伤 {dmg:.0f}")
        else:
            hp = self.positions.get(hero.id)
            if hp is None:
                return
            hr, _hc = hp
            pool: List[Soldier] = []
            for sid, (er, _ec) in self.positions.items():
                sol = self.soldiers.get(sid)
                if not sol or not sol.alive or sol.faction != "enemy":
                    continue
                if er < hr:
                    pool.append(sol)
            if not pool:
                for sol in self.soldiers.values():
                    if sol.alive and sol.faction == "enemy":
                        pool.append(sol)
            if not pool:
                self.log.append("【主角】箭下已无立锥之敌")
                return
            tgt = rng.choice(pool)
            tr, tc = self.positions[tgt.id]
            tterrain = self._cell(tr, tc).terrain
            dmg = self._roll_ranged_damage(hero, tgt, tterrain, rng, siege_defense)
            was_alive = tgt.alive
            self._apply_damage(tgt, dmg, rng, announce_death=False)
            hero.add_fatigue(1.05)
            self._grant_ranged_exp(hero, 0.52)
            thrill = dmg >= 22.0 or (siege_defense and dmg >= 18.0)
            if thrill and rng.random() < 0.45:
                self.log.append(f"【主角】弦响箭至！{tgt.name} 受创 {dmg:.0f}（痛快！）")
            else:
                self.log.append(f"【主角】箭射 {tgt.name}，伤 {dmg:.0f}")
            if was_alive and not tgt.alive:
                self.log.append(f"【主角】{tgt.name} 中箭倒地")

    def _apply_damage(
        self, target: Soldier, dmg: float, rng: random.Random, *, announce_death: bool = True
    ) -> None:
        target.hp -= dmg
        if target.hp <= 0:
            target.hp = 0
            target.alive = False
            if announce_death:
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

    def tick(
        self,
        rng: random.Random,
        *,
        hero_action: str = "hold",
        siege_defense: bool = False,
    ) -> None:
        self.tick_index += 1
        self.log = self.log[-80:]
        self.protagonist_action_phase(rng, hero_action, siege_defense)
        self.movement_phase(rng, siege_defense)
        self.rotation_phase(rng, siege_defense)
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
