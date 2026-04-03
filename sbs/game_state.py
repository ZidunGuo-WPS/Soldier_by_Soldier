from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sbs.army import Army
from sbs.battle_sim import BattleState, Cell, Terrain, UnitRef
from sbs.equipment import Gear
from sbs.officer import Officer, OfficerRank
from sbs.scaling import apply_exp, enemy_morale_from_training
from sbs.soldier import Soldier
from sbs.wounds import BodyPart, Wound, WoundSeverity

PROTAGONIST_ID = "protagonist"


@dataclass
class GameState:
    """Campaign shell + one active battle (expand later for China map)."""

    rng_seed: int
    campaign_hours: float = 0.0
    battle_tick_speed: int = 1  # 1..3 auto-tick rate when会战
    campaign_step_speed: int = 1  # scales hour buttons
    battle: BattleState = field(default_factory=lambda: _dummy_battle())
    mode: str = "battle"  # "strategy" | "battle"
    fight_to_death: bool = False
    allow_rotation: bool = True
    # 主角：每 tick 执行一次指令（近战/射箭/待命）；守城时主角不自动推进、射箭有加成
    hero_stance: str = "hold"  # "melee" | "ranged" | "hold"
    siege_mode: bool = False
    battle_xp_settled: bool = False  # 本会战是否已结算主角战后经验

    def rng(self) -> random.Random:
        return random.Random(self.rng_seed + self.battle.tick_index * 9973)

    def apply_player_doctrine(self) -> None:
        for a in self.battle.armies.values():
            if a.faction == "player":
                a.fight_to_death = self.fight_to_death
                a.allow_fatigue_rotation = self.allow_rotation


def _dummy_battle() -> BattleState:
    return BattleState(1, 1, [[Cell()]], {}, {}, {})


def _make_soldier(d: Dict[str, Any]) -> Soldier:
    prof = {k: float(v) for k, v in d.get("prof", {}).items()}
    exp_prof = {k: float(v) for k, v in d.get("exp_prof", {}).items()}
    wounds: List[Wound] = []
    for w in d.get("wounds", []):
        wounds.append(
            Wound(
                BodyPart(w["part"]),
                WoundSeverity(w["severity"]),
                float(w.get("days_to_recover", 0.0)),
            )
        )
    gear = [Gear(x["slot"], x["name"], int(x.get("tier", 2))) for x in d.get("gear", [])]
    return Soldier(
        id=d["id"],
        name=d["name"],
        faction=d["faction"],
        is_elite_name=bool(d.get("is_elite_name", False)),
        is_protagonist=bool(d.get("is_protagonist", False)),
        zone_key=d.get("zone_key"),
        strength=float(d.get("strength", 10)),
        agility=float(d.get("agility", 10)),
        endurance=float(d.get("endurance", 10)),
        vitality=float(d.get("vitality", 10)),
        wits=float(d.get("wits", 8)),
        exp_strength=float(d.get("exp_strength", 0)),
        exp_agility=float(d.get("exp_agility", 0)),
        exp_endurance=float(d.get("exp_endurance", 0)),
        exp_vitality=float(d.get("exp_vitality", 0)),
        exp_wits=float(d.get("exp_wits", 0)),
        prof=prof,
        exp_prof=exp_prof,
        hp=float(d["hp"]),
        hp_max=float(d.get("hp_max", d["hp"])),
        fatigue=float(d.get("fatigue", 0)),
        battles_fought=float(d.get("battles_fought", 0)),
        training_hours=float(d.get("training_hours", 0)),
        form_bias=float(d.get("form_bias", 0)),
        wounds=wounds,
        gear=gear,
        alive=bool(d.get("alive", True)),
    )


def _soldier_to_dict(s: Soldier) -> Dict[str, Any]:
    return {
        "id": s.id,
        "name": s.name,
        "faction": s.faction,
        "is_elite_name": s.is_elite_name,
        "is_protagonist": s.is_protagonist,
        "zone_key": s.zone_key,
        "strength": s.strength,
        "agility": s.agility,
        "endurance": s.endurance,
        "vitality": s.vitality,
        "wits": s.wits,
        "exp_strength": s.exp_strength,
        "exp_agility": s.exp_agility,
        "exp_endurance": s.exp_endurance,
        "exp_vitality": s.exp_vitality,
        "exp_wits": s.exp_wits,
        "prof": dict(s.prof),
        "exp_prof": dict(s.exp_prof),
        "hp": s.hp,
        "hp_max": s.hp_max,
        "fatigue": s.fatigue,
        "battles_fought": s.battles_fought,
        "training_hours": s.training_hours,
        "form_bias": s.form_bias,
        "wounds": [
            {"part": w.part.value, "severity": w.severity.value, "days_to_recover": w.days_to_recover}
            for w in s.wounds
        ],
        "gear": [{"slot": g.slot, "name": g.name, "tier": g.tier} for g in s.gear],
        "alive": s.alive,
    }


def _officer_from_dict(d: Optional[Dict[str, Any]]) -> Optional[Officer]:
    if not d:
        return None
    return Officer(
        id=d["id"],
        name=d["name"],
        rank=OfficerRank(d.get("rank", "none")),
        leadership=float(d.get("leadership", 15)),
        command=float(d.get("command", 12)),
        tactics=float(d.get("tactics", 10)),
    )


def _officer_to_dict(o: Optional[Officer]) -> Optional[Dict[str, Any]]:
    if o is None:
        return None
    return {
        "id": o.id,
        "name": o.name,
        "rank": o.rank.value,
        "leadership": o.leadership,
        "command": o.command,
        "tactics": o.tactics,
    }


def _army_from_dict(d: Dict[str, Any]) -> Army:
    return Army(
        id=d["id"],
        name=d["name"],
        faction=d["faction"],
        soldier_ids=list(d.get("soldier_ids", [])),
        commander=_officer_from_dict(d.get("commander")),
        fight_to_death=bool(d.get("fight_to_death", False)),
        allow_fatigue_rotation=bool(d.get("allow_fatigue_rotation", True)),
    )


def _army_to_dict(a: Army) -> Dict[str, Any]:
    return {
        "id": a.id,
        "name": a.name,
        "faction": a.faction,
        "soldier_ids": list(a.soldier_ids),
        "commander": _officer_to_dict(a.commander),
        "fight_to_death": a.fight_to_death,
        "allow_fatigue_rotation": a.allow_fatigue_rotation,
    }


def _battle_from_dict(d: Dict[str, Any]) -> BattleState:
    w, h = int(d["width"]), int(d["height"])
    cells_data = d["cells"]
    cells: List[List[Cell]] = []
    for r in range(h):
        row: List[Cell] = []
        for c in range(w):
            cd = cells_data[r][c]
            t = Terrain(cd.get("terrain", "plain"))
            units = [UnitRef(u["army_id"], u["soldier_id"]) for u in cd.get("units", [])]
            row.append(Cell(t, units))
        cells.append(row)
    soldiers = {k: _make_soldier(v) for k, v in d["soldiers"].items()}
    armies = {k: _army_from_dict(v) for k, v in d["armies"].items()}
    positions: Dict[str, Tuple[int, int]] = {}
    for r in range(h):
        for c in range(w):
            for u in cells[r][c].units:
                positions[u.soldier_id] = (r, c)
    b = BattleState(
        width=w,
        height=h,
        cells=cells,
        soldiers=soldiers,
        armies=armies,
        positions=positions,
        log=list(d.get("log", [])),
        tick_index=int(d.get("tick_index", 0)),
    )
    return b


def _battle_to_dict(b: BattleState) -> Dict[str, Any]:
    cells = []
    for r in range(b.height):
        row = []
        for c in range(b.width):
            cell = b.cells[r][c]
            row.append(
                {
                    "terrain": cell.terrain.value,
                    "units": [{"army_id": u.army_id, "soldier_id": u.soldier_id} for u in cell.units],
                }
            )
        cells.append(row)
    return {
        "width": b.width,
        "height": b.height,
        "tick_index": b.tick_index,
        "cells": cells,
        "soldiers": {k: _soldier_to_dict(v) for k, v in b.soldiers.items()},
        "armies": {k: _army_to_dict(v) for k, v in b.armies.items()},
        "log": b.log[-200:],
    }


def game_to_dict(g: GameState) -> Dict[str, Any]:
    return {
        "version": 1,
        "rng_seed": g.rng_seed,
        "campaign_hours": g.campaign_hours,
        "battle_tick_speed": g.battle_tick_speed,
        "campaign_step_speed": g.campaign_step_speed,
        "mode": g.mode,
        "fight_to_death": g.fight_to_death,
        "allow_rotation": g.allow_rotation,
        "hero_stance": g.hero_stance,
        "siege_mode": g.siege_mode,
        "battle_xp_settled": g.battle_xp_settled,
        "battle": _battle_to_dict(g.battle),
    }


def game_from_dict(d: Dict[str, Any]) -> GameState:
    g = GameState(
        rng_seed=int(d.get("rng_seed", 1)),
        campaign_hours=float(d.get("campaign_hours", 0)),
        battle_tick_speed=int(d.get("battle_tick_speed", 1)),
        campaign_step_speed=int(d.get("campaign_step_speed", 1)),
        battle=_battle_from_dict(d["battle"]),
        mode=str(d.get("mode", "battle")),
        fight_to_death=bool(d.get("fight_to_death", False)),
        allow_rotation=bool(d.get("allow_rotation", True)),
        hero_stance=str(d.get("hero_stance", "hold")),
        siege_mode=bool(d.get("siege_mode", False)),
        battle_xp_settled=bool(d.get("battle_xp_settled", False)),
    )
    if g.hero_stance not in ("melee", "ranged", "hold"):
        g.hero_stance = "hold"
    g.apply_player_doctrine()
    return g


def save_game(g: GameState, path: Path) -> None:
    path.write_text(json.dumps(game_to_dict(g), ensure_ascii=False, indent=2), encoding="utf-8")


def load_game(path: Path) -> GameState:
    data = json.loads(path.read_text(encoding="utf-8"))
    return game_from_dict(data)


def new_demo_game(seed: int = 7) -> GameState:
    rng = random.Random(seed)
    soldiers: Dict[str, Soldier] = {}
    p_ids: List[str] = []
    for i in range(9):
        sid = f"p{i+1}"
        p_ids.append(sid)
        soldiers[sid] = Soldier(
            id=sid,
            name=f"锐卒{i+1}",
            faction="player",
            strength=11 + rng.random() * 3,
            agility=10 + rng.random() * 2,
            endurance=12 + rng.random() * 2,
            vitality=11 + rng.random() * 2,
            prof={"one_handed": 8 + rng.random() * 4, "polearm": 2, "bow": 1 + rng.random() * 2},
            fatigue=rng.random() * 8,
            form_bias=rng.uniform(-0.1, 0.1),
            gear=[Gear("weapon", "环首刀", 3), Gear("body", "皮甲", 2)],
        )
    soldiers[PROTAGONIST_ID] = Soldier(
        id=PROTAGONIST_ID,
        name="你",
        faction="player",
        is_elite_name=True,
        is_protagonist=True,
        strength=12 + rng.random() * 2,
        agility=11 + rng.random() * 2,
        endurance=12 + rng.random() * 2,
        vitality=12 + rng.random() * 2,
        wits=10 + rng.random() * 2,
        prof={
            "one_handed": 9 + rng.random() * 3,
            "bow": 10 + rng.random() * 4,
            "polearm": 2,
        },
        fatigue=rng.random() * 5,
        form_bias=rng.uniform(-0.08, 0.08),
        gear=[
            Gear("weapon", "环首刀", 3),
            Gear("ranged", "角弓", 4),
            Gear("body", "皮甲", 2),
        ],
    )
    p_ids.insert(4, PROTAGONIST_ID)
    e_ids: List[str] = []
    for i in range(12):
        sid = f"e{i+1}"
        e_ids.append(sid)
        soldiers[sid] = Soldier(
            id=sid,
            name=f"敌兵{i+1}",
            faction="enemy",
            strength=9 + rng.random() * 2,
            agility=9 + rng.random() * 2,
            endurance=10 + rng.random() * 2,
            vitality=10 + rng.random() * 2,
            prof={"one_handed": 5 + rng.random() * 3},
            battles_fought=rng.random() * 4,
            training_hours=rng.random() * 20,
            fatigue=rng.random() * 6,
            form_bias=rng.uniform(-0.1, 0.1),
            gear=[Gear("weapon", "矛", 2), Gear("body", "布衣", 1)],
        )
    for s in soldiers.values():
        s.sync_hp_cap()

    commander = Officer(
        id="off1",
        name="陈百户",
        rank=OfficerRank.BAIHU,
        leadership=22.0,
        command=18.0,
        tactics=14.0,
    )
    armies: Dict[str, Army] = {
        "a_player": Army(
            id="a_player",
            name="我军",
            faction="player",
            soldier_ids=p_ids,
            commander=commander,
            fight_to_death=False,
            allow_fatigue_rotation=True,
        ),
        "a_enemy": Army(
            id="a_enemy",
            name="敌军",
            faction="enemy",
            soldier_ids=e_ids,
            commander=None,
            fight_to_death=False,
            allow_fatigue_rotation=True,
        ),
    }
    w, h = 8, 5
    cells: List[List[Cell]] = [[Cell() for _ in range(w)] for _ in range(h)]
    battle = BattleState(w, h, cells, soldiers, armies, {})
    battle.setup_demo_skirmish(rng)
    g = GameState(rng_seed=seed, battle=battle, battle_xp_settled=False)
    g.apply_player_doctrine()
    return g


def grant_post_battle_xp(state: GameState, outcome_zh: str) -> None:
    """会战结束时结算主角经验（战斗中已有近战/射箭即时成长，此处为总结算）。"""
    hero = state.battle.soldiers.get(PROTAGONIST_ID)
    if hero is None:
        for s in state.battle.soldiers.values():
            if s.is_protagonist and s.faction == "player":
                hero = s
                break
    if hero is None or not hero.alive:
        return
    mult = 1.0 if outcome_zh == "我军胜" else 0.4
    t = state.battle.tick_index
    base = 3.8 * mult * (1.0 + min(2.5, t * 0.018))
    hero.strength, hero.exp_strength, _ = apply_exp(hero.strength, hero.exp_strength, base * 0.2)
    hero.agility, hero.exp_agility, _ = apply_exp(hero.agility, hero.exp_agility, base * 0.18)
    hero.endurance, hero.exp_endurance, _ = apply_exp(hero.endurance, hero.exp_endurance, base * 0.2)
    hero.vitality, hero.exp_vitality, _ = apply_exp(hero.vitality, hero.exp_vitality, base * 0.18)
    hero.wits, hero.exp_wits, _ = apply_exp(hero.wits, hero.exp_wits, base * 0.12)
    for key in ("one_handed", "bow"):
        cur = hero.prof.get(key, 0.0)
        pool = hero.exp_prof.get(key, 0.0)
        cur, pool, _ = apply_exp(cur, pool, base * 0.35)
        hero.prof[key] = cur
        hero.exp_prof[key] = pool
    hero.battles_fought += 1.0
    hero.sync_hp_cap()
    state.battle.log.append(
        f"【主角战后结算】{hero.name} 获得历练（{outcome_zh}，约 {base:.1f} 基准）"
    )


def army_average_fatigue(battle: BattleState, army: Army) -> float:
    alive_ids = [sid for sid in army.soldier_ids if battle.soldiers.get(sid) and battle.soldiers[sid].alive]
    if not alive_ids:
        return 0.0
    tot = 0.0
    for sid in alive_ids:
        s = battle.soldiers[sid]
        tot += s.fatigue / max(1.0, s.fatigue_max())
    return tot / len(alive_ids)


def army_average_enemy_morale(battle: BattleState, army: Army) -> float:
    if army.faction != "enemy":
        return 0.0
    alive_ids = [sid for sid in army.soldier_ids if battle.soldiers.get(sid) and battle.soldiers[sid].alive]
    if not alive_ids:
        return 0.0
    tot = 0.0
    for sid in alive_ids:
        s = battle.soldiers[sid]
        tot += enemy_morale_from_training(s.battles_fought, s.training_hours)
    return tot / len(alive_ids)
