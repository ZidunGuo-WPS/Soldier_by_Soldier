"""
Main window: 战略占位 + 会战格子 + 宏观色条 + 战报。
操作：鼠标点按钮；会战里可自动推进（速度档位）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

import pygame

from sbs.battle_sim import Terrain
from sbs.fonts import pick_cjk_font
from sbs.game_state import (
    GameState,
    army_average_enemy_morale,
    army_average_fatigue,
    load_game,
    new_demo_game,
    save_game,
)

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
    running = True

    def tick_battle_once() -> None:
        if battle_outcome(state):
            return
        state.battle.tick(state.rng())
        outcome = battle_outcome(state)
        if outcome:
            state.battle.log.append(f"—— 会战结束: {outcome} ——")

    def battle_outcome(g: GameState) -> Optional[str]:
        p, e = g.battle.alive_counts()
        if p <= 0:
            return "敌军胜"
        if e <= 0:
            return "我军胜"
        return None

    def handle_click(mx: int, my: int) -> None:
        nonlocal state
        if 8 <= my <= 40:
            if 20 <= mx <= 110:
                state.mode = "strategy"
            elif 120 <= mx <= 220:
                state.mode = "battle"
            elif 240 <= mx <= 400:
                state.fight_to_death = not state.fight_to_death
                state.apply_player_doctrine()
            elif 420 <= mx <= 600:
                state.allow_rotation = not state.allow_rotation
                state.apply_player_doctrine()
            elif 640 <= mx <= 720:
                state.battle_tick_speed = (state.battle_tick_speed + 1) % 4
            elif 740 <= mx <= 900:
                state.campaign_step_speed = (state.campaign_step_speed % 3) + 1
        if state.mode == "battle" and 52 <= my <= 82 and 20 <= mx <= 160:
            tick_battle_once()
        if state.mode == "strategy" and 52 <= my <= 82:
            mult = state.campaign_step_speed
            if 20 <= mx <= 120:
                state.campaign_hours += 1.0 * mult
            elif 130 <= mx <= 260:
                state.campaign_hours += 6.0 * mult
            elif 270 <= mx <= 400:
                state.campaign_hours += 24.0 * mult

    while running:
        dt = clock.tick(60)
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
                    state.battle.log.append("已读档")
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                handle_click(mx, my)

        screen.fill(BG)

        # top bar
        pygame.draw.rect(screen, PANEL, (0, 0, W, 48))
        t1 = font_m.render("战略", True, ACCENT if state.mode == "strategy" else TEXT)
        t2 = font_m.render("会战", True, ACCENT if state.mode == "battle" else TEXT)
        screen.blit(t1, (32, 10))
        screen.blit(t2, (132, 10))
        pygame.draw.rect(screen, (70, 78, 90), (20, 8, 100, 32), 1)
        pygame.draw.rect(screen, (70, 78, 90), (120, 8, 100, 32), 1)

        ftd = "死战不退: 开" if state.fight_to_death else "死战不退: 关"
        rot = "后撤换气: 开" if state.allow_rotation else "后撤换气: 关"
        screen.blit(font_s.render(ftd, True, TEXT), (240, 14))
        screen.blit(font_s.render(rot, True, TEXT), (420, 14))
        spd_names = ["会战自动: 停", "会战自动: 慢", "会战自动: 中", "会战自动: 快"]
        screen.blit(font_s.render(spd_names[state.battle_tick_speed], True, MUTED), (640, 14))
        screen.blit(
            font_s.render(f"战略步进×{state.campaign_step_speed} (点按钮加时辰)", True, MUTED),
            (740, 14),
        )

        if state.mode == "battle":
            draw_battle(screen, font_l, font_m, font_s, state)
        else:
            draw_strategy(screen, font_l, font_m, font_s, state)

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
) -> None:
    b = state.battle
    y = base_y
    screen.blit(font_l.render("各部宏观", True, ACCENT), (base_x, y))
    y += 36
    for _aid, army in b.armies.items():
        alive = sum(1 for sid in army.soldier_ids if b.soldiers.get(sid) and b.soldiers[sid].alive)
        fat = army_average_fatigue(b, army)
        line = f"{army.name}  存活 {alive}"
        screen.blit(font_m.render(line, True, TEXT), (base_x, y))
        y += 22
        _draw_bar(screen, pygame.Rect(base_x, y, 220, 14), fat, RED if fat > 0.65 else GREEN)
        y += 22
        if army.faction == "enemy":
            mor = army_average_enemy_morale(b, army)
            mor_n = min(1.0, mor / 45.0)
            screen.blit(font_s.render("敌军训练士气(均)", True, MUTED), (base_x, y))
            y += 18
            _draw_bar(screen, pygame.Rect(base_x, y, 220, 12), mor_n, BLUE)
            y += 24
        else:
            bonus = army.officer_morale_bonus_for_troops()
            bn = min(1.0, bonus / 35.0)
            screen.blit(font_s.render("我军军官士气加成", True, MUTED), (base_x, y))
            y += 18
            _draw_bar(screen, pygame.Rect(base_x, y, 220, 12), bn, BLUE)
            y += 28


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


def draw_battle(
    screen: pygame.Surface,
    font_l: pygame.font.Font,
    font_m: pygame.font.Font,
    font_s: pygame.font.Font,
    state: GameState,
) -> None:
    b = state.battle
    pygame.draw.rect(screen, PANEL, (12, 52, 620, 420), width=2)
    bx, by, bw, bh = 20, 60, 600, 400
    cw = bw // b.width
    ch = bh // b.height

    for r in range(b.height):
        for c in range(b.width):
            cell = b.cells[r][c]
            rect = pygame.Rect(bx + c * cw, by + r * ch, cw - 2, ch - 2)
            pygame.draw.rect(screen, _terrain_color(cell.terrain), rect)
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
            label = font_s.render(f"{pc}|{ec}", True, TEXT)
            screen.blit(label, (rect.centerx - label.get_width() // 2, rect.centery - 8))

    pygame.draw.rect(screen, (70, 78, 90), (20, 52, 140, 28), 1)
    screen.blit(font_s.render("手动推进一tick", True, ACCENT), (32, 56))

    pygame.draw.rect(screen, PANEL, (660, 52, 600, 200), width=2)
    draw_army_summary_block(screen, font_l, font_m, font_s, state, 672, 64)

    pygame.draw.rect(screen, PANEL, (660, 260, 600, 430), width=2)
    draw_log_block(screen, font_m, font_s, state, 672, 270, lines=18)


def draw_strategy(
    screen: pygame.Surface,
    font_l: pygame.font.Font,
    font_m: pygame.font.Font,
    font_s: pygame.font.Font,
    state: GameState,
) -> None:
    pygame.draw.rect(screen, PANEL, (12, 52, 1240, 620), width=2)
    screen.blit(font_l.render("中原版图（占位）— 中国历史地理待接入", True, ACCENT), (32, 72))
    screen.blit(
        font_m.render(f"战役累计时间: {state.campaign_hours:.1f} 时辰（抽象单位，可改）", True, TEXT),
        (32, 112),
    )
    pygame.draw.rect(screen, (70, 78, 90), (20, 52, 110, 28), 1)
    pygame.draw.rect(screen, (70, 78, 90), (130, 52, 130, 28), 1)
    pygame.draw.rect(screen, (70, 78, 90), (270, 52, 130, 28), 1)
    screen.blit(font_s.render("+1时辰", True, TEXT), (38, 56))
    screen.blit(font_s.render("+半天(×步进)", True, TEXT), (138, 56))
    screen.blit(font_s.render("+整日(×步进)", True, TEXT), (278, 56))

    screen.blit(font_m.render("当前会战仍可在「会战」页查看；战略层稍后接城池/道路/民心。", True, MUTED), (32, 160))
    draw_army_summary_block(screen, font_l, font_m, font_s, state, base_x=32, base_y=200)
    draw_log_block(screen, font_m, font_s, state, base_x=32, base_y=400, lines=12)


if __name__ == "__main__":
    run()
