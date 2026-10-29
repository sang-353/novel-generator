# -*- coding: utf-8 -*-
"""
tests/e2e/test_og_refine.py - 故事背景与故事主线 AI 辅助写作前端交互与状态机 E2E 测试
覆盖场景：
1. 按钮初始禁用状态与基于输入的动态启用/禁用、title 提示；
2. 加载中状态（readonly、aria-busy、微光脉冲 shimmer、图标旋转、取消按钮显隐）；
3. 取消逻辑（AbortController 中断、恢复原文本、无锁死可再次触发）；
4. 审阅模式（原版/新版分段切换、aria-pressed、保留编辑、保留此版与撤回）；
5. 二次编辑保护（新版上手动修改后切换到原版再切回，编辑内容不丢失）；
6. 状态机独立性（故事背景与故事主线互不干扰）；
7. 审阅状态直接点击「下一步」无缝读取当前显示版本；
8. 内联友好错误横幅（非阻塞 alert、可手动关闭）；
9. 375px 移动端单行无折行布局；
10. 5 张视觉验收截图导出至 tests/e2e/artifacts/。
"""

import json
from pathlib import Path
import pytest

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


def test_step1_refine_button_states_and_tooltips(page, live_server):
    """验证按钮初始状态及随输入动态切换启用/禁用与 tooltip 提示。"""
    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    # 1. 初始空状态检查
    btn_s_regen = page.locator("#btn_setting_regen")
    btn_s_polish = page.locator("#btn_setting_polish")
    btn_s_expand = page.locator("#btn_setting_expand")

    btn_l_regen = page.locator("#btn_storyline_regen")
    btn_l_polish = page.locator("#btn_storyline_polish")
    btn_l_expand = page.locator("#btn_storyline_expand")

    # 换个设定/主线：因题材和书名均为空，初始禁用
    assert btn_s_regen.is_disabled()
    assert btn_s_regen.get_attribute("title") == "请先选择题材或填写书名"
    assert btn_l_regen.is_disabled()
    assert btn_l_regen.get_attribute("title") == "请先选择题材或填写书名"

    # 润色/扩充：因正文内容为空，初始禁用
    assert btn_s_polish.is_disabled()
    assert btn_s_polish.get_attribute("title") == "请先写一点内容"
    assert btn_s_expand.is_disabled()
    assert btn_l_polish.is_disabled()
    assert btn_l_expand.is_disabled()

    # 2. 输入题材 -> 换个设定/换个主线 启用
    page.fill("#og_genre", "科幻修真")
    page.wait_for_timeout(100)
    assert not btn_s_regen.is_disabled()
    assert not btn_l_regen.is_disabled()
    assert not btn_s_regen.get_attribute("title")

    # 清空题材 -> 重新禁用
    page.fill("#og_genre", "")
    page.wait_for_timeout(100)
    assert btn_s_regen.is_disabled()
    assert btn_l_regen.is_disabled()

    # 3. 输入书名 -> 换个设定/换个主线 启用
    page.fill("#og_title", "赛博道祖")
    page.wait_for_timeout(100)
    assert not btn_s_regen.is_disabled()
    assert not btn_l_regen.is_disabled()

    # 4. 输入故事背景 -> 背景的润色/扩充 启用，主线的保持禁用
    page.fill("#og_setting", "在近未来赛博世界中，机械修士占据主导。")
    page.wait_for_timeout(100)
    assert not btn_s_polish.is_disabled()
    assert not btn_s_expand.is_disabled()
    assert btn_l_polish.is_disabled()
    assert btn_l_expand.is_disabled()

    # 5. 输入故事主线 -> 主线的润色/扩充 启用
    page.fill("#og_storyline", "主角打破阶级壁垒，重构灵气网络。")
    page.wait_for_timeout(100)
    assert not btn_l_polish.is_disabled()
    assert not btn_l_expand.is_disabled()


def test_step1_refine_loading_and_cancel_lifecycle(page, live_server):
    """验证加载中状态（readonly、aria-busy、微光 shimmer、取消按钮）及 Abort 取消无锁死。"""
    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    pending_routes = []
    page.route("**/api/refine-field", lambda route: pending_routes.append(route))

    page.fill("#og_genre", "赛博朋克")
    page.fill("#og_setting", "原始背景：九龙城寨旧址。")

    btn_regen = page.locator("#btn_setting_regen")
    btn_cancel = page.locator("#btn_setting_cancel")
    txt_setting = page.locator("#og_setting")

    # 触发换个设定
    btn_regen.click()
    page.wait_for_timeout(150)

    # 断言加载中样式与状态
    assert txt_setting.get_attribute("readonly") is not None
    assert txt_setting.get_attribute("aria-busy") == "true"
    assert "og2-shimmer" in (txt_setting.get_attribute("class") or "")
    assert btn_cancel.is_visible()
    assert btn_regen.locator("svg.og2-spin").count() == 1

    # 点击取消按钮
    btn_cancel.click()
    page.wait_for_timeout(200)

    # 验证取消后：内容恢复原始文本，加载样式与标记清除，取消按钮隐藏
    assert txt_setting.input_value() == "原始背景：九龙城寨旧址。"
    assert txt_setting.get_attribute("readonly") is None
    assert txt_setting.get_attribute("aria-busy") is None
    assert "og2-shimmer" not in (txt_setting.get_attribute("class") or "")
    assert not btn_cancel.is_visible()

    # 验证用例 10：取消后再次点击对应按钮，必须能重新发起请求，不能锁死
    page.unroute("**/api/refine-field")
    page.route(
        "**/api/refine-field",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"text": "【第二次发起成功】全新赛博世界法则。"}),
        ),
    )

    btn_regen.click()
    page.wait_for_timeout(300)
    review_bar = page.locator("#og_setting_review_bar")
    assert review_bar.is_visible(), "取消后重新点击换个设定，必须能够再次成功发起并进入审阅模式"


def test_step1_refine_review_mode_toggle_and_edit_preservation(page, live_server):
    """验证审阅模式的原版/新版切换、aria-pressed 状态及二次手动编辑保护。"""
    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    ai_text = "【AI 润色版】在霓虹与阴影交错的巨构都市深处，人类在机械轰鸣中寻找灵魂的归宿。"
    page.route(
        "**/api/refine-field",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"text": ai_text}),
        ),
    )

    orig_text = "原始设定：一个有很多霓虹灯的赛博大都市。"
    page.fill("#og_setting", orig_text)
    page.fill("#og_genre", "赛博朋克")

    # 点击润色
    page.locator("#btn_setting_polish").click()
    page.wait_for_timeout(300)

    # 1. 验证进入审阅模式
    toolbar = page.locator("#og_setting_toolbar")
    review_bar = page.locator("#og_setting_review_bar")
    btn_view_orig = page.locator("#btn_setting_view_orig")
    btn_view_new = page.locator("#btn_setting_view_new")
    txt_setting = page.locator("#og_setting")

    assert not toolbar.is_visible()
    assert review_bar.is_visible()
    # 默认展示新版
    assert "active" in (btn_view_new.get_attribute("class") or "")
    assert btn_view_new.get_attribute("aria-pressed") == "true"
    assert btn_view_orig.get_attribute("aria-pressed") == "false"
    assert txt_setting.input_value() == ai_text

    # 2. 点击原版
    btn_view_orig.click()
    page.wait_for_timeout(100)
    assert "active" in (btn_view_orig.get_attribute("class") or "")
    assert btn_view_orig.get_attribute("aria-pressed") == "true"
    assert btn_view_new.get_attribute("aria-pressed") == "false"
    assert txt_setting.input_value() == orig_text

    # 3. 切回新版并在新版上手动修改
    btn_view_new.click()
    page.wait_for_timeout(100)
    assert txt_setting.input_value() == ai_text

    manual_addition = "（人工二次微调：补充三大财阀设定）"
    edited_text = ai_text + manual_addition
    page.fill("#og_setting", edited_text)
    page.wait_for_timeout(100)

    # 4. 再次切到原版，验证原版未被污染
    btn_view_orig.click()
    page.wait_for_timeout(100)
    assert txt_setting.input_value() == orig_text

    # 5. 再次切回新版，验证人工二次编辑内容被完整暂存保留！
    btn_view_new.click()
    page.wait_for_timeout(100)
    assert txt_setting.input_value() == edited_text


def test_step1_refine_accept_and_revert(page, live_server):
    """验证「撤回」与「保留此版」功能及状态机恢复至 idle。"""
    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    ai_text = "【AI 扩充版】悬空浮岛与地表废土的对立生态体系。"
    page.route(
        "**/api/refine-field",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"text": ai_text}),
        ),
    )

    orig_text = "旧设定：废土与浮岛。"
    page.fill("#og_setting", orig_text)
    page.fill("#og_genre", "废土科幻")

    # ---- 测试撤回 ----
    page.locator("#btn_setting_expand").click()
    page.wait_for_timeout(300)

    btn_revert = page.locator("#btn_setting_revert")
    btn_accept = page.locator("#btn_setting_accept")
    txt_setting = page.locator("#og_setting")
    toolbar = page.locator("#og_setting_toolbar")
    review_bar = page.locator("#og_setting_review_bar")

    assert review_bar.is_visible()
    btn_revert.click()
    page.wait_for_timeout(200)

    assert txt_setting.input_value() == orig_text
    assert not review_bar.is_visible()
    assert toolbar.is_visible()

    # ---- 测试用例 10：保留/撤回后再次点击对应按钮，必须能重新发起请求，不能锁死 ----
    page.locator("#btn_setting_expand").click()
    page.wait_for_timeout(300)
    assert review_bar.is_visible()

    # ---- 测试保留此版 ----
    btn_accept.click()
    page.wait_for_timeout(200)

    assert txt_setting.input_value() == ai_text
    assert not review_bar.is_visible()
    assert toolbar.is_visible()


def test_step1_refine_independent_state_machines(page, live_server):
    """验证用例 11：在背景正在生成的 loading 状态下，主线的按钮不应被禁用，仍可独立发起主线的请求。"""
    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    pending_setting_routes = []

    def route_handler(route):
        req_data = json.loads(route.request.post_data or "{}")
        field = req_data.get("field")
        if field == "setting":
            pending_setting_routes.append(route)
        else:
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"text": "快速主线生成完成"}),
            )

    page.route("**/api/refine-field", route_handler)

    page.fill("#og_genre", "刑侦推理")
    page.fill("#og_setting", "背景内容：暴风雨中的海岛孤舟。")
    page.fill("#og_storyline", "主线内容：探寻连环失踪案件真凶。")

    # 1. 触发背景的扩充
    page.locator("#btn_setting_expand").click()
    page.wait_for_timeout(150)

    # 断言背景处于 loading 状态（取消按钮可见）
    assert page.locator("#btn_setting_cancel").is_visible()

    # 2. 验证用例 11：主线的按钮绝不被背景的 loading 禁用！
    btn_l_polish = page.locator("#btn_storyline_polish")
    assert not btn_l_polish.is_disabled(), "用例 11 失败：背景生成中时，主线按钮不应被禁用"

    # 3. 独立点击主线润色
    btn_l_polish.click()
    page.wait_for_timeout(300)

    # 断言主线率先进入审阅模式
    assert page.locator("#og_storyline_review_bar").is_visible()
    assert page.locator("#og_storyline").input_value() == "快速主线生成完成"

    # 响应背景的请求
    if pending_setting_routes:
        pending_setting_routes[0].fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"text": "背景慢生成完成"}),
        )
        page.wait_for_timeout(200)
        assert page.locator("#og_setting_review_bar").is_visible()


def test_step1_refine_step1_next_reads_current_display_during_review(page, live_server):
    """验证用例 12：审阅状态下直接点「下一步」，进入第 2 步且读到的是当前显示的版本。"""
    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    ai_setting = "【当前审阅中的 AI 背景】赛博世界观 2.0"
    page.route(
        "**/api/refine-field",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"text": ai_setting}),
        ),
    )

    page.fill("#og_title", "深渊之城")
    page.fill("#og_genre", "赛博朋克")
    page.fill("#og_setting", "初始背景")
    page.fill("#og_storyline", "主角挑战旧神统治。")

    # 触发背景润色，使其处于审阅状态中
    page.locator("#btn_setting_polish").click()
    page.wait_for_timeout(300)

    assert page.locator("#og_setting_review_bar").is_visible()
    assert page.locator("#og_setting").input_value() == ai_setting

    # 在审阅模式下直接点击「下一步」
    btn_next = page.locator("#btn_step1_next")
    btn_next.click()
    page.wait_for_timeout(300)

    # 断言成功推进到第 2 步（面板切换为 display: block）
    assert page.locator("#og_step_2").is_visible()
    assert not page.locator("#og_step_1").is_visible()

    # 读取前端 originalPayload() 验证设定字段值准确为当前展示的审阅内容
    payload = page.evaluate("() => typeof originalPayload === 'function' ? originalPayload() : null")
    assert payload is not None
    assert payload["setting"] == ai_setting


def test_step1_refine_error_banner_handling(page, live_server):
    """验证大模型失败或超时时展示内联错误横幅（非 alert），且可手动关闭。"""
    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    error_msg = "上游大模型连接超时，请检查网络或配置"
    page.route(
        "**/api/refine-field",
        lambda route: route.fulfill(
            status=502,
            content_type="application/json",
            body=json.dumps({"error": error_msg}),
        ),
    )

    page.fill("#og_genre", "都市言情")
    page.fill("#og_setting", "背景内容")

    # 监听 alert 对话框，确保不弹出原生 alert
    alerts = []
    page.on("dialog", lambda dialog: alerts.append(dialog.message))

    page.locator("#btn_setting_polish").click()
    page.wait_for_timeout(300)

    assert len(alerts) == 0, "严禁弹出原生 alert 阻断用户"
    err_banner = page.locator("#og_setting_err")
    err_text = page.locator("#og_setting_err_msg")

    assert err_banner.is_visible()
    assert error_msg in err_text.inner_text()

    # 点击关闭错误横幅
    page.locator("#btn_setting_err_close").click()
    page.wait_for_timeout(100)
    assert not err_banner.is_visible()


def test_step1_refine_mobile_375px_layout(page, live_server):
    """验证在 375px 窄屏视口下，工具栏按钮紧凑排列在单行内，不发生折行。"""
    page.set_viewport_size({"width": 375, "height": 667})
    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    page.fill("#og_genre", "都市异能")
    page.fill("#og_setting", "灵气复苏的现代都市。")
    page.wait_for_timeout(100)

    btn_regen = page.locator("#btn_setting_regen")
    btn_polish = page.locator("#btn_setting_polish")
    btn_expand = page.locator("#btn_setting_expand")
    cnt_words = page.locator("#txt_setting_word_count")

    assert btn_regen.is_visible()
    assert btn_polish.is_visible()
    assert btn_expand.is_visible()
    assert cnt_words.is_visible()

    box_regen = btn_regen.bounding_box()
    box_polish = btn_polish.bounding_box()
    box_expand = btn_expand.bounding_box()
    box_words = cnt_words.bounding_box()

    assert box_regen and box_polish and box_expand and box_words

    # 验证三个按钮垂直坐标一致（误差小于 2px），证明位于同一行无换行
    assert abs(box_regen["y"] - box_polish["y"]) < 2.0
    assert abs(box_polish["y"] - box_expand["y"]) < 2.0


def test_step1_refine_screenshots_capture(page, live_server):
    """捕获用户指定的 5 张验收截图并导出至 tests/e2e/artifacts/。"""
    # 1. 1280px 常规 idle 工具栏状态
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    page.fill("#og_genre", "赛博朋克")
    page.fill("#og_setting", "在九龙城寨旧址之上，各大跨国巨企以浮空矩阵划分领空，底层的义体流民在电子霓虹中苟延残喘。")
    page.fill("#og_storyline", "底层黑客偶然截获核心代码，引来顶层执政官的全力追杀。")
    page.wait_for_timeout(200)

    p1 = ARTIFACTS_DIR / "step1_toolbar_idle_1280.png"
    page.locator(".og2-inputs-group").screenshot(path=str(p1))
    assert p1.exists()

    # 2. 加载中微光脉冲状态
    pending_routes = []
    page.route("**/api/refine-field", lambda route: pending_routes.append(route))

    page.locator("#btn_setting_expand").click()
    page.wait_for_timeout(200)

    p2 = ARTIFACTS_DIR / "step1_refine_loading_shimmer.png"
    page.locator(".og2-inputs-group").screenshot(path=str(p2))
    assert p2.exists()

    # 3. 审阅模式对比状态
    if pending_routes:
        pending_routes[0].fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "text": "【AI 深度扩充世界法则】在九龙城寨旧址之上，各大跨国巨企以浮空矩阵划分领空，构建出严密的神经监控天网。底层义体流民在永不熄灭的霓虹辐射下苟延残喘，旧时代的黑市与赛博修仙门派在暗流中暗中结盟。"
            }),
        )
    page.wait_for_timeout(300)

    p3 = ARTIFACTS_DIR / "step1_refine_review_mode.png"
    page.locator(".og2-inputs-group").screenshot(path=str(p3))
    assert p3.exists()

    # 4. 错误提示横幅状态
    page.unroute("**/api/refine-field")
    page.route(
        "**/api/refine-field",
        lambda route: route.fulfill(
            status=502,
            content_type="application/json",
            body=json.dumps({"error": "大模型服务响应超时（502），请检查 API Key 配额或重试"}),
        ),
    )
    # 退出当前审阅
    page.locator("#btn_setting_accept").click()
    page.wait_for_timeout(200)

    page.locator("#btn_setting_polish").click()
    page.wait_for_timeout(300)

    p4 = ARTIFACTS_DIR / "step1_refine_error_banner.png"
    page.locator(".og2-inputs-group").screenshot(path=str(p4))
    assert p4.exists()

    # 5. 375px 窄屏移动端工具栏
    page.set_viewport_size({"width": 375, "height": 667})
    page.locator("#btn_setting_err_close").click()
    page.wait_for_timeout(200)

    p5 = ARTIFACTS_DIR / "step1_toolbar_mobile_375.png"
    page.locator(".og2-inputs-group").screenshot(path=str(p5))
    assert p5.exists()
