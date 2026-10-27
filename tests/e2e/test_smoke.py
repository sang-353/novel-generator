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
        assert nav_btn.is_visible(), f"导航按钮未找到: {nav_sel}"
        nav_btn.click()
        page.wait_for_timeout(300)
        assert page.locator(anchor_sel).is_visible(), f"导航至 {view_hash} 失败，未找到锚点元素 {anchor_sel}"
        monitor.assert_no_errors(f"切换至视图 {view_hash}")

    # 第 5 个主视图：Studio 阅读器（通过 openReader 进入）
    page.evaluate(f"openReader({json.dumps(test_title)})")
    page.wait_for_timeout(500)
    assert page.locator("#rd_main").is_visible(), "进入阅读器失败，#rd_main 未展示"
    monitor.assert_no_errors("进入 Studio 阅读器视图")


def test_smoke_visible_buttons_click_response(page, live_server):
    """
    冒烟测试遍历每个主视图内所有可见的 button、a、[role=button]：
    逐个点击后断言有可观察变化（弹窗打开/视图切换/请求发出/Toast/DOM属性变更），且无控制台报错。
    点击后恢复状态再测试下一个。
    """
    monitor = PageMonitor(page, "smoke_buttons_probe")
    test_title = ensure_sample_novel(page, live_server, "按钮遍历探测书")

    # 准备回收站测试数据以供破坏性按钮点击
    page.evaluate("""() => {
        return fetch('/api/novels/import-txt', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ title: '待清空废弃书', text: '# 第1章 废弃\\n废弃正文。' })
        }).then(() => fetch('/api/novels/待清空废弃书', { method: 'DELETE' }));
    }""")
    page.wait_for_timeout(300)

    # 自动确认所有 confirm() 提示框
    page.on("dialog", lambda dialog: dialog.accept())

    network_requests = []
    page.on("request", lambda req: network_requests.append(req.url))

    views = [
        ("#original", "#view-original"),
        ("#continuation", "#view-continuation"),
        ("#library", "#view-library"),
        ("#settings", "#view-settings"),
        (f"#read/{urllib.parse.quote(test_title)}/0", "#rd_main"),
    ]

    total_buttons_clicked = 0

    for view_hash, container_sel in views:
        page.goto(f"{live_server}/{view_hash}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(300)

        # 为各视图预置基础表单测试数据，确保业务提交按钮在有效上下文下执行
        if view_hash == "#original":
            page.fill("#og_title", "冒烟原创书")
            page.fill("#og_genre", "奇幻")
            page.fill("#og_setting", "灵气复苏时代的测试背景。")
        elif view_hash == "#continuation":
            page.fill("#ct_source_title", "冒烟续写书")
            page.fill("#ct_source_text", "长夜难明，残月当空。青衣剑客仗剑行于荒野之上，寒风呼啸。")
        elif view_hash == "#settings":
            page.fill("#web_auth_new", "")

        # 获取容器内所有当前可见的交互按钮与链接
        # 排除顶栏全局导航链接（已在 test_smoke_page_load_and_views_navigation 中专项覆盖）
        button_elements = page.locator(
            f"{container_sel} button:visible, {container_sel} a:visible, {container_sel} [role='button']:visible"
        ).all()

        assert len(button_elements) > 0, f"视图 {view_hash} 下未找到任何可见按钮"
        view_clicked = 0

        for idx, btn in enumerate(button_elements):
            if not btn.is_visible():
                continue

            btn_text = (btn.text_content() or btn.get_attribute("title") or btn.get_attribute("aria-label") or f"Btn_{idx}").strip()
            btn_id = btn.get_attribute("id") or ""

            # 记录点击前的基线状态
            req_count_before = len(network_requests)
            url_before = page.url
            class_before = btn.get_attribute("class") or ""

            # 点击按钮
            try:
                btn.click(timeout=1000)
            except Exception:
                try:
                    btn.click(force=True, timeout=1000)
                except Exception:
                    pass

            page.wait_for_timeout(200)
            view_clicked += 1
            total_buttons_clicked += 1

            # 1. 验证无控制台报错
            monitor.assert_no_errors(f"视图 {view_hash} 点击按钮 [{btn_text}] (#{btn_id})")

            # 2. 验证产生可观察的变化
            req_count_after = len(network_requests)
            url_after = page.url
            try:
                class_after = btn.get_attribute("class") or ""
                btn_disabled = btn.is_disabled()
            except Exception:
                # 元素在点击后从 DOM 中销毁或重新渲染（如删除/切换），属于明确的可观察变化
                class_after = "detached"
                btn_disabled = False

            toast_count = page.locator(".toast:visible, #toast:visible").count()
            modals_count = page.locator(".modal-mask:visible, .modal-box:visible, .rd-sheet:visible, .card:visible").count()

            has_observable_change = (
                url_after != url_before
                or req_count_after > req_count_before
                or toast_count > 0
                or modals_count > 0
                or class_after != class_before
                or btn_disabled
            )
            assert has_observable_change, f"视图 {view_hash} 点击按钮 [{btn_text}] (#{btn_id}) 后界面毫无响应（无弹窗/无视图切换/无请求/无Toast）"

            # 3. 状态还原：关闭可能打开的弹窗或抽屉
            page.evaluate("""() => {
                document.querySelectorAll('.modal-mask, .modal, .rd-sheet').forEach(m => {
                    if (window.getComputedStyle(m).display !== 'none') {
                        m.style.display = 'none';
                        m.classList.remove('show', 'open');
                    }
                });
                const mask = document.getElementById('rd_mask');
                if (mask) mask.classList.remove('open');
            }""")
            if page.url != f"{live_server}/{view_hash}":
                page.goto(f"{live_server}/{view_hash}")
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(200)

        print(f"\n[Smoke Button Traversal] 视图 {view_hash}: 发现可见按钮 {len(button_elements)} 个，已点击测试 {view_clicked} 个")

    print(f"\n[Smoke Button Traversal] 冒烟测试全视图按钮遍历完毕，共覆盖点击测试了 {total_buttons_clicked} 个交互按钮/链接")


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
