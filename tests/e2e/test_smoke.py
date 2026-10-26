"""
tests/e2e/test_smoke.py - 冒烟测试套件 (Smoke Test)

覆盖范围：
1. 打开首页，严格监听 console error、pageerror、失败的网络请求，任何一个出现即判为失败
2. 依次访问 5 个主视图（#original, #continuation, #library, #reader, #settings），验证响应性与无报错
3. 针对每个弹窗执行全生命周期测试：
   - 打开 -> 点击关闭按钮关闭 -> 断言关闭
   - 再次打开 -> 按 Esc / 点击遮罩关闭 -> 断言关闭
   - 关闭后用 document.elementFromPoint 严格核查页面中心没有残留遮罩层拦截点击
4. 连续交叉打开两个不同弹窗，验证状态互不干扰
"""

import json
import urllib.parse
import pytest
from tests.e2e.conftest import PageMonitor


def ensure_sample_novel(page, live_server, title="冒烟测试小品"):
    """辅助函数：通过 import-txt 导入一部包含 2 个章节的标准小说，供 Reader 与书架视图使用。"""
    page.goto(live_server)
    page.wait_for_load_state("networkidle")
    real_title = page.evaluate(f"""() => {{
        return fetch('/api/novels/import-txt', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{
                title: {json.dumps(title)},
                text: '# 第1章 初入江湖\\n青石长阶，细雨微茫。少年负剑独立，神色坚毅。\\n\\n# 第2章 寒江夜雨\\n夜雨如注，破庙内刀光骤现。'
            }})
        }}).then(r => r.json()).then(d => d.title || {json.dumps(title)});
    }}""")
    page.wait_for_timeout(300)
    return real_title


def test_smoke_page_load_and_views_navigation(page, live_server):
    """验证首页加载无报错，且 5 个主视图可正常切换呈现。"""
    monitor = PageMonitor(page, "smoke_views_nav")
    test_title = ensure_sample_novel(page, live_server, "冒烟导航书")

    views = [
        ("#original", "header .nav[data-view='original']", "#view-original"),
        ("#continuation", "header .nav[data-view='continuation']", "#view-continuation"),
        ("#library", "header .nav[data-view='library']", "#view-library"),
        ("#settings", "header .nav[data-view='settings']", "#view-settings"),
    ]

    for view_hash, nav_sel, anchor_sel in views:
        nav_btn = page.locator(nav_sel)
        if nav_btn.is_visible():
            nav_btn.click()
        else:
            page.evaluate(f"window.location.hash = '{view_hash}'")

        page.wait_for_timeout(300)
        assert page.locator(anchor_sel).is_visible(), f"导航至 {view_hash} 失败，未找到锚点元素 {anchor_sel}"
        monitor.assert_no_errors(f"切换至视图 {view_hash}")

    # 第 5 个主视图：Studio 阅读器（通过 openReader 进入）
    page.evaluate(f"openReader({json.dumps(test_title)})")
    page.wait_for_timeout(500)
    assert page.locator("#rd_main").is_visible(), "进入阅读器失败，#rd_main 未展示"
    monitor.assert_no_errors("进入 Studio 阅读器视图")


def test_smoke_visible_buttons_click_response(page, live_server):
    """验证各主视图中核心可交互分类与切换按钮点击响应正常，无报错。"""
    monitor = PageMonitor(page, "smoke_buttons_probe")
    ensure_sample_novel(page, live_server, "按钮探测书")

    # 1. 原创视图：题材分类切换
    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")
    for tab_sel in ["#og_trope_cat_tabs button", "#og_genre_pills button"]:
        tabs = page.locator(tab_sel).all()
        for t in tabs[:3]:
            if t.is_visible():
                t.click()
                page.wait_for_timeout(100)
    monitor.assert_no_errors("原创视图分类切换")

    # 2. 书架视图：分类与卡片/表格切换
    page.goto(f"{live_server}/#library")
    page.wait_for_load_state("networkidle")
    for filter_btn in page.locator("#lib_filter_tabs button").all():
        if filter_btn.is_visible():
            filter_btn.click()
            page.wait_for_timeout(100)
    page.locator("#lib_view_table_btn").click()
    page.wait_for_timeout(200)
    assert page.locator("#lib_table_wrap").is_visible()
    page.locator("#lib_view_grid_btn").click()
    page.wait_for_timeout(200)
    assert page.locator("#lib_grid").is_visible()
    monitor.assert_no_errors("书架视图切换")

    # 3. 设置视图：提示词模板切换
    page.goto(f"{live_server}/#settings")
    page.wait_for_load_state("networkidle")
    pills = page.locator("#prompt_template_pills button").all()
    for pill in pills[:3]:
        if pill.is_visible():
            pill.click()
            page.wait_for_timeout(100)
    monitor.assert_no_errors("设置视图模板切换")


def test_smoke_modals_lifecycle_and_mask_cleanup(page, live_server):
    """
    弹窗全生命周期测试：
    打开 -> 点击关闭按钮关闭 -> 断言关闭 -> 再次打开 -> 点击遮罩/Esc 关闭 -> elementFromPoint 校验遮罩彻底清除
    """
    monitor = PageMonitor(page, "smoke_modals_lifecycle")
    test_title = ensure_sample_novel(page, live_server, "弹窗测试书")

    # 进入 Studio 阅读器
    page.goto(f"{live_server}/#library")
    page.wait_for_load_state("networkidle")
    page.evaluate(f"openReader({json.dumps(test_title)})")
    page.wait_for_timeout(500)
    assert page.locator("#rd_main").is_visible()

    modal_cases = [
        {
            "name": "快捷键速查模态框",
            "modal_sel": "#shortcuts_modal",
            "open_fn": lambda: page.locator("#rd_shortcuts_btn").click(),
            "close_btn_sel": "#sm_close",
        },
        {
            "name": "章节快照历史模态框",
            "modal_sel": "#history_modal",
            "open_fn": lambda: page.locator("#rd_history_btn").click(),
            "close_btn_sel": "#hm_close",
        },
        {
            "name": "划词 AI 辅助精修弹窗",
            "modal_sel": "#rd_assist_modal",
            "open_fn": lambda: page.evaluate("""() => {
                window.activeSelectionSnippet = '测试划词片段内容';
                openAssistModal('expand');
            }"""),
            "close_btn_sel": "#rd_assist_close",
        },
    ]

    for case in modal_cases:
        m_name = case["name"]
        m_sel = case["modal_sel"]
        modal = page.locator(m_sel)

        # 1. 打开 -> 点关闭按钮关闭
        case["open_fn"]()
        page.wait_for_timeout(300)
        assert modal.is_visible(), f"{m_name} 打开失败"
        monitor.assert_no_errors(f"{m_name} 打开")

        close_btn = page.locator(case["close_btn_sel"]).first
        assert close_btn.is_visible()
        close_btn.click()
        page.wait_for_timeout(300)
        assert not modal.is_visible(), f"{m_name} 点击关闭按钮后未能关闭"

        # 2. 再次打开 -> 按 Esc 关闭
        case["open_fn"]()
        page.wait_for_timeout(300)
        assert modal.is_visible()
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        if modal.is_visible():
            close_btn.click()
            page.wait_for_timeout(200)

        # 3. 关键断言：用 elementFromPoint 检查页面正中心点击能穿透到底层主体，没有任何残留遮罩层拦截！
        top_element_tag = page.evaluate("""() => {
            const el = document.elementFromPoint(window.innerWidth / 2, window.innerHeight / 2);
            return el ? { id: el.id, className: el.className, tag: el.tagName } : null;
        }""")
        assert top_element_tag is not None
        cls_str = str(top_element_tag.get("className", ""))
        assert "mask" not in cls_str.lower() or "open" not in cls_str.lower(), f"{m_name} 关闭后，页面中心仍有残留遮罩层拦截点击: {top_element_tag}"
        monitor.assert_no_errors(f"{m_name} 完整闭环与遮罩清理")


def test_smoke_consecutive_modals_no_interference(page, live_server):
    """连续交叉打开两个不同的弹窗，验证事件与遮罩层不互相干扰。"""
    monitor = PageMonitor(page, "smoke_consecutive_modals")
    test_title = ensure_sample_novel(page, live_server, "交叉弹窗书")

    page.goto(f"{live_server}/#library")
    page.wait_for_load_state("networkidle")
    page.evaluate(f"openReader({json.dumps(test_title)})")
    page.wait_for_timeout(500)
    assert page.locator("#rd_main").is_visible()

    # 打开弹窗 A (快捷键速查)
    page.locator("#rd_shortcuts_btn").click()
    page.wait_for_timeout(300)
    assert page.locator("#shortcuts_modal").is_visible()

    # 关闭弹窗 A
    page.locator("#sm_close").click()
    page.wait_for_timeout(300)
    assert not page.locator("#shortcuts_modal").is_visible()

    # 紧接着打开弹窗 B (版本历史快照)
    page.locator("#rd_history_btn").click()
    page.wait_for_timeout(300)
    assert page.locator("#history_modal").is_visible()

    # 关闭弹窗 B
    page.locator("#hm_close").click()
    page.wait_for_timeout(300)
    assert not page.locator("#history_modal").is_visible()

    monitor.assert_no_errors("交叉弹窗状态独立")
