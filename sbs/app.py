"""
Main window: 战略占位 + 会战六边形格 + 宏观色条 + 战报。
操作：鼠标点按钮；会战里可自动推进（速度档位）。
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import List, Optional, Tuple

import pygame

from sbs.battle_sim import Terrain
from sbs.fonts import pick_cjk_font
from sbs.game_state import (
    PROTAGONIST_ID,
    GameState,
    army_average_enemy_morale,
    army_average_fatigue,
    grant_post_battle_xp,
    load_game,
    new_demo_game,
    save_game,
)
from sbs.soldier import Soldier
from sbs.wounds import PART_LABEL_ZH, WoundSeverity

W, H = 1280, 720
SAVE_PATH = Path(__file__).resolve().parent.parent / "save_game.json"

BG = (26, 30, 36)
PANEL = (44, 50, 60)
ACCENT = (210, 175, 110)
TEXT = (210, 215, 225)
MUTED = (130, 138, 150)
GREEN = (90, 180, 120)
BLUE = (100, 160, 240)
RED = (230, 100, 100)
BTN_SHADOW = (10, 12, 16)
BTN_FACE = (52, 58, 68)
BTN_FACE_ACTIVE = (58, 78, 62)
BTN_FACE_PRESS = (38, 44, 52)
BTN_FACE_ACTIVE_PRESS = (44, 62, 48)
BTN_RIM = (28, 32, 40)
CLICK_FLASH_MS = 140


def _terrain_color(t: Terrain) -> Tuple[int, int, int]:
    if t == Terrain.RIVER:
        return (45, 85, 140)
    if t == Terrain.HIGH:
        return (110, 92, 70)
    return (52, 58, 48)


def _draw_bar(
    surf: pygame.Surface,
    rect: pygame.Rect,
    ratio: float,
    color: Tuple[int, int, int],
    bg: Tuple[int, int, int] = (30, 34, 40),
) -> None:
    ratio = max(0.0, min(1.0, ratio))
    pygame.draw.rect(surf, bg, rect)
    inner = pygame.Rect(rect.x + 2, rect.y + 2, int((rect.width - 4) * ratio), rect.height - 4)
    pygame.draw.rect(surf, color, inner)


def _tup_add(a: Tuple[int, int, int], d: int) -> Tuple[int, int, int]:
    return tuple(max(0, min(255, x + d)) for x in a)


def _draw_soft_button(
    surf: pygame.Surface,
    rect: pygame.Rect,
    label: pygame.Surface,
    *,
    active: bool = False,
    pressed: bool = False,
    hovered: bool = False,
    accent_label: bool = False,
) -> None:
    """立体按钮：底层阴影 + 圆角面 + 斜面高光/暗边；pressed 时略下沉并反转斜面。"""
    face = BTN_FACE_ACTIVE if active else BTN_FACE
    if active and pressed:
        face = BTN_FACE_ACTIVE_PRESS
    elif pressed:
        face = BTN_FACE_PRESS
    elif hovered:
        face = _tup_add(BTN_FACE_ACTIVE if active else BTN_FACE, 12)

    sh = rect.copy()
    sh.x += 2
    sh.y += 2
    pygame.draw.rect(surf, BTN_SHADOW, sh, border_radius=5)

    r = rect.copy()
    if pressed:
        r.x += 1
        r.y += 1

    pygame.draw.rect(surf, BTN_RIM, r.inflate(4, 4), border_radius=7, width=1)
    pygame.draw.rect(surf, face, r, border_radius=5)

    hi = _tup_add(face, 26)
    lo = _tup_add(face, -20)
    t = 1
    if not pressed:
        pygame.draw.line(surf, hi, (r.x + 3, r.y + 2), (r.right - 4, r.y + 2), t)
        pygame.draw.line(surf, hi, (r.x + 2, r.y + 3), (r.x + 2, r.bottom - 4), t)
        pygame.draw.line(surf, lo, (r.right - 3, r.y + 3), (r.right - 3, r.bottom - 4), t)
        pygame.draw.line(surf, lo, (r.x + 3, r.bottom - 3), (r.right - 4, r.bottom - 3), t)
    else:
        pygame.draw.line(surf, lo, (r.x + 3, r.y + 2), (r.right - 4, r.y + 2), t)
        pygame.draw.line(surf, lo, (r.x + 2, r.y + 3), (r.x + 2, r.bottom - 4), t)
        pygame.draw.line(surf, hi, (r.right - 3, r.y + 3), (r.right - 3, r.bottom - 4), t)
        pygame.draw.line(surf, hi, (r.x + 3, r.bottom - 3), (r.right - 4, r.bottom - 3), t)

    tc = ACCENT if accent_label or active else TEXT
    if pressed:
        tc = _tup_add(tc, -18)
    surf.blit(label, (r.centerx - label.get_width() // 2, r.centery - label.get_height() // 2))


# odd-r 存储与 battle_sim 一致：列向右、行向下，奇数行列向右错半格；点状朝上的六边形像素布局。
def _hex_center_oddr_pt(col: int, row: int, radius: float) -> Tuple[float, float]:
    x = radius * math.sqrt(3) * (col + 0.5 * (row & 1))
    y = radius * 1.5 * row
    return x, y


def _hex_vertices_pointy(cx: float, cy: float, radius: float) -> List[Tuple[int, int]]:
    pts: List[Tuple[int, int]] = []
    for i in range(6):
        ang = math.pi / 3 * i - math.pi / 2
        pts.append((int(cx + radius * math.cos(ang)), int(cy + radius * math.sin(ang))))
    return pts


def _hex_grid_bbox(cols: int, rows: int, radius: float) -> Tuple[float, float, float, float]:
    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")
    for r in range(rows):
        for c in range(cols):
            cx, cy = _hex_center_oddr_pt(c, r, radius)
            for px, py in _hex_vertices_pointy(cx, cy, radius):
                min_x = min(min_x, float(px))
                max_x = max(max_x, float(px))
                min_y = min(min_y, float(py))
                max_y = max(max_y, float(py))
    return min_x, min_y, max_x, max_y


def _fit_hex_radius(cols: int, rows: int, max_w: float, max_h: float) -> float:
    lo, hi = 6.0, 120.0
    best = lo
    for _ in range(48):
        mid = (lo + hi) * 0.5
        mn_x, mn_y, mx_x, mx_y = _hex_grid_bbox(cols, rows, mid)
        bw, bh = mx_x - mn_x, mx_y - mn_y
        if bw <= max_w and bh <= max_h:
            best = mid
            lo = mid
        else:
            hi = mid
    return best


def _hex_screen_xy(
    col: int, row: int, radius: float, origin_x: float, origin_y: float
) -> Tuple[float, float]:
    cx, cy = _hex_center_oddr_pt(col, row, radius)
    return cx + origin_x, cy + origin_y


def _wound_summary_zh(sol: Soldier) -> str:
    if not sol.wounds:
        return "无伤"
    sev_zh = {
        WoundSeverity.LIGHT: "轻",
        WoundSeverity.HEAVY: "重",
        WoundSeverity.PERMANENT: "残",
    }
    chunks = []
    for w in sol.wounds[-4:]:
        chunks.append(f"{PART_LABEL_ZH.get(w.part, '?')}{sev_zh.get(w.severity, '')}")
    return " ".join(chunks)


def _player_alive_sorted(state: GameState) -> List[Soldier]:
    b = state.battle
    out: List[Soldier] = []
    for army in b.armies.values():
        if army.faction != "player":
            continue
        for sid in army.soldier_ids:
            s = b.soldiers.get(sid)
            if s and s.alive:
                out.append(s)
    out.sort(key=lambda x: (0 if x.is_protagonist else 1, x.name, x.id))
    return out


# 顶栏与主要可点区域（与绘制、命中一致）
TOP_STRATEGY_RECT = pygame.Rect(18, 5, 98, 38)
TOP_BATTLE_RECT = pygame.Rect(118, 5, 98, 38)
TOP_FT_RECT = pygame.Rect(226, 5, 172, 38)
TOP_ROT_RECT = pygame.Rect(404, 5, 190, 38)
TOP_SPD_RECT = pygame.Rect(602, 5, 124, 38)
TOP_STEP_RECT = pygame.Rect(730, 5, 176, 38)
MANUAL_TICK_RECT = pygame.Rect(16, 49, 152, 36)
# 会战页右侧：我军列表滚动区、下方单位详情、战报（与事件处理共用几何）
PLAYER_LIST_ROW_H = 48
PLAYER_LIST_RECT = pygame.Rect(642, 300, 626, 178)
PLAYER_DETAIL_RECT = pygame.Rect(642, 486, 626, 118)
NEW_BATTLE_BTN_RECT = pygame.Rect(188, 352, 284, 48)
HERO_MELEE_RECT = pygame.Rect(18, 90, 74, 32)
HERO_RANGED_RECT = pygame.Rect(98, 90, 74, 32)
HERO_HOLD_RECT = pygame.Rect(178, 90, 62, 32)
SIEGE_TOGGLE_RECT = pygame.Rect(246, 90, 136, 32)
STRAT_H1_RECT = pygame.Rect(18, 54, 108, 34)
STRAT_H6_RECT = pygame.Rect(132, 54, 138, 34)
STRAT_H24_RECT = pygame.Rect(274, 54, 138, 34)


def _player_list_scroll_bounds(state: GameState) -> Tuple[int, int]:
    soldiers = _player_alive_sorted(state)
    line_h = PLAYER_LIST_ROW_H
    header = 22
    inner_h = PLAYER_LIST_RECT.height - 34
    content_h = header + len(soldiers) * line_h
    max_scroll = max(0, content_h - inner_h)
    return content_h, max_scroll


def _player_list_hit_soldier_id(
    mx: int, my: int, scroll_y: int, state: GameState
) -> Optional[str]:
    r = PLAYER_LIST_RECT
    if not r.collidepoint(mx, my):
        return None
    inner = pygame.Rect(r.x + 6, r.y + 28, r.width - 12, r.height - 34)
    if not inner.collidepoint(mx, my):
        return None
    soldiers = _player_alive_sorted(state)
    rel_y = my - inner.y + scroll_y - 22
    if rel_y < 0:
        return None
    idx = rel_y // PLAYER_LIST_ROW_H
    if 0 <= idx < len(soldiers):
        return soldiers[idx].id
    return None


def _normalize_detail_selection(state: GameState, sid: Optional[str]) -> Optional[str]:
    if sid is None:
        return None
    sol = state.battle.soldiers.get(sid)
    if sol and sol.alive and sol.faction == "player":
        return sid
    hero = state.battle.soldiers.get(PROTAGONIST_ID)
    if hero and hero.alive:
        return PROTAGONIST_ID
    alive = _player_alive_sorted(state)
    return alive[0].id if alive else None


def _gear_one_line(sol: Soldier) -> str:
    if not sol.gear:
        return "无装"
    return " ".join(f"{g.name}T{g.tier}" for g in sol.gear)


def draw_top_bar(
    screen: pygame.Surface,
    state: GameState,
    font_m: pygame.font.Font,
    font_s: pygame.font.Font,
    mouse_xy: Tuple[int, int],
    press_id: Optional[str],
    press_active: bool,
) -> None:
    mx, my = mouse_xy

    def flash(bid: str) -> bool:
        return press_active and press_id == bid

    pygame.draw.rect(screen, (32, 36, 42), (0, 0, W, 48))
    pygame.draw.line(screen, (18, 20, 26), (0, 47), (W, 47), 2)

    _draw_soft_button(
        screen,
        TOP_STRATEGY_RECT,
        font_m.render("战略", True, TEXT),
        active=state.mode == "strategy",
        pressed=flash("top_strategy"),
        hovered=TOP_STRATEGY_RECT.collidepoint(mx, my),
        accent_label=state.mode == "strategy",
    )
    _draw_soft_button(
        screen,
        TOP_BATTLE_RECT,
        font_m.render("会战", True, TEXT),
        active=state.mode == "battle",
        pressed=flash("top_battle"),
        hovered=TOP_BATTLE_RECT.collidepoint(mx, my),
        accent_label=state.mode == "battle",
    )

    ftd = "死战不退 · 开" if state.fight_to_death else "死战不退 · 关"
    rot = "后撤换气 · 开" if state.allow_rotation else "后撤换气 · 关"
    spd_names = ["会战自动 · 停", "会战自动 · 慢", "会战自动 · 中", "会战自动 · 快"]
    step_lbl = f"战略步进 ×{state.campaign_step_speed}"

    _draw_soft_button(
        screen,
        TOP_FT_RECT,
        font_s.render(ftd, True, TEXT),
        active=state.fight_to_death,
        pressed=flash("top_ftd"),
        hovered=TOP_FT_RECT.collidepoint(mx, my),
    )
    _draw_soft_button(
        screen,
        TOP_ROT_RECT,
        font_s.render(rot, True, TEXT),
        active=state.allow_rotation,
        pressed=flash("top_rot"),
        hovered=TOP_ROT_RECT.collidepoint(mx, my),
    )
    _draw_soft_button(
        screen,
        TOP_SPD_RECT,
        font_s.render(spd_names[state.battle_tick_speed], True, TEXT),
        active=state.battle_tick_speed > 0,
        pressed=flash("top_spd"),
        hovered=TOP_SPD_RECT.collidepoint(mx, my),
    )
    _draw_soft_button(
        screen,
        TOP_STEP_RECT,
        font_s.render(step_lbl, True, TEXT),
        active=state.campaign_step_speed > 1,
        pressed=flash("top_step"),
        hovered=TOP_STEP_RECT.collidepoint(mx, my),
    )


def run() -> None:
    pygame.init()
    pygame.display.set_caption("Soldier by Soldier")
    screen = pygame.display.set_mode((W, H))
    clock = pygame.time.Clock()

    font_l = pick_cjk_font(22)
    font_m = pick_cjk_font(17)
    font_s = pick_cjk_font(14)

    state = new_demo_game(11)
    auto_ms = 0.0
    player_list_scroll = 0
    selected_detail_id: Optional[str] = PROTAGONIST_ID
    running = True

    def tick_battle_once() -> None:
        if battle_outcome(state):
            return
        state.battle.tick(
            state.rng(),
            hero_action=state.hero_stance,
            siege_defense=state.siege_mode,
        )
        outcome = battle_outcome(state)
        if outcome:
            state.battle.log.append(f"—— 会战结束: {outcome} ——")
            if not state.battle_xp_settled:
                grant_post_battle_xp(state, outcome)
                state.battle_xp_settled = True

    def battle_outcome(g: GameState) -> Optional[str]:
        p, e = g.battle.alive_counts()
        if p <= 0:
            return "敌军胜"
        if e <= 0:
            return "我军胜"
        return None

    def start_new_demo_battle() -> None:
        nonlocal state, player_list_scroll, auto_ms, selected_detail_id
        seed = (state.rng_seed + 7919) % 1_000_000
        mode = state.mode
        bts = state.battle_tick_speed
        css = state.campaign_step_speed
        ch = state.campaign_hours
        ftd = state.fight_to_death
        rot = state.allow_rotation
        state = new_demo_game(seed)
        state.mode = mode
        state.battle_tick_speed = bts
        state.campaign_step_speed = css
        state.campaign_hours = ch
        state.fight_to_death = ftd
        state.allow_rotation = rot
        state.apply_player_doctrine()
        state.battle_xp_settled = False
        player_list_scroll = 0
        auto_ms = 0.0
        selected_detail_id = PROTAGONIST_ID
        state.battle.log.append("—— 新开演示会战 ——")

    def handle_click(mx: int, my: int) -> Optional[str]:
        nonlocal state, player_list_scroll, selected_detail_id
        if state.mode == "battle" and battle_outcome(state) and NEW_BATTLE_BTN_RECT.collidepoint(mx, my):
            start_new_demo_battle()
            return "new_battle"
        if TOP_STRATEGY_RECT.collidepoint(mx, my):
            state.mode = "strategy"
            return "top_strategy"
        if TOP_BATTLE_RECT.collidepoint(mx, my):
            state.mode = "battle"
            return "top_battle"
        if TOP_FT_RECT.collidepoint(mx, my):
            state.fight_to_death = not state.fight_to_death
            state.apply_player_doctrine()
            return "top_ftd"
        if TOP_ROT_RECT.collidepoint(mx, my):
            state.allow_rotation = not state.allow_rotation
            state.apply_player_doctrine()
            return "top_rot"
        if TOP_SPD_RECT.collidepoint(mx, my):
            state.battle_tick_speed = (state.battle_tick_speed + 1) % 4
            return "top_spd"
        if TOP_STEP_RECT.collidepoint(mx, my):
            state.campaign_step_speed = (state.campaign_step_speed % 3) + 1
            return "top_step"
        if state.mode == "battle" and not battle_outcome(state):
            pick = _player_list_hit_soldier_id(mx, my, player_list_scroll, state)
            if pick is not None:
                selected_detail_id = pick
                return "player_pick"
            if MANUAL_TICK_RECT.collidepoint(mx, my):
                tick_battle_once()
                return "manual_tick"
            if HERO_MELEE_RECT.collidepoint(mx, my):
                state.hero_stance = "melee"
                return "hero_melee"
            if HERO_RANGED_RECT.collidepoint(mx, my):
                state.hero_stance = "ranged"
                return "hero_ranged"
            if HERO_HOLD_RECT.collidepoint(mx, my):
                state.hero_stance = "hold"
                return "hero_hold"
            if SIEGE_TOGGLE_RECT.collidepoint(mx, my):
                state.siege_mode = not state.siege_mode
                return "siege_toggle"
        if state.mode == "strategy":
            mult = state.campaign_step_speed
            if STRAT_H1_RECT.collidepoint(mx, my):
                state.campaign_hours += 1.0 * mult
                return "strat_h1"
            if STRAT_H6_RECT.collidepoint(mx, my):
                state.campaign_hours += 6.0 * mult
                return "strat_h6"
            if STRAT_H24_RECT.collidepoint(mx, my):
                state.campaign_hours += 24.0 * mult
                return "strat_h24"
        return None

    ui_press_id: Optional[str] = None
    ui_press_until = 0

    while running:
        dt = clock.tick(60)
        now_ms = pygame.time.get_ticks()
        if ui_press_id is not None and now_ms >= ui_press_until:
            ui_press_id = None
        press_active = ui_press_id is not None and now_ms < ui_press_until
        if state.mode == "battle" and state.battle_tick_speed > 0:
            if not battle_outcome(state):
                spd = {1: 900, 2: 500, 3: 260}[min(3, max(1, state.battle_tick_speed))]
                auto_ms += dt
                while auto_ms >= spd:
                    auto_ms -= spd
                    tick_battle_once()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_F5:
                    save_game(state, SAVE_PATH)
                    state.battle.log.append(f"已存档 {SAVE_PATH.name}")
                elif event.key == pygame.K_F9 and SAVE_PATH.exists():
                    state = load_game(SAVE_PATH)
                    player_list_scroll = 0
                    selected_detail_id = _normalize_detail_selection(state, PROTAGONIST_ID)
                    state.battle.log.append("已读档")
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                bid = handle_click(mx, my)
                if bid is not None:
                    ui_press_id = bid
                    ui_press_until = pygame.time.get_ticks() + CLICK_FLASH_MS
            elif event.type == pygame.MOUSEWHEEL and state.mode == "battle":
                mx, my = pygame.mouse.get_pos()
                if PLAYER_LIST_RECT.collidepoint(mx, my):
                    _, max_scroll = _player_list_scroll_bounds(state)
                    player_list_scroll = max(0, min(max_scroll, player_list_scroll - event.y * 24))

        screen.fill(BG)

        mouse_xy = pygame.mouse.get_pos()
        draw_top_bar(screen, state, font_m, font_s, mouse_xy, ui_press_id, press_active)

        if state.mode == "battle":
            selected_detail_id = _normalize_detail_selection(state, selected_detail_id)
            _, mx_sc = _player_list_scroll_bounds(state)
            player_list_scroll = min(player_list_scroll, mx_sc)
            draw_battle(
                screen,
                font_l,
                font_m,
                font_s,
                state,
                battle_outcome(state),
                player_list_scroll,
                selected_detail_id,
                mouse_xy,
                ui_press_id,
                press_active,
            )
        else:
            draw_strategy(
                screen, font_l, font_m, font_s, state, mouse_xy, ui_press_id, press_active
            )

        hint = font_s.render("F5 存档  F9 读档 (save_game.json)", True, (90, 98, 110))
        screen.blit(hint, (W - hint.get_width() - 16, H - 26))

        pygame.display.flip()

    pygame.quit()


def draw_army_summary_block(
    screen: pygame.Surface,
    font_l: pygame.font.Font,
    font_m: pygame.font.Font,
    font_s: pygame.font.Font,
    state: GameState,
    base_x: int,
    base_y: int,
    *,
    compact: bool = False,
) -> None:
    b = state.battle
    y = base_y
    title_font = font_m if compact else font_l
    screen.blit(title_font.render("各部宏观", True, ACCENT), (base_x, y))
    y += 22 if compact else 36
    bar_w = 200 if compact else 220
    fat_h, mor_h = (9, 8) if compact else (14, 12)
    gap_after_fat = 12 if compact else 22
    gap_mor_lbl = 11 if compact else 18
    gap_after_mor = 10 if compact else 24
    gap_player_extra = 8 if compact else 28
    name_font = font_s if compact else font_m
    name_step = 15 if compact else 22
    for _aid, army in b.armies.items():
        alive = sum(1 for sid in army.soldier_ids if b.soldiers.get(sid) and b.soldiers[sid].alive)
        fat = army_average_fatigue(b, army)
        line = f"{army.name}  存活 {alive}"
        screen.blit(name_font.render(line, True, TEXT), (base_x, y))
        y += name_step
        _draw_bar(screen, pygame.Rect(base_x, y, bar_w, fat_h), fat, RED if fat > 0.65 else GREEN)
        y += gap_after_fat
        if army.faction == "enemy":
            mor = army_average_enemy_morale(b, army)
            mor_n = min(1.0, mor / 45.0)
            screen.blit(font_s.render("敌军训练士气(均)", True, MUTED), (base_x, y))
            y += gap_mor_lbl
            _draw_bar(screen, pygame.Rect(base_x, y, bar_w, mor_h), mor_n, BLUE)
            y += gap_after_mor
        else:
            bonus = army.officer_morale_bonus_for_troops()
            bn = min(1.0, bonus / 35.0)
            screen.blit(font_s.render("我军军官士气加成", True, MUTED), (base_x, y))
            y += gap_mor_lbl
            _draw_bar(screen, pygame.Rect(base_x, y, bar_w, mor_h), bn, BLUE)
            y += gap_player_extra


def draw_log_block(
    screen: pygame.Surface,
    font_m: pygame.font.Font,
    font_s: pygame.font.Font,
    state: GameState,
    base_x: int,
    base_y: int,
    lines: int = 18,
) -> None:
    b = state.battle
    screen.blit(font_m.render("战报", True, ACCENT), (base_x, base_y))
    log_y = base_y + 30
    for line in b.log[-lines:]:
        surf = font_s.render(line[:80], True, TEXT)
        screen.blit(surf, (base_x, log_y))
        log_y += 20


def draw_battle_legend(
    screen: pygame.Surface,
    font_s: pygame.font.Font,
    state: GameState,
    x: int,
    y: int,
    max_width: int,
) -> None:
    plain = _terrain_color(Terrain.PLAIN)
    river = _terrain_color(Terrain.RIVER)
    high = _terrain_color(Terrain.HIGH)
    pygame.draw.rect(screen, plain, (x, y, 14, 14))
    pygame.draw.rect(screen, river, (x + 80, y, 14, 14))
    pygame.draw.rect(screen, high, (x + 160, y, 14, 14))
    screen.blit(font_s.render("平地", True, TEXT), (x + 18, y - 2))
    screen.blit(font_s.render("河", True, TEXT), (x + 98, y - 2))
    screen.blit(font_s.render("高地", True, TEXT), (x + 178, y - 2))
    line2 = "格内写作 我n|敌m：左为我方、右为敌方本格存活人数；odd-r 六邻接自动推进，无手动移格。"
    surf2 = font_s.render(line2, True, MUTED)
    if surf2.get_width() > max_width:
        line2 = "格内 我n|敌m = 我方|敌方本格存活；六邻接自动推进。"
        surf2 = font_s.render(line2, True, MUTED)
    screen.blit(surf2, (x, y + 22))
    line3 = "疲劳条：绿≤65% 耐力负荷，红>65%（后撤换气阈值约72%见逻辑）。"
    surf3 = font_s.render(line3, True, MUTED)
    if surf3.get_width() > max_width:
        line3 = "疲劳条：绿≤65%，红>65%（后撤阈值约72%）。"
        surf3 = font_s.render(line3, True, MUTED)
    screen.blit(surf3, (x, y + 42))
    hero_line = (
        "主角「你」与士卒同属性；每 tick 按左侧 近战/射箭/待命 行动（自动推进也执行）。"
        + (" 守城：主角固守、射箭加成。" if state.siege_mode else "")
    )
    h2 = font_s.render(hero_line[:52], True, MUTED)
    screen.blit(h2, (x, y + 60))
    gold_ln = "金色六角描边 = 主角「你」所在格（可与敌同格混战）。"
    g2 = font_s.render(gold_ln, True, MUTED)
    if g2.get_width() > max_width:
        gold_ln = "金边六角格 = 主角所在（可混战格）。"
        g2 = font_s.render(gold_ln, True, MUTED)
    screen.blit(g2, (x, y + 78))


def draw_player_list_block(
    screen: pygame.Surface,
    font_m: pygame.font.Font,
    font_s: pygame.font.Font,
    state: GameState,
    scroll_y: int,
    selected_id: Optional[str],
) -> None:
    r = PLAYER_LIST_RECT
    pygame.draw.rect(screen, PANEL, r, width=2)
    screen.blit(
        font_m.render("我军存活（点行看详情 · 滚轮）", True, ACCENT),
        (r.x + 8, r.y + 6),
    )
    inner = pygame.Rect(r.x + 6, r.y + 28, r.width - 12, r.height - 34)
    prev_clip = screen.get_clip()
    screen.set_clip(inner)
    row_h = PLAYER_LIST_ROW_H
    y0 = inner.y - scroll_y + 22
    soldiers = _player_alive_sorted(state)
    for sol in soldiers:
        if y0 > inner.bottom:
            break
        block_bottom = y0 + row_h - 2
        if block_bottom >= inner.y:
            if sol.id == selected_id:
                pygame.draw.rect(
                    screen,
                    (48, 56, 68),
                    (inner.x, y0 - 1, inner.width, row_h - 2),
                    border_radius=2,
                )
            screen.blit(
                font_s.render(f"{sol.name}  HP {sol.hp:.0f}/{sol.hp_max:.0f}", True, TEXT),
                (inner.x + 4, y0),
            )
            fat_r = sol.fatigue / max(1.0, sol.fatigue_max())
            _draw_bar(
                screen,
                pygame.Rect(inner.x + 200, y0 + 1, 88, 9),
                fat_r,
                RED if fat_r > 0.65 else GREEN,
            )
            st = (
                f"力{sol.strength:.0f} 敏{sol.agility:.0f} "
                f"耐{sol.endurance:.0f} 健{sol.vitality:.0f}  "
                f"单手{sol.prof.get('one_handed', 0):.0f} 弓{sol.prof.get('bow', 0):.0f}"
            )
            screen.blit(font_s.render(st, True, MUTED), (inner.x + 4, y0 + 14))
            wline = f"伤势:{_wound_summary_zh(sol)}  装备:{_gear_one_line(sol)}"
            screen.blit(font_s.render(wline[:62], True, MUTED), (inner.x + 4, y0 + 30))
        y0 += row_h
    if not soldiers:
        screen.blit(font_s.render("（无存活）", True, MUTED), (inner.x, inner.y + 8))
    screen.set_clip(prev_clip)


def draw_soldier_detail_panel(
    screen: pygame.Surface,
    font_m: pygame.font.Font,
    font_s: pygame.font.Font,
    state: GameState,
    soldier_id: Optional[str],
) -> None:
    r = PLAYER_DETAIL_RECT
    pygame.draw.rect(screen, PANEL, r, width=2)
    screen.blit(font_m.render("单位详情", True, ACCENT), (r.x + 8, r.y + 4))
    ix = r.x + 8
    iy = r.y + 26
    sid = _normalize_detail_selection(state, soldier_id)
    if sid is None:
        screen.blit(font_s.render("无我军存活单位", True, MUTED), (ix, iy))
        return
    sol = state.battle.soldiers[sid]
    tag = " · 主角" if sol.is_protagonist else ""
    hp_r = sol.hp / max(1.0, sol.hp_max)
    fat_r = sol.fatigue / max(1.0, sol.fatigue_max())
    screen.blit(
        font_s.render(f"{sol.name}{tag}  HP {sol.hp:.0f}/{sol.hp_max:.0f}", True, TEXT),
        (ix, iy),
    )
    iy += 16
    _draw_bar(screen, pygame.Rect(ix, iy, 200, 8), hp_r, RED)
    _draw_bar(screen, pygame.Rect(ix + 208, iy, 96, 8), fat_r, RED if fat_r > 0.65 else GREEN)
    iy += 12
    screen.blit(
        font_s.render(
            f"力{sol.strength:.0f} 敏{sol.agility:.0f} 耐{sol.endurance:.0f} "
            f"健{sol.vitality:.0f} 智{sol.wits:.0f}",
            True,
            MUTED,
        ),
        (ix, iy),
    )
    iy += 16
    po = sol.prof.get("polearm", 0)
    po_s = f" 枪{po:.0f}" if po > 0.5 else ""
    screen.blit(
        font_s.render(
            f"单手{sol.prof.get('one_handed', 0):.0f} 弓{sol.prof.get('bow', 0):.0f}{po_s}",
            True,
            MUTED,
        ),
        (ix, iy),
    )
    iy += 16
    screen.blit(font_s.render(f"装备 {_gear_one_line(sol)[:44]}", True, MUTED), (ix, iy))
    iy += 16
    pos = state.battle.positions.get(sol.id)
    pos_s = f"地图格 行{pos[0]} 列{pos[1]}" if pos else "位置未知"
    screen.blit(
        font_s.render(f"伤势 {_wound_summary_zh(sol)}  ·  {pos_s}", True, MUTED),
        (ix, iy),
    )


def draw_battle_end_overlay(
    screen: pygame.Surface,
    font_m: pygame.font.Font,
    font_s: pygame.font.Font,
    outcome: str,
    mouse_xy: Tuple[int, int],
    press_id: Optional[str],
    press_active: bool,
) -> None:
    overlay = pygame.Surface((616, 500), pygame.SRCALPHA)
    overlay.fill((12, 14, 18, 200))
    screen.blit(overlay, (14, 88))
    cx, cy = 322, 280
    title = font_m.render(f"会战已结束 · {outcome}", True, ACCENT)
    screen.blit(title, (cx - title.get_width() // 2, cy - 50))
    t2 = font_s.render("自动推进已停；可调顶部「会战自动」或点「手动推进」无效。", True, TEXT)
    screen.blit(t2, (cx - t2.get_width() // 2, cy - 18))
    t3 = font_s.render("点击下方按钮开始新的演示会战。", True, MUTED)
    screen.blit(t3, (cx - t3.get_width() // 2, cy + 6))
    mx, my = mouse_xy
    flash_nb = press_active and press_id == "new_battle"
    _draw_soft_button(
        screen,
        NEW_BATTLE_BTN_RECT,
        font_m.render("新开演示会战", True, TEXT),
        active=True,
        pressed=flash_nb,
        hovered=NEW_BATTLE_BTN_RECT.collidepoint(mx, my),
        accent_label=True,
    )


def draw_battle(
    screen: pygame.Surface,
    font_l: pygame.font.Font,
    font_m: pygame.font.Font,
    font_s: pygame.font.Font,
    state: GameState,
    outcome: Optional[str],
    player_scroll: int,
    selected_detail_id: Optional[str],
    mouse_xy: Tuple[int, int],
    press_id: Optional[str],
    press_active: bool,
) -> None:
    b = state.battle
    mx, my = mouse_xy

    def flash(bid: str) -> bool:
        return press_active and press_id == bid

    pygame.draw.rect(screen, PANEL, (12, 52, 620, 612), width=2)

    if not outcome:
        _draw_soft_button(
            screen,
            MANUAL_TICK_RECT,
            font_s.render("手动推进 · tick", True, TEXT),
            active=True,
            pressed=flash("manual_tick"),
            hovered=MANUAL_TICK_RECT.collidepoint(mx, my),
            accent_label=True,
        )
    else:
        hint = font_s.render("已结束", True, RED)
        screen.blit(hint, (174, 60))

    if not outcome:
        _draw_soft_button(
            screen,
            HERO_MELEE_RECT,
            font_s.render("近战", True, TEXT),
            active=state.hero_stance == "melee",
            pressed=flash("hero_melee"),
            hovered=HERO_MELEE_RECT.collidepoint(mx, my),
            accent_label=state.hero_stance == "melee",
        )
        _draw_soft_button(
            screen,
            HERO_RANGED_RECT,
            font_s.render("射箭", True, TEXT),
            active=state.hero_stance == "ranged",
            pressed=flash("hero_ranged"),
            hovered=HERO_RANGED_RECT.collidepoint(mx, my),
            accent_label=state.hero_stance == "ranged",
        )
        _draw_soft_button(
            screen,
            HERO_HOLD_RECT,
            font_s.render("待命", True, TEXT),
            active=state.hero_stance == "hold",
            pressed=flash("hero_hold"),
            hovered=HERO_HOLD_RECT.collidepoint(mx, my),
            accent_label=state.hero_stance == "hold",
        )
        siege_on = state.siege_mode
        _draw_soft_button(
            screen,
            SIEGE_TOGGLE_RECT,
            font_s.render("守城 · 开" if siege_on else "守城 · 关", True, TEXT),
            active=siege_on,
            pressed=flash("siege_toggle"),
            hovered=SIEGE_TOGGLE_RECT.collidepoint(mx, my),
            accent_label=siege_on,
        )

    hex_area_w, hex_area_h = 584, 336
    bx, by = 20, 130
    radius = _fit_hex_radius(b.width, b.height, float(hex_area_w - 8), float(hex_area_h - 8))
    mn_x, mn_y, mx_x, mx_y = _hex_grid_bbox(b.width, b.height, radius)
    gw, gh = mx_x - mn_x, mx_y - mn_y
    origin_x = bx + (hex_area_w - gw) * 0.5 - mn_x
    origin_y = by + (hex_area_h - gh) * 0.5 - mn_y
    edge = (60, 65, 72)

    hero_pos: Optional[Tuple[int, int]] = None
    hero_sol = b.soldiers.get(PROTAGONIST_ID)
    if hero_sol and hero_sol.alive:
        hero_pos = b.positions.get(PROTAGONIST_ID)

    for r in range(b.height):
        for c in range(b.width):
            cell = b.cells[r][c]
            cx, cy = _hex_screen_xy(c, r, radius, origin_x, origin_y)
            pts = _hex_vertices_pointy(cx, cy, radius * 0.92)
            pygame.draw.polygon(screen, _terrain_color(cell.terrain), pts)
            pygame.draw.polygon(screen, edge, pts, 1)
            pc = ec = 0
            for u in cell.units:
                sol = b.soldiers.get(u.soldier_id)
                if not sol or not sol.alive:
                    continue
                fac = b.armies[u.army_id].faction
                if fac == "player":
                    pc += 1
                elif fac == "enemy":
                    ec += 1
            label = font_s.render(f"我{pc}|敌{ec}", True, TEXT)
            screen.blit(label, (int(cx - label.get_width() // 2), int(cy - label.get_height() // 2)))
            if hero_pos is not None and (r, c) == hero_pos:
                pygame.draw.polygon(screen, (218, 175, 55), pts, 3)

    draw_battle_legend(screen, font_s, state, 24, 478, 580)

    pygame.draw.rect(screen, PANEL, (642, 52, 626, 240), width=2)
    draw_army_summary_block(screen, font_l, font_m, font_s, state, 654, 56, compact=True)

    draw_player_list_block(screen, font_m, font_s, state, player_scroll, selected_detail_id)

    draw_soldier_detail_panel(screen, font_m, font_s, state, selected_detail_id)

    pygame.draw.rect(screen, PANEL, (642, 612, 626, 108), width=2)
    draw_log_block(screen, font_m, font_s, state, 654, 620, lines=5)

    if outcome:
        draw_battle_end_overlay(screen, font_m, font_s, outcome, mouse_xy, press_id, press_active)


def draw_strategy(
    screen: pygame.Surface,
    font_l: pygame.font.Font,
    font_m: pygame.font.Font,
    font_s: pygame.font.Font,
    state: GameState,
    mouse_xy: Tuple[int, int],
    press_id: Optional[str],
    press_active: bool,
) -> None:
    mx, my = mouse_xy

    def flash(bid: str) -> bool:
        return press_active and press_id == bid

    pygame.draw.rect(screen, PANEL, (12, 52, 1240, 620), width=2)
    screen.blit(font_l.render("中原版图（占位）— 中国历史地理待接入", True, ACCENT), (32, 102))
    screen.blit(
        font_m.render(f"战役累计时间: {state.campaign_hours:.1f} 时辰（抽象单位，可改）", True, TEXT),
        (32, 142),
    )
    _draw_soft_button(
        screen,
        STRAT_H1_RECT,
        font_s.render("+1 时辰", True, TEXT),
        pressed=flash("strat_h1"),
        hovered=STRAT_H1_RECT.collidepoint(mx, my),
    )
    _draw_soft_button(
        screen,
        STRAT_H6_RECT,
        font_s.render("+半天 (×步进)", True, TEXT),
        pressed=flash("strat_h6"),
        hovered=STRAT_H6_RECT.collidepoint(mx, my),
    )
    _draw_soft_button(
        screen,
        STRAT_H24_RECT,
        font_s.render("+整日 (×步进)", True, TEXT),
        pressed=flash("strat_h24"),
        hovered=STRAT_H24_RECT.collidepoint(mx, my),
    )

    screen.blit(font_m.render("当前会战仍可在「会战」页查看；战略层稍后接城池/道路/民心。", True, MUTED), (32, 182))
    draw_army_summary_block(screen, font_l, font_m, font_s, state, base_x=32, base_y=222)
    draw_log_block(screen, font_m, font_s, state, base_x=32, base_y=422, lines=12)


if __name__ == "__main__":
    run()
