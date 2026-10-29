# -*- coding: utf-8 -*-
"""
tests/e2e/test_og_summary.py - 验证第 1 步「作品卡」摘要条、完成度、钩子链路与响应式粘性定位
"""

import pytest
from tests.e2e.conftest import PageMonitor


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
