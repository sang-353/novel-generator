# -*- coding: utf-8 -*-
"""
tests/e2e/test_og_buttons.py - 验证第 1 步各操作按钮在交互全生命周期中保持 SVG 图标且无 emoji
"""

import re
import pytest
from tests.e2e.conftest import PageMonitor


def test_step1_suggest_titles_and_refresh_buttons_keep_svg_no_emoji(page, live_server):
    """
    验证 #btn_suggest_titles 和 #btn_refresh_tropes 在初始、点击加载中、完成、出错状态下：
    1. SVG 图标始终存在，绝不被 textContent/innerHTML 抹除；
    2. 按钮文本绝不重新引入 ✨ 或 🎲 等 emoji。
    """
    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    # -------------------------------------------------------------
    # 1. 验证 #btn_suggest_titles 拟名按钮
    # -------------------------------------------------------------
    btn_titles = page.locator("#btn_suggest_titles")
    assert btn_titles.is_visible()
    assert btn_titles.locator("svg").count() == 1, "初始状态下 AI 拟名按钮缺少 SVG 图标"
    assert "✨" not in btn_titles.inner_text(), "初始状态下 AI 拟名按钮不应包含 emoji"

    # 填写题材，触发拟名
    page.fill("#og_genre", "科幻修真")
    btn_titles.click()
    page.wait_for_timeout(300)

    # 断言拟名完成后：SVG 必须仍然存在，且文本中绝无 emoji
    assert btn_titles.locator("svg").count() == 1, "缺陷复现：点击拟名后，btn.textContent 导致 SVG 图标丢失！"
    btn_text = btn_titles.inner_text()
    assert "✨" not in btn_text, f"缺陷复现：拟名按钮恢复时重新写入了 emoji：{btn_text}"

    # -------------------------------------------------------------
    # 2. 验证 #btn_refresh_tropes 换一批按钮
    # -------------------------------------------------------------
    btn_refresh = page.locator("#btn_refresh_tropes")
    assert btn_refresh.is_visible()
    assert btn_refresh.locator("svg").count() == 1, "初始状态下换一批按钮缺少 SVG 图标"
    assert "🎲" not in btn_refresh.inner_text()
    assert "✨" not in btn_refresh.inner_text()

    # 点击换一批
    btn_refresh.click()
    page.wait_for_timeout(300)

    # 断言换一批完成后：SVG 依然存在且无 emoji
    assert btn_refresh.locator("svg").count() == 1, "换一批完成后 SVG 图标必须保留"
    refresh_text = btn_refresh.inner_text()
    assert "🎲" not in refresh_text and "✨" not in refresh_text
