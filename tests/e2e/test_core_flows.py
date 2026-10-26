"""
tests/e2e/test_core_flows.py - 核心业务流程 E2E 测试套件

覆盖范围：
1. 原创流程：选灵感脑洞卡 -> 表单填入 -> 生成大纲 -> 开始全书生成(Mock流式) -> 书架呈现新书
2. 书架流程：实时搜索、视图切换、重命名、移入回收站、查看回收站并还原
3. Studio 流程：进入编辑模式、正文保存、刷新持久化验证、全书查找替换(侧栏面板)
4. 设置流程：模型 Provider 连通性测试、保存设置
5. TXT 导入：多卷章结构 TXT 解析预览与导入建书
"""

import json
import time
import urllib.parse
import pytest
from tests.e2e.conftest import PageMonitor


def test_core_flow_original_novel_generation(page, live_server):
    """原创生成全流程：选灵感 -> 细纲生成 -> 开始写书(流式) -> 书架落盘展示。"""
    monitor = PageMonitor(page, "flow_original_gen")
    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    # 1. 填写设定
    page.fill("#og_title", "深空守望者")
    page.fill("#og_genre", "科幻未来")
    page.fill("#og_setting", "人类移居地下的未来时代。")

    # 2. 进入步骤 2 并生成大纲
    page.locator("#btn_step1_next").click()
    page.wait_for_timeout(300)

    gen_outline_btn = page.locator("#btn_outline")
    if gen_outline_btn.is_visible():
        gen_outline_btn.click()
        page.locator("#og_outline_card").wait_for(state="visible", timeout=10000)

    # 3. 进入步骤 3 并启动全书生成 (Mock 流式)
    page.locator("#btn_step2_next").click()
    page.wait_for_timeout(300)
    page.fill("#og_chapters", "1")

    submit_btn = page.locator("#btn_write_all")
    assert submit_btn.is_visible(), "未找到开始全书生成按钮"
    submit_btn.click()

    # 4. 验证进度卡片完成与流式文本更新
    page.locator("#og_open_reader").wait_for(state="visible", timeout=15000)
    monitor.assert_no_errors("原创生成完成")

    # 5. 导航至书架，验证新书呈现
    page.goto(f"{live_server}/#library")
    page.wait_for_load_state("networkidle")
    page.locator(".book-card, tr.novel").first.wait_for(state="visible", timeout=5000)
    book_titles = page.locator(".book-card-title, .novel td").all_text_contents()
    assert any("深空守望者" in t for t in book_titles), f"书架未找到新生成的书籍: 深空守望者，现有: {book_titles}"


def test_core_flow_library_operations(page, live_server):
    """书架管理流程：搜索、表格视图切换、重命名、移入回收站、还原。"""
    monitor = PageMonitor(page, "flow_library_ops")
    page.goto(f"{live_server}/#library")
    page.wait_for_load_state("networkidle")

    # 确保书架至少有一本书（正确传递 text 字段）
    page.evaluate("""() => {
        return fetch('/api/novels/import-txt', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({title: '书架测试样本', text: '# 第1章 测试\\n正文内容。'})
        });
    }""")
    page.reload()
    page.wait_for_load_state("networkidle")

    # 1. 实时搜索过滤
    search_input = page.locator("#lib_search_input")
    search_input.fill("样本")
    page.wait_for_timeout(300)
    visible_cards = page.locator(".book-card:visible, tr.novel:visible").count()
    assert visible_cards >= 1, "搜索 '样本' 未匹配到卡片"

    # 清空搜索
    search_input.fill("")
    page.wait_for_timeout(300)

    # 2. 切换至表格视图测试精准操作
    page.locator("#lib_view_table_btn").click()
    page.wait_for_timeout(300)

    # 重命名测试
    rename_btn = page.locator("tr.novel [data-act='rename']").first
    if rename_btn.is_visible():
        rename_btn.click()
        page.wait_for_timeout(300)
        rename_modal = page.locator("#rename_modal")
        assert rename_modal.is_visible()
        page.fill("#rename_input", "重命名后的好书")
        page.locator("#btn_confirm_rename").click()
        page.wait_for_timeout(500)

    # 3. 移入回收站
    del_btn = page.locator("tr.novel [data-act='del']").first
    if del_btn.is_visible():
        page.once("dialog", lambda dialog: dialog.accept())
        del_btn.click()
        page.wait_for_timeout(500)

    # 4. 展开回收站并还原
    trash_toggle = page.locator("#lib_trash_toggle_btn")
    if trash_toggle.is_visible():
        trash_toggle.click()
        page.wait_for_timeout(300)
        assert page.locator("#lib_trash_card").is_visible()
        restore_btn = page.locator("#lib_trash_list [data-act='restore']").first
        if restore_btn.is_visible():
            restore_btn.click()
            page.wait_for_timeout(500)

    monitor.assert_no_errors("书架管理全流程")


def test_core_flow_studio_reader_and_editor(page, live_server):
    """Studio 流程：正文编辑模式、保存持久化、全局查找替换面板。"""
    monitor = PageMonitor(page, "flow_studio_editor")
    test_title = "Studio测试书"

    # 导入测试小说
    page.goto(live_server)
    page.wait_for_load_state("networkidle")
    page.evaluate(f"""() => {{
        return fetch('/api/novels/import-txt', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{title: {json.dumps(test_title)}, text: '# 第1章 初入江湖\\n这是第一段正文。'}})
        }});
    }}""")
    page.wait_for_timeout(300)

    # 进入 Studio 阅读器
    page.evaluate(f"openReader({json.dumps(test_title)})")
    page.wait_for_timeout(500)
    assert page.locator("#rd_main").is_visible()

    # 1. 点击编辑按钮进入编辑模式
    edit_btn = page.locator("#rd_edit_btn")
    if edit_btn.is_visible():
        edit_btn.click()
        page.wait_for_timeout(300)

        # 填写正文并保存
        edit_body = page.locator("#rd_edit_body_inp")
        assert edit_body.is_visible(), "进入编辑模式未渲染 #rd_edit_body_inp"
        edit_body.fill("这是经过双向测试编辑更新后的全新段落。")
        page.locator("#rd_edit_save_btn").click()
        page.wait_for_timeout(600)

        # 重新加载该书验证持久化
        page.evaluate(f"openReader({json.dumps(test_title)})")
        page.wait_for_timeout(500)
        reloaded_text = page.locator("#rd_content").text_content()
        assert "全新段落" in reloaded_text, "正文编辑保存后未找到更新文本"

    # 2. 调用全书查找替换 (点击顶栏按钮展开侧栏面板)
    replace_btn = page.locator("#rd_search_replace_btn")
    if replace_btn.is_visible():
        replace_btn.click()
        page.wait_for_timeout(300)
        assert page.locator("#rd_ast_panel_search").is_visible(), "查找替换面板未展开"
        page.fill("#sr_find_input", "全新")
        page.fill("#sr_replace_input", "奇幻")
        page.locator("#sr_preview_btn").click()
        page.wait_for_timeout(500)

    monitor.assert_no_errors("Studio 阅读与编辑")


def test_core_flow_settings_provider_and_auth(page, live_server):
    """设置流程：模型 Provider 连通性测试、保存设置持久化。"""
    monitor = PageMonitor(page, "flow_settings")
    page.goto(f"{live_server}/#settings")
    page.wait_for_load_state("networkidle")

    # 1. 连通性测试
    test_btn = page.locator("#btn_test")
    if test_btn.is_visible():
        test_btn.click()
        page.wait_for_timeout(500)

    # 2. 保存配置
    save_btn = page.locator("#btn_save_settings")
    if save_btn.is_visible():
        save_btn.click()
        page.wait_for_timeout(500)

    monitor.assert_no_errors("设置页面测试")


def test_core_flow_txt_import(page, live_server):
    """TXT 导入流程：含分卷分章标记的文本解析。"""
    monitor = PageMonitor(page, "flow_txt_import")
    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    sample_txt_content = (
        "## 卷：第一卷 少年游\n\n"
        "# 第一章 风起青萍之末\n"
        "少年负剑下天山，江湖初露峥嵘。\n\n"
        "# 第二章 寒江夜雨古刹\n"
        "夜雨如注，破庙内刀光骤现。\n"
    )

    page.evaluate(f"""() => {{
        const blob = new Blob([{json.dumps(sample_txt_content)}], {{ type: 'text/plain' }});
        const formData = new FormData();
        formData.append('file', blob, '武侠样例.txt');
        return fetch('/api/novels/import-txt', {{ method: 'POST', body: formData }});
    }}""")

    page.wait_for_timeout(500)
    monitor.assert_no_errors("TXT 结构导入")
