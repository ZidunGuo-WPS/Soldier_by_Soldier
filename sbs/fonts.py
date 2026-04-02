from __future__ import annotations

import pygame


def pick_cjk_font(size: int) -> pygame.font.Font:
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
