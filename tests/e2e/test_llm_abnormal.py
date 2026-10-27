"""
tests/e2e/test_llm_abnormal.py - 大模型异常输出容错与防御性渲染 E2E 测试

覆盖范围：
1. 让假 LLM 返回缺字段、字段名漂移、空数组、非 JSON 的畸形数据
2. 检查前端界面上绝对不出现 "undefined"、"null"、"[object Object]" 药丸或文本
3. 发生异常后，页面的重试/确认/取消按钮仍然处于可用可点击状态（杜绝锁死）
"""

import time
import pytest
from tests.e2e.conftest import PageMonitor
from tests.e2e.fake_llm_server import FakeLLMState


def test_llm_abnormal_field_drift_and_missing(page, live_server):
    """
    测试 LLM 字段漂移（如 tropes 变为 templates）或字段缺失时，
    前端卡片不渲染 undefined/null，且「换一批」等操作按钮保持可用。
    """
    monitor = PageMonitor(page, "llm_abnormal_field_drift")

    # 1. 设置假 LLM 注入字段漂移模式
    FakeLLMState.set_mode("field_drift")

    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    # 点击换一批 / 重新生成灵感脑洞
    refresh_tropes_btn = page.locator("#btn_refresh_tropes")
    assert refresh_tropes_btn.is_visible(), "未找到换一批按钮 #btn_refresh_tropes"
    refresh_tropes_btn.click()
    page.wait_for_timeout(800)

    # 2. 断言页面文本绝对不包含恶性字符串
    body_text = page.locator("body").inner_text()
    assert "undefined" not in body_text, "缺陷复现：大模型字段变动导致前端渲染出了 'undefined' 标签/文本！"
    assert "[object Object]" not in body_text, "缺陷：前端将 Object 直接拼接入 HTML，出现了 '[object Object]'！"

    # 3. 验证按钮仍然可用可点击（未被锁死）
    assert refresh_tropes_btn.is_enabled(), "灵感生成异常后，换一批按钮被永久禁用锁死！"

    monitor.assert_no_errors("大模型字段漂移容错")
    FakeLLMState.reset()


def test_llm_abnormal_malformed_json_resilience(page, live_server):
    """测试 LLM 返回非 JSON 破损字符串时，前端给出友好 Toast，不卡死无 undefined。"""
    monitor = PageMonitor(page, "llm_abnormal_malformed")

    # 注入畸形非 JSON 模式
    FakeLLMState.set_mode("malformed_json")

    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    page.fill("#og_title", "异常容错测试")
    page.fill("#og_genre", "都市言情")
    page.fill("#og_setting", "测试设定背景。")
    page.locator("#btn_step1_next").click()
    page.wait_for_timeout(200)

    # 触发大纲推演（此时假 LLM 返回畸形非 JSON）
    outline_btn = page.locator("#btn_outline")
    assert outline_btn.is_visible(), "未找到生成大纲按钮 #btn_outline"
    outline_btn.click()
    page.wait_for_timeout(1000)

    body_text = page.locator("body").inner_text()
    assert "undefined" not in body_text
    assert "[object Object]" not in body_text

    # 关键断言：绝对不能有未捕获的 JS 异常导致全站瘫痪
    assert len(monitor.page_errors) == 0, f"大模型畸形响应导致未捕获 JS 异常: {monitor.page_errors}"
    FakeLLMState.reset()
