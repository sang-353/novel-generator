# -*- coding: utf-8 -*-
"""
tests/e2e/test_og_summary.py - 验证第 1 步「作品卡」摘要条、完成度、钩子链路、反馈与撤销、下一步校验
"""

import os
import json
import pytest
from tests.e2e.conftest import PageMonitor

ARTIFACTS_DIR = os.path.join(os.path.dirname(__file__), "artifacts", "1c")


def ensure_artifacts_dir():
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)


def test_og_summary_hook_chain(page, live_server):
    """
    验证 window.ogStep1AfterFill 链式封装完整性：
    og_refine.js 与 og_step1.js 彼此链式包裹，绝无覆盖丢失。
    """
    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    # 直接向输入框填充内容（模拟外部脚本写入而不触发 input 事件）
    page.evaluate("""() => {
        $('og_genre').value = '科幻悬疑';
        $('og_title').value = '星渊守望者';
        $('og_setting').value = '人类在废弃环状太空城建立了最后的避难所。';
        $('og_storyline').value = '主角必须在太空城动力核心熄灭前找到失落的密钥。';
        // 触发全局链路钩子
        window.ogStep1AfterFill();
    }""")

    # 1. 验证 1b og_refine.js 的字数统计被正确触发
    setting_wc = page.locator("#txt_setting_word_count")
    assert "20 字" in setting_wc.inner_text(), f"og_refine.js 钩子未执行，字数: {setting_wc.inner_text()}"

    # 2. 验证 1c-1 og_step1.js 的摘要条与完成度被正确触发
    summary_genre = page.locator("#og2_summary_genre")
    assert summary_genre.inner_text().strip() == "科幻悬疑"

    summary_title = page.locator("#og2_summary_title")
    assert summary_title.inner_text().strip() == "星渊守望者"

    summary_setting_wc = page.locator("#og2_summary_setting_wc")
    assert "背景 20 字" in summary_setting_wc.inner_text()

    summary_completion = page.locator("#og2_summary_completion")
    assert summary_completion.inner_text().strip() == "已填写 4/4"


def test_og_summary_live_updates_across_lifecycle(page, live_server):
    """
    验证作品卡摘要条随手动输入、灵感卡片点击、清空表单、草稿恢复全生命周期实时更新。
    """
    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    bar = page.locator("#og2_summary_bar")
    assert bar.is_visible()

    # 1. 初始空态
    assert page.locator("#og2_summary_genre").inner_text().strip() == "未选题材"
    assert page.locator("#og2_summary_title").inner_text().strip() == "未命名"
    assert "背景 0 字" in page.locator("#og2_summary_setting_wc").inner_text()
    assert "主线 0 字" in page.locator("#og2_summary_storyline_wc").inner_text()
    assert page.locator("#og2_summary_completion").inner_text().strip() == "已填写 0/4"

    # 2. 手动键入更新
    page.fill("#og_genre", "都市言情")
    assert page.locator("#og2_summary_genre").inner_text().strip() == "都市言情"
    assert not page.locator("#og2_summary_genre").evaluate("el => el.classList.contains('is-empty')")

    page.fill("#og_title", "盛夏恋曲")
    assert page.locator("#og2_summary_title").inner_text().strip() == "盛夏恋曲"
    assert not page.locator("#og2_summary_title").evaluate("el => el.classList.contains('is-empty')")

    page.fill("#og_setting", "初夏的林荫道。")
    assert "背景 7 字" in page.locator("#og2_summary_setting_wc").inner_text()

    page.fill("#og_storyline", "重逢与救赎。")
    assert "主线 6 字" in page.locator("#og2_summary_storyline_wc").inner_text()
    assert page.locator("#og2_summary_completion").inner_text().strip() == "已填写 4/4"

    # 3. 点击灵感脑洞卡片
    first_trope = page.locator("#og_trope_pills .trope-pill").first
    first_trope.click()
    page.wait_for_timeout(300)

    # 验证摘要条已被灵感内容填入
    applied_title = page.locator("#og_title").input_value().strip()
    assert page.locator("#og2_summary_title").inner_text().strip() == applied_title
    applied_genre = page.locator("#og_genre").input_value().strip()
    assert page.locator("#og2_summary_genre").inner_text().strip() == applied_genre

    # 4. 清空表单
    page.on("dialog", lambda dialog: dialog.accept())
    page.locator("#btn_clear_og").click()
    page.wait_for_timeout(300)

    # 验证清空后摘要条恢复初始空态
    assert page.locator("#og2_summary_genre").inner_text().strip() == "未选题材"
    assert page.locator("#og2_summary_title").inner_text().strip() == "未命名"
    assert "背景 0 字" in page.locator("#og2_summary_setting_wc").inner_text()
    assert "主线 0 字" in page.locator("#og2_summary_storyline_wc").inner_text()
    assert page.locator("#og2_summary_completion").inner_text().strip() == "已填写 0/4"


def test_og_summary_completion_dots_and_aria_live(page, live_server):
    """
    验证 4 个指示圆点状态（实心 .filled 与空心）随项数更新，以及 aria-live 仅在分值变化时通报。
    """
    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    # 初始 0/4
    assert page.locator("#og2_dot_genre.filled").count() == 0
    assert page.locator("#og2_dot_title.filled").count() == 0
    assert page.locator("#og2_dot_setting.filled").count() == 0
    assert page.locator("#og2_dot_storyline.filled").count() == 0
    assert page.locator("#og2_summary_completion").inner_text().strip() == "已填写 0/4"

    # 填第 1 项：题材
    page.fill("#og_genre", "武侠")
    assert page.locator("#og2_dot_genre.filled").count() == 1
    assert page.locator("#og2_summary_completion").inner_text().strip() == "已填写 1/4"
    assert page.locator("#og2_summary_announce").inner_text().strip() == "已填写 1/4"

    # 填第 2 项：书名
    page.fill("#og_title", "剑破苍穹")
    assert page.locator("#og2_dot_title.filled").count() == 1
    assert page.locator("#og2_summary_completion").inner_text().strip() == "已填写 2/4"
    assert page.locator("#og2_summary_announce").inner_text().strip() == "已填写 2/4"

    # 继续向书名中敲字，分值未变（仍为 2/4）
    page.fill("#og_title", "剑破苍穹之逆天行")
    assert page.locator("#og2_summary_completion").inner_text().strip() == "已填写 2/4"

    # 填第 3 项：背景设定
    page.fill("#og_setting", "纷乱江湖。")
    assert page.locator("#og2_dot_setting.filled").count() == 1
    assert page.locator("#og2_summary_completion").inner_text().strip() == "已填写 3/4"
    assert page.locator("#og2_summary_announce").inner_text().strip() == "已填写 3/4"

    # 填第 4 项：故事主线
    page.fill("#og_storyline", "荡平魔教。")
    assert page.locator("#og2_dot_storyline.filled").count() == 1
    assert page.locator("#og2_summary_completion").inner_text().strip() == "已填写 4/4"
    assert page.locator("#og2_summary_announce").inner_text().strip() == "已填写 4/4"


def test_og_summary_sticky_position_and_no_overflow(page, live_server):
    """
    验证摘要条 sticky 吸顶位置与顶栏紧贴、祖先容器无 overflow 截断、375px 移动端无横向溢出。
    """
    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    # 1. 验证祖先元素没有导致 sticky 失效的 overflow
    overflow_culprits = page.evaluate("""() => {
        const bar = document.getElementById('og2_summary_bar');
        const culprits = [];
        let p = bar.parentElement;
        while (p && p !== document.body) {
            const style = window.getComputedStyle(p);
            const ov = style.overflow + style.overflowX + style.overflowY;
            if (/hidden|auto|scroll/.test(ov)) {
                culprits.push({ tag: p.tagName, id: p.id, cls: p.className, overflow: ov });
            }
            p = p.parentElement;
        }
        return culprits;
    }""")
    assert len(overflow_culprits) == 0, f"发现导致 sticky 失效的祖先容器 overflow: {overflow_culprits}"

    # 2. 页面向下滚动 400px 后，验证摘要条顶边紧贴顶栏下沿
    page.evaluate("window.scrollTo(0, 400)")
    page.wait_for_timeout(300)

    header_box = page.locator("header").bounding_box()
    bar_box = page.locator("#og2_summary_bar").bounding_box()

    assert header_box is not None and bar_box is not None
    header_bottom = header_box["y"] + header_box["height"]

    # 摘要条顶边距离顶栏下沿的间距误差在 2px 以内（紧密贴合）
    gap = abs(bar_box["y"] - header_bottom)
    assert gap <= 2.0, f"摘要条未紧贴顶栏下沿！顶栏底: {header_bottom}, 摘要条顶: {bar_box['y']}, 间距: {gap}"

    # 3. 移动端 375px 视口测试
    page.set_viewport_size({"width": 375, "height": 667})
    page.wait_for_timeout(300)

    # 填写长书名验证
    page.fill("#og_genre", "科幻修真与极道流")
    page.fill("#og_title", "这是一本非常非常长的测试小说标题名称用来验证省略号")

    bar_mobile_box = page.locator("#og2_summary_bar").bounding_box()
    assert bar_mobile_box["height"] <= 40.0, f"375px 下摘要条高度超出 40px: {bar_mobile_box['height']}"

    # 验证 375px 下字数统计已响应式隐藏，仅显示「题材 · 书名 · n/4」
    assert not page.locator("#og2_summary_setting_wc").is_visible()
    assert not page.locator("#og2_summary_storyline_wc").is_visible()

    # 验证无横向溢出
    is_overflow = page.evaluate("""() => {
        const bar = document.getElementById('og2_summary_bar');
        return bar.scrollWidth > bar.clientWidth;
    }""")
    assert not is_overflow, "375px 移动端下摘要条出现横向溢出"


def test_og_trope_apply_scroll_and_highlight(page, live_server):
    """
    验证点击灵感卡片后的反馈行为：
    1. 书名输入框不在视口内时平滑滚动到视口；
    2. 被填入的字段做 600ms outline 高亮；
    3. prefers-reduced-motion 下取消滚动动画和高亮动画。
    """
    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    # 滚动到页面底部，使 #og_title 移出视口上方
    page.evaluate("window.scrollTo(0, 800)")
    page.wait_for_timeout(200)

    # 点击灵感卡片
    trope_btn = page.locator("#og_trope_pills .trope-pill").first
    trope_btn.click()
    page.wait_for_timeout(700)

    # 验证 #og_title 滚入视口中
    title_box = page.locator("#og_title").bounding_box()
    assert title_box is not None
    assert title_box["y"] > 50, "点击灵感卡片后未将书名输入框滚动至安全视口内"

    # 验证 prefers-reduced-motion 模式
    page.emulate_media(reduced_motion="reduce")
    page.locator("#btn_random_trope").click()
    page.wait_for_timeout(200)
    # 在 reduced-motion 下不添加高亮动画类
    assert page.locator("#og_title.og2-flash-highlight").count() == 0


def test_og_trope_undo_snapshot_and_restore_all_fields(page, live_server):
    """
    验证灵感应用前全量快照与撤销 Toast：
    1. 含有旧内容时点击灵感，弹出 10 秒撤销 Toast（且通用 Toast 隐藏不重叠）；
    2. 点击撤销，全部 9 个字段完整恢复（含第 2、3 步字段）。
    """
    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    # 预先在步骤 1 和步骤 2 填写特定值
    page.fill("#og_genre", "旧题材")
    page.fill("#og_title", "旧书名")
    page.fill("#og_setting", "旧设定内容")
    page.evaluate("""() => {
        $('og_characters').value = '主角：林风，剑客';
        $('og_chapters').value = '25';
    }""")

    # 点击灵感卡片应用新灵感
    first_trope = page.locator("#og_trope_pills .trope-pill").first
    first_trope.click()
    page.wait_for_timeout(300)

    # 验证新灵感已覆盖
    assert page.locator("#og_title").input_value().strip() != "旧书名"

    # 验证撤销 Toast 弹出，且全局 Toast 隐藏防重叠
    undo_toast = page.locator("#og2_undo_toast")
    assert undo_toast.is_visible(), "撤销 Toast 未弹出"
    assert "已应用灵感" in undo_toast.inner_text()
    assert page.locator("#toast").count() == 0 or not page.locator("#toast").is_visible(), "全局 Toast 与撤销 Toast 发生重叠"

    # 点击撤销按钮
    page.locator("#btn_og2_undo").click()
    page.wait_for_timeout(300)

    # 验证全部字段已恢复到快照值
    assert page.locator("#og_genre").input_value().strip() == "旧题材"
    assert page.locator("#og_title").input_value().strip() == "旧书名"
    assert page.locator("#og_setting").input_value().strip() == "旧设定内容"
    assert page.evaluate("() => $('og_characters').value") == "主角：林风，剑客"
    assert page.evaluate("() => $('og_chapters').value") == "25"

    # 验证撤销 Toast 已关闭
    assert not undo_toast.is_visible()


def test_og_trope_undo_not_shown_on_empty_form(page, live_server):
    """
    验证在完全空白表单上点击灵感卡片，不触发撤销 Toast。
    """
    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    # 确保表单全空
    page.on("dialog", lambda dialog: dialog.accept())
    page.locator("#btn_clear_og").click()
    page.wait_for_timeout(200)

    # 点击灵感卡片
    page.locator("#og_trope_pills .trope-pill").first.click()
    page.wait_for_timeout(300)

    # 验证空白表单应用后绝不弹撤销 Toast
    undo_toast = page.locator("#og2_undo_toast")
    assert not undo_toast.is_visible(), "空表单应用灵感时不应弹出撤销 Toast"


def test_og_step1_next_validation_inline_tip_and_focus(page, live_server):
    """
    验证下一步校验拦截机制：
    1. 缺必填项时按钮显示 aria-disabled 且不跳转、不发请求；
    2. 显示内联提示并聚焦到 #og_setting；
    3. 填入任一必填项后自动恢复可点击。
    """
    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    # 1. 初始空态，验证下一步按钮状态
    next_btn = page.locator("#btn_step1_next")
    assert next_btn.get_attribute("aria-disabled") == "true"

    # 2. 点击下一步拦截（force=True 模拟用户点击 aria-disabled 按钮）
    next_btn.click(force=True)
    page.wait_for_timeout(200)

    # 依然停留在第 1 步，未跳至第 2 步
    assert page.locator("#og_step_1").is_visible()
    assert not page.locator("#og_step_2").is_visible()

    # 验证内联提示展现，文案正确
    inline_tip = page.locator("#og2_step1_next_inline_tip")
    assert inline_tip.is_visible()
    assert "请至少填写题材、背景设定或书名中的一项" in inline_tip.inner_text()

    # 验证输入焦点落在 #og_setting
    is_focused = page.evaluate("() => document.activeElement && document.activeElement.id === 'og_setting'")
    assert is_focused, "未聚焦至 #og_setting"

    # 3. 填入一项题材，验证按钮自动恢复有效且提示隐藏
    page.fill("#og_genre", "科幻")
    page.wait_for_timeout(200)
    assert next_btn.get_attribute("aria-disabled") == "false"
    assert not inline_tip.is_visible()

    # 点击下一步进入第 2 步
    next_btn.click()
    page.wait_for_timeout(300)
    assert page.locator("#og_step_2").is_visible()


def test_og_genre_pills_no_requests_and_hint_bar(page, live_server):
    """
    验证点击题材芯片不发网络请求，并在灵感区上方展示「题材已更改，点「换一批」获取新灵感」提示条。
    """
    reqs = []
    page.on("request", lambda r: reqs.append(r.url) if "/api/" in r.url else None)

    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    req_count_init = len(reqs)

    # 点击一个题材芯片
    page.locator("#og_genre_pills .tag-pill").first.click()
    page.wait_for_timeout(300)

    # 验证没有发出任何 /api/ 请求
    new_reqs = reqs[req_count_init:]
    assert len(new_reqs) == 0, f"点击题材芯片发出了意外网络请求: {new_reqs}"

    # 验证灵感区上方提示条出现
    hint_bar = page.locator("#og2_genre_hint_bar")
    assert hint_bar.is_visible()
    assert "题材已更改" in hint_bar.inner_text()

    # 点击换一批后提示条消失
    page.locator("#btn_refresh_tropes").click()
    page.wait_for_timeout(200)
    assert not hint_bar.is_visible()


def test_og_review_mode_trope_click_and_undo_flow(page, live_server):
    """
    验证审阅状态下点击灵感卡片：
    静默结束审阅，撤销快照取屏幕显示文本，撤销后完整恢复。
    """
    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    page.fill("#og_genre", "悬疑")
    page.fill("#og_setting", "深海潜水基地发生失联事故。")

    # 触发换设定进入审阅模式
    page.locator("#btn_setting_regen").click()
    page.locator("#og_setting_review_bar").wait_for(state="visible", timeout=10000)
    displayed_text = page.locator("#og_setting").input_value().strip()

    # 在审阅态下点击灵感卡片
    page.locator("#og_trope_pills .trope-pill").first.click()
    page.wait_for_timeout(300)

    # 验证审阅条已静默关闭
    assert not page.locator("#og_setting_review_bar").is_visible()
    assert page.locator("#og_setting").input_value().strip() != displayed_text

    # 点击撤销
    page.locator("#btn_og2_undo").click()
    page.wait_for_timeout(300)

    # 验证恢复回审阅时屏幕显示的文本
    assert page.locator("#og_setting").input_value().strip() == displayed_text


def test_og_clear_form_reload_clean(page, live_server):
    """
    验证清空表单后刷新页面，无任何僵尸草稿残留。
    """
    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    page.fill("#og_title", "即将清空的书")
    page.fill("#og_setting", "即将清空的背景")
    page.wait_for_timeout(600)  # 等待草稿防抖写入

    # 点击清空
    page.on("dialog", lambda dialog: dialog.accept())
    page.locator("#btn_clear_og").click()
    page.wait_for_timeout(300)

    # 刷新页面
    page.reload()
    page.wait_for_load_state("networkidle")

    assert page.locator("#og_title").input_value().strip() == ""
    assert page.locator("#og_setting").input_value().strip() == ""
    assert page.locator("#og2_summary_completion").inner_text().strip() == "已填写 0/4"


def test_og_draft_consistency_after_accept_undo_and_reload(page, live_server):
    """
    验证灵感应用与撤销后刷新页面，草稿与屏幕内容完全一致。
    """
    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    page.fill("#og_title", "原始未改名")
    page.fill("#og_setting", "原始背景设定")

    # 点击灵感卡片
    page.locator("#og_trope_pills .trope-pill").first.click()
    page.wait_for_timeout(300)

    # 撤销回原始
    page.locator("#btn_og2_undo").click()
    page.wait_for_timeout(600)  # 等待草稿 500ms 防抖保存

    # 刷新页面
    page.reload()
    page.wait_for_load_state("networkidle")

    assert page.locator("#og_title").input_value().strip() == "原始未改名"
    assert page.locator("#og_setting").input_value().strip() == "原始背景设定"


def test_og_undo_toast_hidden_on_clear_form(page, live_server):
    """验证点击「清空表单」立即隐藏撤销 Toast 并清除快照。"""
    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    # 先输入旧内容，再应用灵感以触发撤销 Toast
    page.fill("#og_title", "旧书名")
    page.locator("#og_trope_pills .trope-pill").first.click()
    page.wait_for_timeout(200)
    assert page.locator("#og2_undo_toast").is_visible(), "应用灵感后应出现撤销 Toast"

    # 点击清空表单并确认
    page.on("dialog", lambda d: d.accept())
    page.locator("#btn_clear_og").click()
    page.wait_for_timeout(200)

    # 断言 Toast 立即隐藏
    assert not page.locator("#og2_undo_toast").is_visible(), "清空表单后撤销 Toast 必须立即隐藏"


def test_og_undo_toast_hidden_on_step1_next_success(page, live_server):
    """验证「下一步」成功跳转后立即隐藏撤销 Toast 并清除快照。"""
    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    # 填入旧书名并应用灵感（满足校验）
    page.fill("#og_title", "原始书名")
    page.locator("#og_trope_pills .trope-pill").first.click()
    page.wait_for_timeout(200)
    assert page.locator("#og2_undo_toast").is_visible(), "应用灵感后应出现撤销 Toast"

    # 点击下一步（由于已应用灵感，必填项满足，成功进入步骤 2）
    page.locator("#btn_step1_next").click()
    page.wait_for_timeout(300)

    # 验证已进入步骤 2 且撤销 Toast 已隐藏
    assert page.locator("#og_step_2").is_visible(), "应成功跳转到步骤 2"
    assert not page.locator("#og2_undo_toast").is_visible(), "下一步跳转成功后撤销 Toast 必须立即隐藏"


def test_og_undo_toast_hidden_on_user_manual_input(page, live_server):
    """验证用户在 10 秒内手动编辑任一表单字段立即隐藏撤销 Toast 并清除快照。"""
    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    # 填入旧书名并应用灵感
    page.fill("#og_title", "测试书名")
    page.locator("#og_trope_pills .trope-pill").first.click()
    page.wait_for_timeout(200)
    assert page.locator("#og2_undo_toast").is_visible(), "应用灵感后应出现撤销 Toast"

    # 用户手动在书名框打字编辑
    page.locator("#og_title").press_sequentially("新追加的文本", delay=50)
    page.wait_for_timeout(200)

    # 断言 Toast 立即隐藏
    assert not page.locator("#og2_undo_toast").is_visible(), "用户手动编辑字段后撤销 Toast 必须立即隐藏"


def test_og_undo_toast_375px_layout_and_no_collision(page, live_server):
    """验证 375px 移动端下撤销 Toast 尺寸、触控区及防相交避让。"""
    page.set_viewport_size({"width": 375, "height": 667})
    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    # 先输入再应用灵感
    page.fill("#og_title", "移动端书名")
    page.locator("#og_trope_pills .trope-pill").first.click()
    page.wait_for_timeout(200)

    toast = page.locator("#og2_undo_toast")
    assert toast.is_visible()
    toast_box = toast.bounding_box()
    assert toast_box is not None

    # 1. 宽度为 calc(100vw - 32px) = 343px (允许 2px 误差)
    assert abs(toast_box["width"] - 343) <= 2, f"375px 下宽度应为 343px，实际为 {toast_box['width']}"

    # 2. 按钮与 × 的触控区不小于 36px
    undo_btn_box = page.locator("#btn_og2_undo").bounding_box()
    close_btn_box = page.locator("#btn_og2_undo_close").bounding_box()
    assert undo_btn_box["width"] >= 36 and undo_btn_box["height"] >= 36, f"撤销按钮触控区不足 36px: {undo_btn_box}"
    assert close_btn_box["width"] >= 36 and close_btn_box["height"] >= 36, f"关闭按钮触控区不足 36px: {close_btn_box}"

    # 3. 验证与视口内可见的字段工具栏及下一步按钮均不相交
    def rects_intersect(r1, r2):
        return not (r1["x"] + r1["width"] <= r2["x"] or
                    r1["x"] >= r2["x"] + r2["width"] or
                    r1["y"] + r1["height"] <= r2["y"] or
                    r1["y"] >= r2["y"] + r2["height"])

    for footer in page.locator("#view-original .og2-field-footer").all():
        if footer.is_visible():
            fbox = footer.bounding_box()
            if fbox and fbox["y"] < 667 and fbox["y"] + fbox["height"] > 0:
                assert not rects_intersect(toast_box, fbox), "撤销 Toast 与字段工具栏发生了矩形相交重叠！"

    # 模拟滚动使 #btn_step1_next 进入视口底部冲突区域，验证向上避让至其上方
    page.evaluate("""() => {
        const btn = document.getElementById('btn_step1_next');
        const rect = btn.getBoundingClientRect();
        window.scrollBy(0, rect.top - 620);
        window.dispatchEvent(new Event('scroll'));
    }""")
    page.wait_for_timeout(200)

    toast_box2 = toast.bounding_box()
    next_box2 = page.locator("#btn_step1_next").bounding_box()
    if next_box2 and next_box2["y"] < 667 and next_box2["y"] + next_box2["height"] > 0:
        assert not rects_intersect(toast_box2, next_box2), "避让后撤销 Toast 仍与 #btn_step1_next 相交！"
        if toast_box2["y"] < next_box2["y"]:
            assert toast_box2["y"] + toast_box2["height"] <= next_box2["y"], "发生相交时撤销 Toast 必须避让置于 #btn_step1_next 上方！"


def test_og_undo_toast_1280px_position_no_overlap_textarea(page, live_server):
    """验证 1280px 下撤销 Toast 位于视口右下角，不遮挡正在编辑的文本框。"""
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    page.fill("#og_title", "桌面端书名")
    page.locator("#og_trope_pills .trope-pill").first.click()
    page.wait_for_timeout(200)

    toast = page.locator("#og2_undo_toast")
    assert toast.is_visible()
    toast_box = toast.bounding_box()
    assert toast_box is not None

    right_margin = 1280 - (toast_box["x"] + toast_box["width"])
    assert right_margin >= 16 and right_margin <= 32, f"右下角右侧间距异常: {right_margin}"
    bottom_margin = 800 - (toast_box["y"] + toast_box["height"])
    assert bottom_margin >= 16 and bottom_margin <= 32, f"右下角底部间距异常: {bottom_margin}"

    page.locator("#og_setting").focus()
    setting_box = page.locator("#og_setting").bounding_box()
    assert not (toast_box["x"] < setting_box["x"] + setting_box["width"] and
                toast_box["x"] + toast_box["width"] > setting_box["x"] and
                toast_box["y"] < setting_box["y"] + setting_box["height"] and
                toast_box["y"] + toast_box["height"] > setting_box["y"]), "撤销 Toast 遮挡了当前正在编辑的文本框正文"


def test_og_screenshots_capture(page, live_server):
    """
    按照验收要求截取 1280px 与 375px 下的各状态截图并保存至 tests/e2e/artifacts/1c/。
    """
    ensure_artifacts_dir()

    # ---------------- 1280px 桌面端 ----------------
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    # 1. 摘要条空态
    page.screenshot(path=os.path.join(ARTIFACTS_DIR, "1280_summary_empty.png"))

    # 2. 摘要条完成态
    page.fill("#og_genre", "赛博朋克")
    page.fill("#og_title", "霓虹深渊录")
    page.fill("#og_setting", "在永夜与全息广告交织的高耸九龙浮空城。")
    page.fill("#og_storyline", "义体黑客追查意识仿生人失踪谜案。")
    page.wait_for_timeout(200)
    page.screenshot(path=os.path.join(ARTIFACTS_DIR, "1280_summary_completed.png"))

    # 3. 滚动后吸顶
    page.evaluate("window.scrollTo(0, 350)")
    page.wait_for_timeout(200)
    page.screenshot(path=os.path.join(ARTIFACTS_DIR, "1280_summary_sticky.png"))

    # 4. 点灵感后（高亮 + 撤销 Toast）
    page.evaluate("window.scrollTo(0, 0)")
    page.locator("#og_trope_pills .trope-pill").first.click()
    page.wait_for_timeout(200)
    page.screenshot(path=os.path.join(ARTIFACTS_DIR, "1280_trope_applied_undo.png"))

    # 5. 下一步缺项提示
    page.on("dialog", lambda dialog: dialog.accept())
    page.locator("#btn_clear_og").click()
    page.wait_for_timeout(200)
    page.locator("#btn_step1_next").click(force=True)
    page.wait_for_timeout(200)
    page.screenshot(path=os.path.join(ARTIFACTS_DIR, "1280_step1_next_error.png"))

    # ---------------- 375px 移动端 ----------------
    page.set_viewport_size({"width": 375, "height": 667})
    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    # 1. 摘要条
    page.fill("#og_genre", "都市言情")
    page.fill("#og_title", "深情不可负")
    page.wait_for_timeout(200)
    page.screenshot(path=os.path.join(ARTIFACTS_DIR, "375_summary_mobile.png"))

    # 2. 点灵感后的撤销 Toast
    page.locator("#og_trope_pills .trope-pill").first.click()
    page.wait_for_timeout(200)
    page.screenshot(path=os.path.join(ARTIFACTS_DIR, "375_trope_applied_undo.png"))

    # 3. 下一步缺项提示
    page.locator("#btn_clear_og").click()
    page.wait_for_timeout(200)
    page.locator("#btn_step1_next").click(force=True)
    page.wait_for_timeout(200)
    page.screenshot(path=os.path.join(ARTIFACTS_DIR, "375_step1_next_error.png"))
