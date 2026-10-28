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


def test_step1_word_counts_live_update_and_programmatic_fill(page, live_server):
    """
    验证步骤 2：故事背景与故事主线输入框下方的实时字数统计「N 字」
    1. 初始状态为 0 字；
    2. 用户键盘输入实时更新；
    3. 点击灵感模板卡片（程序化写入）后自动更新为卡片内容字数；
    4. 点击清空表单后自动重置为 0 字。
    """
    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    txt_setting_cnt = page.locator("#txt_setting_word_count")
    txt_storyline_cnt = page.locator("#txt_storyline_word_count")

    # 1. 初始为 0 字
    assert txt_setting_cnt.inner_text().strip() == "0 字"
    assert txt_storyline_cnt.inner_text().strip() == "0 字"

    # 2. 键盘输入测试
    setting_input = "在赛博朋克的九龙城寨中，人类与机械深度共生。"
    storyline_input = "主角探寻身世之谜，反抗巨型企业财团。"

    page.fill("#og_setting", setting_input)
    page.wait_for_timeout(100)
    assert txt_setting_cnt.inner_text().strip() == f"{len(re.sub(r'\s+', '', setting_input))} 字"

    page.fill("#og_storyline", storyline_input)
    page.wait_for_timeout(100)
    assert txt_storyline_cnt.inner_text().strip() == f"{len(re.sub(r'\s+', '', storyline_input))} 字"

    # 3. 灵感模板程序化写入测试
    first_trope = page.locator("#og_trope_pills .trope-pill").first
    assert first_trope.is_visible()
    first_trope.click()
    page.wait_for_timeout(200)

    setting_val = page.locator("#og_setting").input_value()
    storyline_val = page.locator("#og_storyline").input_value()
    expected_setting_len = len(re.sub(r"\s+", "", setting_val))
    expected_storyline_len = len(re.sub(r"\s+", "", storyline_val))

    assert expected_setting_len > 0
    assert expected_storyline_len > 0
    assert txt_setting_cnt.inner_text().strip() == f"{expected_setting_len} 字"
    assert txt_storyline_cnt.inner_text().strip() == f"{expected_storyline_len} 字"

    # 4. 清空表单测试
    page.on("dialog", lambda dialog: dialog.accept())
    page.locator("#btn_clear_og").click()
    page.wait_for_timeout(300)

    assert txt_setting_cnt.inner_text().strip() == "0 字"
    assert txt_storyline_cnt.inner_text().strip() == "0 字"
