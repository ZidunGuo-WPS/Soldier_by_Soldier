"""
Abstract tactical map: zones for 前/左/中/右/后军 (both sides).
Click zone → roster; click name → equipment with tier-colored text.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pygame

from sbs.battle_layout import POSITIONS, demo_armies, soldiers_in_zone
from sbs.equipment import SLOT_LABEL_ZH, TIER_COLORS, tier_color
from sbs.soldier import Soldier


W, H = 1120, 700
MAP_X0, MAP_Y0 = 24, 24
MAP_W, MAP_H = 640, 640
PANEL_X = MAP_X0 + MAP_W + 16
PANEL_W = W - PANEL_X - 24

BG = (28, 32, 38)
GRID = (55, 62, 74)
TEXT_DIM = (160, 168, 182)
ACCENT = (200, 180, 120)
LINE_COLOR = (90, 98, 110)


@dataclass
class ZoneHit:
    side: str  # "ours" | "theirs"
    key: str


def _pick_font(size: int) -> pygame.font.Font:
    for name in (
        "Noto Sans CJK SC",
        "Noto Sans CJK JP",
        "Source Han Sans SC",
        "WenQuanYi Micro Hei",
        "WenQuanYi Zen Hei",
        "Droid Sans Fallback",
        "SimHei",
        "Microsoft YaHei",
    ):
        font = pygame.font.SysFont(name, size)
        if font.render("甲", True, (255, 255, 255)).get_width() >= 10:
            return font
    return pygame.font.SysFont(None, size)


def _layout_zone_rects() -> Dict[Tuple[str, str], pygame.Rect]:
    """Five zones per side: horizontal row for enemy (top), horizontal row for us (bottom)."""
    rects: Dict[Tuple[str, str], pygame.Rect] = {}
    n = len(POSITIONS)
    pad = 8
    cell_w = (MAP_W - pad * (n + 1)) // n
    cell_h = 120

    y_enemy = MAP_Y0 + 40
    y_ours = MAP_Y0 + MAP_H - cell_h - 40

    for i, (key, _zh) in enumerate(POSITIONS):
        x = MAP_X0 + pad + i * (cell_w + pad)
        rects[("theirs", key)] = pygame.Rect(x, y_enemy, cell_w, cell_h)
        rects[("ours", key)] = pygame.Rect(x, y_ours, cell_w, cell_h)
    return rects


def run() -> None:
    pygame.init()
    pygame.display.set_caption("Soldier by Soldier — 战术地图")
    screen = pygame.display.set_mode((W, H))
    clock = pygame.time.Clock()

    font_title = _pick_font(22)
    font_label = _pick_font(18)
    font_body = _pick_font(16)
    font_small = _pick_font(14)

    ours, theirs = demo_armies()
    zone_rects = _layout_zone_rects()

    selected_side: Optional[str] = None
    selected_zone: Optional[str] = None
    selected_soldier: Optional[Soldier] = None
    roster_hits: List[Tuple[pygame.Rect, Soldier]] = []

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                hit_zone: Optional[ZoneHit] = None
                for (side, key), rect in zone_rects.items():
                    if rect.collidepoint(mx, my):
                        hit_zone = ZoneHit(side, key)
                        break
                if hit_zone:
                    selected_side = hit_zone.side
                    selected_zone = hit_zone.key
                    selected_soldier = None
                    continue
                for rect, sol in roster_hits:
                    if rect.collidepoint(mx, my):
                        selected_soldier = sol
                        break

        screen.fill(BG)

        # Map frame
        pygame.draw.rect(screen, GRID, (MAP_X0, MAP_Y0, MAP_W, MAP_H), width=2)
        mid_y = MAP_Y0 + MAP_H // 2
        pygame.draw.line(screen, LINE_COLOR, (MAP_X0 + 8, mid_y), (MAP_X0 + MAP_W - 8, mid_y), 2)
        battle_line = font_label.render("—— 战线 ——", True, ACCENT)
        screen.blit(battle_line, (MAP_X0 + MAP_W // 2 - battle_line.get_width() // 2, mid_y - 28))

        army_ours = font_title.render("我军", True, (140, 200, 255))
        army_theirs = font_title.render("敌军", True, (255, 140, 130))
        screen.blit(army_theirs, (MAP_X0 + 8, MAP_Y0 + 8))
        screen.blit(army_ours, (MAP_X0 + 8, MAP_Y0 + MAP_H - 36))

        for (side, key), rect in zone_rects.items():
            pygame.draw.rect(screen, GRID, rect, width=2)
            zh = next(z for k, z in POSITIONS if k == key)
            label = font_label.render(zh, True, TEXT_DIM)
            screen.blit(label, (rect.centerx - label.get_width() // 2, rect.y + 6))
            army = ours if side == "ours" else theirs
            count = len(soldiers_in_zone(army, key))
            cnt_s = font_small.render(f"{count} 人", True, TEXT_DIM)
            screen.blit(cnt_s, (rect.centerx - cnt_s.get_width() // 2, rect.bottom - 26))

        # Right panel
        pygame.draw.rect(screen, GRID, (PANEL_X, MAP_Y0, PANEL_W, MAP_H), width=2)
        panel_title = font_title.render("阵中详情", True, ACCENT)
        screen.blit(panel_title, (PANEL_X + 12, MAP_Y0 + 12))

        roster_hits.clear()
        y = MAP_Y0 + 52

        if selected_side and selected_zone:
            army = ours if selected_side == "ours" else theirs
            zh = next(z for k, z in POSITIONS if k == selected_zone)
            side_zh = "我军" if selected_side == "ours" else "敌军"
            hint = font_body.render(f"{side_zh} · {zh}", True, TEXT_DIM)
            screen.blit(hint, (PANEL_X + 12, y))
            y += 32

            roster = soldiers_in_zone(army, selected_zone)
            if not roster:
                empty = font_small.render("该阵位暂无士兵", True, (120, 120, 130))
                screen.blit(empty, (PANEL_X + 12, y))
                y += 28
            else:
                pick = font_small.render("点击姓名查看装备（强度见颜色）", True, (130, 140, 155))
                screen.blit(pick, (PANEL_X + 12, y))
                y += 26
                for sol in roster:
                    line = f"{sol.name}  HP {int(sol.hp)}  疲劳 {int(sol.fatigue)}/{int(sol.fatigue_max())}"
                    surf = font_body.render(line, True, (220, 225, 235))
                    row_rect = pygame.Rect(PANEL_X + 8, y - 2, PANEL_W - 16, surf.get_height() + 4)
                    if selected_soldier is sol:
                        pygame.draw.rect(screen, (50, 58, 72), row_rect)
                    screen.blit(surf, (PANEL_X + 12, y))
                    roster_hits.append((row_rect, sol))
                    y += surf.get_height() + 10

            y += 16
            if selected_soldier:
                pygame.draw.line(screen, LINE_COLOR, (PANEL_X + 12, y), (PANEL_X + PANEL_W - 12, y), 1)
                y += 14
                eq_title = font_body.render(f"装备 — {selected_soldier.name}", True, ACCENT)
                screen.blit(eq_title, (PANEL_X + 12, y))
                y += 28
                for g in selected_soldier.gear:
                    slot_zh = SLOT_LABEL_ZH.get(g.slot, g.slot)
                    slot_surf = font_small.render(f"{slot_zh}：", True, TEXT_DIM)
                    screen.blit(slot_surf, (PANEL_X + 12, y))
                    name_surf = font_body.render(f"{g.name}  [T{g.tier}]", True, g.color())
                    screen.blit(name_surf, (PANEL_X + 12 + slot_surf.get_width() + 4, y - 2))
                    y += 26
        else:
            tip = font_body.render("点击左侧阵位查看该处士兵", True, TEXT_DIM)
            screen.blit(tip, (PANEL_X + 12, y))

        # Tier legend
        leg_y = MAP_Y0 + MAP_H - 88
        pygame.draw.line(screen, LINE_COLOR, (PANEL_X + 12, leg_y - 8), (PANEL_X + PANEL_W - 12, leg_y - 8), 1)
        leg = font_small.render("装备强度（字体颜色）", True, ACCENT)
        screen.blit(leg, (PANEL_X + 12, leg_y))
        leg_y += 22
        x_leg = PANEL_X + 12
        for tier in sorted(TIER_COLORS.keys()):
            c = tier_color(tier)
            lab = font_small.render(f"T{tier}", True, c)
            screen.blit(lab, (x_leg, leg_y))
            x_leg += lab.get_width() + 18

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    run()
