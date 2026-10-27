"""
tests/e2e/test_llm_abnormal.py - 大模型异常输出容错与防御性渲染 E2E 测试

覆盖范围：
1. 对 suggest-tropes、generate-bible、outline、generate-variants 四个功能，
   分别用 missing_fields / field_drift / top_level_array / malformed_json / empty 五种模式各测一遍
2. 断言页面无 undefined/null/[object Object]
3. 发生异常后，页面的操作按钮（重试/生成/取消）仍然处于可用可点击状态（杜绝死锁）
4. 断言有友好提示（Toast/状态提示/候选卡片/缺省提示），无未捕获 JS 异常
"""

import json
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


FEATURES = ["suggest-tropes", "generate-bible", "outline", "generate-variants"]
MODES = ["missing_fields", "field_drift", "top_level_array", "malformed_json", "empty"]


@pytest.mark.parametrize("feature", FEATURES)
@pytest.mark.parametrize("mode", MODES)
def test_llm_abnormal_matrix(page, live_server, feature, mode):
    """
    参数化全矩阵容错测试：
    对 suggest-tropes、generate-bible、outline、generate-variants 四个功能，
    分别在 missing_fields / field_drift / top_level_array / malformed_json / empty 五种模式下运行。
    断言页面无 undefined/null/[object Object]，相关按钮仍可点击，有友好提示。
    """
    monitor = PageMonitor(page, f"llm_matrix_{feature}_{mode}")
    FakeLLMState.set_mode(mode, target_feature=feature)

    try:
        if feature == "suggest-tropes":
            page.goto(f"{live_server}/#original")
            page.wait_for_load_state("networkidle")
            btn = page.locator("#btn_refresh_tropes")
            assert btn.is_visible()
            btn.click()
            page.wait_for_timeout(800)

            # 验证按钮仍然可用可点击
            assert btn.is_enabled(), f"[{feature}][{mode}] 按钮被锁死"
            # 友好提示验证：脑洞药丸被降级或正常渲染，或容器有内容
            tropes_count = page.locator("#og_trope_pills .trope-pill").count()
            pills_text = page.locator("#og_trope_pills").inner_text()
            assert tropes_count > 0 or len(pills_text.strip()) > 0, f"[{feature}][{mode}] 未展示任何提示或脑洞药丸"

        elif feature == "generate-bible":
            page.goto(f"{live_server}/#original")
            page.wait_for_load_state("networkidle")
            page.fill("#og_title", f"设定集容错_{mode}")
            page.fill("#og_genre", "科幻")
            page.fill("#og_setting", "测试在设定集异常下的系统容错能力。")
            page.locator("#btn_step1_next").click()
            page.wait_for_timeout(200)

            btn = page.locator("#btn_outline")
            assert btn.is_visible()
            btn.click()
            # 等待生成完成（或异常捕获后释放按钮）
            for _ in range(20):
                page.wait_for_timeout(250)
                if btn.is_enabled():
                    break
            assert btn.is_enabled(), f"[{feature}][{mode}] 规划按钮被锁死未复原"

            status_text = page.locator("#og_status").inner_text()
            bible_visible = page.locator("#og_bible_card").is_visible()
            assert len(status_text.strip()) > 0 or bible_visible, f"[{feature}][{mode}] 既无状态提示也无设定卡片"

        elif feature == "outline":
            page.goto(f"{live_server}/#original")
            page.wait_for_load_state("networkidle")
            page.fill("#og_title", f"大纲容错_{mode}")
            page.fill("#og_genre", "都市")
            page.fill("#og_setting", "测试在大纲推演异常下的系统容错能力。")
            page.locator("#btn_step1_next").click()
            page.wait_for_timeout(200)

            btn = page.locator("#btn_outline")
            assert btn.is_visible()
            btn.click()
            for _ in range(20):
                page.wait_for_timeout(250)
                if btn.is_enabled():
                    break
            assert btn.is_enabled(), f"[{feature}][{mode}] 规划按钮被锁死未复原"

            status_text = page.locator("#og_status").inner_text()
            outline_editor_text = page.locator("#og_outline_editor").inner_text()
            assert len(status_text.strip()) > 0 or len(outline_editor_text.strip()) > 0, f"[{feature}][{mode}] 既无状态提示也无大纲提示"

        elif feature == "generate-variants":
            title = f"小样容错测试_{mode}"
            page.goto(live_server)
            page.wait_for_load_state("networkidle")
            page.evaluate(f"""() => {{
                return fetch('/api/novels/import-txt', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{
                        title: {json.dumps(title)},
                        text: '第1章 起始\\n前文正文片段，测试生成走向小样。'
                    }})
                }});
            }}""")
            page.wait_for_timeout(200)
            page.evaluate(f"openContinueCard({json.dumps(title)}, 'continuation')")
            page.wait_for_timeout(300)

            var_btn = page.locator("#rm_trigger_variants_btn")
            assert var_btn.is_visible()
            var_btn.click()
            page.wait_for_timeout(800)

            # 验证操作按钮仍可点击（重试按钮或关闭按钮）
            assert page.locator("#rm_cancel").is_enabled(), f"[{feature}][{mode}] 取消按钮被锁死"
            assert var_btn.is_enabled(), f"[{feature}][{mode}] 生成小样按钮被锁死"

            cards_box_text = page.locator("#rm_variants_cards").inner_text()
            assert len(cards_box_text.strip()) > 0, f"[{feature}][{mode}] 走向小样容器完全空白"

        # 核心通用断言：页面文本绝对不含未处理的 JS 占位符
        body_text = page.locator("body").inner_text()
        assert "undefined" not in body_text, f"[{feature}][{mode}] 页面出现了 'undefined'！"
        assert "null" not in body_text, f"[{feature}][{mode}] 页面出现了 'null'！"
        assert "[object Object]" not in body_text, f"[{feature}][{mode}] 页面出现了 '[object Object]'！"

        # 页面绝对不能有未捕获的全局 JS 异常导致瘫痪
        assert len(monitor.page_errors) == 0, f"[{feature}][{mode}] 产生未捕获 JS 异常: {monitor.page_errors}"

    finally:
        FakeLLMState.reset()
