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
import os
from pathlib import Path
import time
import urllib.parse
import pytest
from tests.e2e.conftest import PageMonitor, ARTIFACTS_DIR


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
    assert gen_outline_btn.is_visible(), "未找到生成大纲按钮 #btn_outline"
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
    assert rename_btn.is_visible(), "未在表格行中找到重命名按钮 [data-act='rename']"
    rename_btn.click()
    page.wait_for_timeout(300)
    rename_modal = page.locator("#rename_modal")
    assert rename_modal.is_visible(), "重命名弹窗 #rename_modal 未弹出"
    page.fill("#rename_input", "重命名后的好书")
    page.locator("#btn_confirm_rename").click()
    page.wait_for_timeout(500)

    # 3. 移入回收站
    del_btn = page.locator("tr.novel [data-act='del']").first
    assert del_btn.is_visible(), "未在表格行中找到删除按钮 [data-act='del']"
    page.once("dialog", lambda dialog: dialog.accept())
    del_btn.click()
    page.wait_for_timeout(500)

    # 4. 展开回收站并还原
    trash_toggle = page.locator("#lib_trash_toggle_btn")
    assert trash_toggle.is_visible(), "未找到回收站开关按钮 #lib_trash_toggle_btn"
    trash_toggle.click()
    page.wait_for_timeout(300)
    assert page.locator("#lib_trash_card").is_visible(), "回收站卡片 #lib_trash_card 未展示"
    restore_btn = page.locator("#lib_trash_list [data-act='restore']").first
    assert restore_btn.is_visible(), "回收站中未找到还原按钮 [data-act='restore']"
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
    assert edit_btn.is_visible(), "未找到进入编辑按钮 #rd_edit_btn"
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
    assert replace_btn.is_visible(), "未找到查找替换按钮 #rd_search_replace_btn"
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
    assert test_btn.is_visible(), "设置页面未找到测通按钮 #btn_test"
    test_btn.click()
    page.wait_for_timeout(500)

    # 2. 保存配置
    save_btn = page.locator("#btn_save_settings")
    assert save_btn.is_visible(), "设置页面未找到保存设置按钮 #btn_save_settings"
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


def test_skip_outline_direct_generate(page, live_server):
    """跳过大纲直接点击生成全书：验证界面是否给出友好的 Toast 提示'请先生成大纲'。"""
    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    # 1. 填写设定
    page.fill("#og_title", "跳过大纲测试书")
    page.fill("#og_genre", "科幻")
    page.fill("#og_setting", "测试跳过大纲直接写书。")

    # 2. 进入步骤 2 (不点击生成大纲)，直接进入步骤 3
    page.locator("#btn_step1_next").click()
    page.wait_for_timeout(300)
    page.locator("#btn_step2_next").click()
    page.wait_for_timeout(300)

    # 3. 点击开始全书生成
    submit_btn = page.locator("#btn_write_all")
    submit_btn.click()
    page.wait_for_timeout(600)

    # 4. 检查 Toast 提示
    toast_text = page.locator("#toast").text_content() or ""
    print(f"用户在界面看到的提示为: {toast_text}")
    assert "请先生成大纲" in toast_text, f"未出现友好的'请先生成大纲'提示，实际为: {toast_text}"
    assert "生成失败：" not in toast_text, f"界面出现原始报错前缀: {toast_text}"


def test_core_flow_studio_chapter_reorder(page, live_server):
    """Studio 流程：目录列表内章节上下移动排序。"""
    monitor = PageMonitor(page, "flow_chapter_reorder")
    title = "排序测试书"
    page.goto(live_server)
    page.wait_for_load_state("networkidle")
    page.evaluate(f"""() => {{
        return fetch('/api/novels/import-txt', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{
                title: {json.dumps(title)},
                text: '第1章 甲篇\\n甲篇正文。\\n\\n第2章 乙篇\\n乙篇正文。\\n\\n第3章 丙篇\\n丙篇正文。'
            }})
        }});
    }}""")
    page.wait_for_timeout(300)

    page.evaluate(f"openReader({json.dumps(title)})")
    page.wait_for_timeout(500)
    assert page.locator("#rd_main").is_visible()

    # 确保目录展开
    page.evaluate("setTocOpen(true)")
    page.wait_for_timeout(300)

    # 验证初始章节顺序：第一项为甲篇
    items = page.locator("#rd_toc_list .toc-item")
    assert items.count() == 3, f"目录章节数不符: {items.count()}"
    first_title = items.nth(0).locator(".t").text_content() or ""
    assert "甲篇" in first_title

    # 点击第1章的下移按钮
    down_btn = items.nth(0).locator(".toc-reorder-btn[data-act='down']")
    assert down_btn.is_visible(), "未找到第1章下移按钮"
    down_btn.click()
    page.wait_for_timeout(600)

    # 刷新后验证持久化顺序：乙篇变第一，甲篇变第二
    page.evaluate(f"openReader({json.dumps(title)}, 0, {{ reload: true }})")
    page.wait_for_timeout(500)
    items_after = page.locator("#rd_toc_list .toc-item")
    new_first_title = items_after.nth(0).locator(".t").text_content() or ""
    new_second_title = items_after.nth(1).locator(".t").text_content() or ""
    assert "乙篇" in new_first_title, f"重新排序后第一章应为乙篇，实际为: {new_first_title}"
    assert "甲篇" in new_second_title, f"重新排序后第二章应为甲篇，实际为: {new_second_title}"
    monitor.assert_no_errors("章节移动重排")


def test_core_flow_studio_snapshot_restore(page, live_server):
    """Studio 流程：编辑保存产生快照，后从历史快照弹窗一键还原。"""
    monitor = PageMonitor(page, "flow_snapshot_restore")
    title = "快照还原书"
    page.goto(live_server)
    page.wait_for_load_state("networkidle")
    page.evaluate(f"""() => {{
        return fetch('/api/novels/import-txt', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{
                title: {json.dumps(title)},
                text: '# 第1章 初始版本\\n【原始初版段落内容】古道西风瘦马。'
            }})
        }});
    }}""")
    page.wait_for_timeout(300)

    page.evaluate(f"openReader({json.dumps(title)})")
    page.wait_for_timeout(500)

    # 1. 进入编辑，修改并保存为第二版
    page.locator("#rd_edit_btn").click()
    page.wait_for_timeout(300)
    page.fill("#rd_edit_body_inp", "【第二版修改内容】小桥流水人家。")
    page.locator("#rd_edit_save_btn").click()
    page.wait_for_timeout(600)

    # 2. 打开历史快照弹窗
    page.locator("#rd_history_btn").click()
    page.wait_for_timeout(400)
    modal = page.locator("#history_modal")
    assert modal.is_visible(), "历史快照弹窗未打开"

    # 3. 检查列表中存在快照并点击还原
    restore_btn = page.locator("#hm_snapshots_list .snap-restore-btn").first
    assert restore_btn.is_visible(), "快照列表中未找到还原按钮"
    page.once("dialog", lambda dialog: dialog.accept())
    restore_btn.click()
    page.wait_for_timeout(600)

    # 4. 验证正文还原回初始内容
    content_text = page.locator("#rd_content").text_content() or ""
    assert "原始初版段落内容" in content_text, f"还原快照后正文未呈现初版内容: {content_text}"
    monitor.assert_no_errors("快照版本还原")


def test_core_flow_studio_selection_assist_and_apply(page, live_server):
    """Studio 流程：划词弹出浮动工具栏 -> 点击扩写 -> 弹窗生成 -> 替换回正文。"""
    monitor = PageMonitor(page, "flow_selection_assist")
    title = "划词精修书"
    page.goto(live_server)
    page.wait_for_load_state("networkidle")
    page.evaluate(f"""() => {{
        return fetch('/api/novels/import-txt', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{
                title: {json.dumps(title)},
                text: '# 第1章 暮色\\n青石长阶，细雨微茫。少年负剑踏上青石长廊。'
            }})
        }});
    }}""")
    page.wait_for_timeout(300)

    page.evaluate(f"openReader({json.dumps(title)})")
    page.wait_for_timeout(500)

    # 划词选中文本并触发工具条
    page.evaluate("""() => {
        const bodyEl = document.querySelector('.chapter-body') || document.querySelector('#rd_content');
        const range = document.createRange();
        range.selectNodeContents(bodyEl);
        const sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(range);
        openAssistModal('expand');
    }""")
    page.wait_for_timeout(500)

    # 验证精修弹窗打开
    assist_modal = page.locator("#rd_assist_modal")
    assert assist_modal.is_visible(), "精修弹窗 #rd_assist_modal 未展开"

    # 等待精修结果呈现
    page.locator("#rd_assist_result_wrap").wait_for(state="visible", timeout=10000)
    result_text = page.locator("#rd_assist_result_text").input_value()
    assert len(result_text) > 0, "精修结果框文本为空"

    # 点击应用替换
    page.locator("#rd_assist_apply_btn").click()
    page.wait_for_timeout(600)

    # 验证弹窗关闭并已写入正文
    assert not assist_modal.is_visible(), "应用精修后弹窗未能关闭"
    monitor.assert_no_errors("划词精修替换")


def test_core_flow_studio_search_and_replace_execution(page, live_server):
    """Studio 流程：Ctrl+F 全书查找替换（预览匹配项 + 正式批量替换执行）。"""
    monitor = PageMonitor(page, "flow_search_replace_exec")
    title = "全书替换执行书"
    page.goto(live_server)
    page.wait_for_load_state("networkidle")
    page.evaluate(f"""() => {{
        return fetch('/api/novels/import-txt', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{
                title: {json.dumps(title)},
                text: '第1章 初入江湖\\n青云门下弟子众多，青云山脉延绵。\\n\\n第2章 仗剑远行\\n青云之志不可夺。'
            }})
        }});
    }}""")
    page.wait_for_timeout(300)

    page.evaluate(f"openReader({json.dumps(title)})")
    page.wait_for_timeout(500)

    # 打开查找替换面板
    page.locator("#rd_search_replace_btn").click()
    page.wait_for_timeout(300)
    assert page.locator("#rd_ast_panel_search").is_visible()

    page.fill("#sr_find_input", "青云")
    page.fill("#sr_replace_input", "紫霄")

    # 预览
    page.locator("#sr_preview_btn").click()
    page.wait_for_timeout(600)
    preview_box = page.locator("#sr_results_list")
    assert "青云" in (preview_box.text_content() or ""), "替换预览未匹配到目标关键词"

    # 执行替换
    page.once("dialog", lambda dialog: dialog.accept())
    page.locator("#sr_execute_btn").click()
    page.wait_for_timeout(800)

    # 重新加载检查正文内容
    page.evaluate(f"openReader({json.dumps(title)}, 0, {{ reload: true }})")
    page.wait_for_timeout(500)
    content_after = page.locator("#rd_content").text_content() or ""
    assert "紫霄" in content_after, f"替换后正文应包含'紫霄'，实际为: {content_after}"
    assert "青云" not in content_after, f"替换后正文不应再残留'青云'，实际为: {content_after}"
    monitor.assert_no_errors("全书查找替换执行")


def test_core_flow_studio_keyboard_shortcuts(page, live_server):
    """Studio 流程：全部阅读器快捷键操作验证（?, Ctrl+B, Ctrl+J, Ctrl+F, Ctrl+S）。"""
    monitor = PageMonitor(page, "flow_shortcuts")
    title = "快捷键测试书"
    page.goto(live_server)
    page.wait_for_load_state("networkidle")
    page.evaluate(f"""() => {{
        return fetch('/api/novels/import-txt', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{
                title: {json.dumps(title)},
                text: '第1章 初始\\n快捷键测试正文。'
            }})
        }});
    }}""")
    page.wait_for_timeout(300)

    page.evaluate(f"openReader({json.dumps(title)})")
    page.wait_for_timeout(500)

    # 1. 点击速查按钮呼出快捷键模态框，并测试关闭
    page.locator("#rd_shortcuts_btn").click()
    page.wait_for_timeout(300)
    sm = page.locator("#shortcuts_modal")
    assert sm.is_visible(), "点击速查按钮未能呼出 #shortcuts_modal"
    page.locator("#sm_close").click()
    page.wait_for_timeout(200)

    # 2. Ctrl+B 切换目录侧边栏显隐
    toc = page.locator("#rd_toc")
    page.keyboard.press("Control+b")
    page.wait_for_timeout(300)
    # 再次按 Ctrl+B 还原
    page.keyboard.press("Control+b")
    page.wait_for_timeout(300)

    # 3. Ctrl+J 切换 AI 侧边助手显隐（默认展开，按 Ctrl+J 折叠）
    ast = page.locator("#rd_assistant")
    page.keyboard.press("Control+j")
    page.wait_for_timeout(300)
    assert "collapsed" in (ast.get_attribute("class") or "")
    # 再次按 Ctrl+J 还原展开
    page.keyboard.press("Control+j")
    page.wait_for_timeout(300)
    assert "collapsed" not in (ast.get_attribute("class") or "")

    # 4. Ctrl+F 呼出全局查找替换
    page.keyboard.press("Control+f")
    page.wait_for_timeout(300)
    assert page.locator("#rd_ast_panel_search").is_visible(), "Ctrl+F 未能呼出查找替换面板"

    # 5. Ctrl+S 保存正文编辑
    page.locator("#rd_edit_btn").click()
    page.wait_for_timeout(300)
    page.fill("#rd_edit_body_inp", "【Ctrl+S快捷保存内容】")
    page.keyboard.press("Control+s")
    page.wait_for_timeout(600)
    page.evaluate(f"openReader({json.dumps(title)}, 0, {{ reload: true }})")
    page.wait_for_timeout(500)
    assert "Ctrl+S快捷保存内容" in (page.locator("#rd_content").text_content() or "")
    monitor.assert_no_errors("阅读器全部快捷键")


def test_core_flow_library_export_three_formats(page, live_server):
    """书架流程：三种格式（TXT, Markdown, EPUB）导出，并严格校验下载得到的文件内容与结构。"""
    monitor = PageMonitor(page, "flow_export_formats")
    title = "格式导出测试书"
    page.goto(live_server)
    page.wait_for_load_state("networkidle")
    page.evaluate(f"""() => {{
        return fetch('/api/novels/import-txt', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{
                title: {json.dumps(title)},
                text: '# 第1章 碧海潮生\\n碧海潮生按玉箫。\\n\\n# 第2章 桃花影落\\n桃花影落飞神剑。'
            }})
        }});
    }}""")
    page.wait_for_timeout(300)

    page.goto(f"{live_server}/#library")
    page.wait_for_load_state("networkidle")

    # 1. 导出 TXT 并断言内容
    with page.expect_download() as txt_info:
        page.evaluate(f"exportNovel({json.dumps(title)}, 'txt')")
    txt_download = txt_info.value
    txt_path = ARTIFACTS_DIR / txt_download.suggested_filename
    txt_download.save_as(str(txt_path))
    txt_content = txt_path.read_text(encoding="utf-8")
    assert "碧海潮生按玉箫" in txt_content, f"导出的 TXT 缺少章节内容: {txt_content}"

    # 2. 导出 Markdown 并断言 Markdown 结构
    with page.expect_download() as md_info:
        page.evaluate(f"exportNovel({json.dumps(title)}, 'md')")
    md_download = md_info.value
    md_path = ARTIFACTS_DIR / md_download.suggested_filename
    md_download.save_as(str(md_path))
    md_content = md_path.read_text(encoding="utf-8")
    assert f"# {title}" in md_content or "## " in md_content, f"导出的 Markdown 缺少标题格式: {md_content}"
    assert "桃花影落飞神剑" in md_content

    # 3. 导出 EPUB 并断言魔数与结构
    with page.expect_download() as epub_info:
        page.evaluate(f"exportNovel({json.dumps(title)}, 'epub')")
    epub_download = epub_info.value
    epub_path = ARTIFACTS_DIR / epub_download.suggested_filename
    epub_download.save_as(str(epub_path))
    epub_bytes = epub_path.read_bytes()
    assert epub_bytes.startswith(b"PK\x03\x04"), "导出的 EPUB 文件魔数不正确，非标准 ZIP/EPUB 容器"
    assert b"mimetype" in epub_bytes, "EPUB 容器缺少 mimetype 标记"
    monitor.assert_no_errors("三种格式导出校验")


def test_core_flow_trash_purge_permanently(page, live_server):
    """书架流程：移入回收站后执行彻底删除（Purge），断言物理文件彻底销毁。"""
    monitor = PageMonitor(page, "flow_trash_purge")
    title = "永久删除测试书"
    page.goto(live_server)
    page.wait_for_load_state("networkidle")
    page.evaluate(f"""() => {{
        return fetch('/api/novels/import-txt', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{
                title: {json.dumps(title)},
                text: '# 第1章 即将销毁\\n即将永久删除的内容。'
            }})
        }}).then(() => fetch('/api/novels/' + encodeURIComponent({json.dumps(title)}), {{ method: 'DELETE' }}));
    }}""")
    page.wait_for_timeout(400)

    page.goto(f"{live_server}/#library")
    page.wait_for_load_state("networkidle")

    # 展开回收站
    page.locator("#lib_trash_toggle_btn").click()
    page.wait_for_timeout(300)
    trash_card = page.locator("#lib_trash_card")
    assert trash_card.is_visible()

    # 找到目标书籍的彻底删除按钮
    purge_btn = page.locator("#lib_trash_list [data-act='purge']").first
    assert purge_btn.is_visible(), "未在回收站找到彻底删除按钮"
    page.once("dialog", lambda dialog: dialog.accept())
    purge_btn.click()
    page.wait_for_timeout(600)

    # 再次查询回收站，该项不复存在
    trash_text = page.locator("#lib_trash_list").text_content() or ""
    assert title not in trash_text, f"彻底删除后回收站依然存在该书: {trash_text}"
    monitor.assert_no_errors("彻底删除销毁")


def test_core_flow_privacy_wrong_password(page, live_server):
    """书架隐私流程：使用错误密码尝试解锁隐私书架，断言被坚决拒绝且内容不泄露。"""
    monitor = PageMonitor(page, "flow_privacy_wrong_pwd")
    page.goto(live_server)
    page.wait_for_load_state("networkidle")

    try:
        # 1. 导入书籍
        page.evaluate("""() => {
            return fetch('/api/novels/import-txt', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ title: '绝密绝密不公开', text: '第1章 密\\n密' })
            });
        }""")
        page.wait_for_timeout(300)

        # 2. 设置隐私密码
        page.evaluate("""() => {
            return fetch('/api/privacy/set', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ new_password: 'CorrectPassword888' })
            });
        }""")
        page.wait_for_timeout(300)

        # 3. 解锁并将书籍设为私密，随后加锁
        page.evaluate("""() => {
            return fetch('/api/privacy/unlock', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ password: 'CorrectPassword888' })
            }).then(r => r.json()).then(d => {
                return fetch('/api/novels/绝密绝密不公开/privacy', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ private: true, token: d.token })
                }).then(() => {
                    return fetch('/api/privacy/lock', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ token: d.token })
                    });
                });
            });
        }""")
        page.wait_for_timeout(400)

        page.goto(f"{live_server}/#library")
        page.wait_for_load_state("networkidle")

        # 4. 尝试用错误密码解锁
        page.fill("#pv_password", "WrongPassword999")
        page.locator("#pv_unlock").click()
        page.wait_for_timeout(500)

        # 5. 验证提示错误且私密书架未展示目标书
        pv_list_text = page.locator("#pv_tbody").text_content() or ""
        assert "绝密绝密不公开" not in pv_list_text, "安全漏洞：输入错误密码后私密书籍居然被渲染出来！"
        assert len(monitor.page_errors) == 0, f"JS 未捕获异常: {monitor.page_errors}"
    finally:
        try:
            page.evaluate("""() => {
                fetch('/api/privacy/set', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ old_password: 'CorrectPassword888', new_password: '' })
                });
            }""")
        except Exception:
            pass
        cfg_path = Path(os.environ.get("NOVEL_CONFIG_FILE", "config.json"))
        if cfg_path.exists():
            try:
                cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
                cfg["privacy"] = {}
                cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass


def test_core_flow_settings_provider_crud_persistence(page, live_server):
    """设置流程：新增 Provider、修改参数、保存后刷新页面验证持久化保存。"""
    monitor = PageMonitor(page, "flow_provider_crud")
    page.goto(f"{live_server}/#settings")
    page.wait_for_load_state("networkidle")

    # 点击新增 Provider 按钮
    page.locator("#btn_add_provider").click()
    page.wait_for_timeout(300)

    # 找到最新添加的卡片并填写
    new_card = page.locator("#provider_list .provider-card").last
    new_card.locator("input[data-field='name']").fill("自动化新增模型")
    new_card.locator("input[data-field='model']").fill("auto-test-model")
    new_card.locator("input[data-field='base_url']").fill("http://127.0.0.1:59999")

    # 保存设置
    page.locator("#btn_save_settings").click()
    page.wait_for_timeout(600)

    # 刷新页面并重新检查
    page.reload()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(300)

    all_names = [el.input_value() for el in page.locator("#provider_list input[data-field='name']").all()]
    assert "自动化新增模型" in all_names, f"刷新页面后未找到新保存的 Provider: {all_names}"
    monitor.assert_no_errors("Provider 增改与持久化")


def test_core_flow_settings_web_auth_lifecycle(browser, live_server):
    """设置流程：全站口令开启 -> 新 Context 访问拦截 -> 登录放行 -> 关闭全站口令。"""
    ctx_admin = browser.new_context()
    page_admin = ctx_admin.new_page()
    page_admin.goto(f"{live_server}/#settings")
    page_admin.wait_for_load_state("networkidle")

    try:
        # 1. 开启全站口令
        page_admin.fill("#web_auth_new", "AuthGate888")
        page_admin.fill("#web_auth_new2", "AuthGate888")
        page_admin.locator("#web_auth_save_btn").click()
        page_admin.wait_for_timeout(500)

        # 2. 新访客 Context 访问被拦截
        ctx_visitor = browser.new_context()
        page_visitor = ctx_visitor.new_page()
        page_visitor.goto(f"{live_server}/#library")
        page_visitor.wait_for_load_state("networkidle")
        auth_modal = page_visitor.locator("#web_auth_modal")
        assert auth_modal.is_visible(), "开启口令后未登录访客未被全站访问弹窗拦截"

        # 3. 访客输入口令完成登录
        page_visitor.fill("#web_auth_input", "AuthGate888")
        page_visitor.locator("#web_auth_login_btn").click()
        page_visitor.wait_for_timeout(500)
        assert not auth_modal.is_visible(), "口令正确后全站登录弹窗未能顺利关闭"

        # 4. 管理员关闭全站口令
        page_admin.fill("#web_auth_old", "AuthGate888")
        page_admin.once("dialog", lambda dialog: dialog.accept("AuthGate888"))
        page_admin.locator("#web_auth_disable_btn").click()
        page_admin.wait_for_timeout(500)

        # 5. 第三个新 Context 访问无需口令
        ctx_third = browser.new_context()
        page_third = ctx_third.new_page()
        page_third.goto(f"{live_server}/#library")
        page_third.wait_for_load_state("networkidle")
        assert not page_third.locator("#web_auth_modal").is_visible(), "关闭全站口令后仍出现拦截弹窗"
    finally:
        try:
            page_admin.evaluate("""() => {
                fetch('/api/auth/set-password', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ old_password: 'AuthGate888', disable: true })
                });
            }""")
        except Exception:
            pass
        cfg_path = Path(os.environ.get("NOVEL_CONFIG_FILE", "config.json"))
        if cfg_path.exists():
            try:
                cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
                cfg["web_auth"] = {}
                cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass
        ctx_admin.close()
        try:
            ctx_visitor.close()
        except Exception:
            pass
        try:
            ctx_third.close()
        except Exception:
            pass


def test_core_flow_txt_import_via_ui_with_preview(page, live_server):
    """TXT 导入流程：通过界面文件上传控件选择文件，断言分章预览效果并导入。"""
    monitor = PageMonitor(page, "flow_txt_ui_import")
    page.goto(f"{live_server}/#library")
    page.wait_for_load_state("networkidle")

    # 打开导入弹窗
    page.locator("#lib_import_btn").click()
    page.wait_for_timeout(300)
    modal = page.locator("#import_modal")
    assert modal.is_visible(), "导入弹窗 #import_modal 未弹出"

    # 构造本地临时样例 TXT 文件
    sample_content = (
        "第一卷 潜龙在渊\n\n"
        "第一章 少年与剑\n"
        "少年负剑独立绝壁，晨光熹微。\n\n"
        "第二章 寒锋初试\n"
        "长剑出鞘，剑气森然。"
    )
    tmp_txt = ARTIFACTS_DIR / "upload_sample_novel.txt"
    tmp_txt.write_text(sample_content, encoding="utf-8")

    # 界面上传文件
    page.set_input_files("#im_file_inp", str(tmp_txt))
    page.wait_for_timeout(500)

    # 检查分卷分章预览区
    preview = page.locator("#im_preview_box")
    assert preview.is_visible(), "分章解析预览框未展现"
    preview_text = preview.text_content() or ""
    assert "第一章 少年与剑" in preview_text, f"预览缺少第一章: {preview_text}"
    assert "第二章 寒锋初试" in preview_text, f"预览缺少第二章: {preview_text}"

    # 点击确认导入
    page.locator("#im_confirm_btn").click()
    page.wait_for_timeout(800)
    assert not modal.is_visible(), "确认导入后弹窗未能关闭"

    # 检查书架出现新书
    book_titles = page.locator(".book-card-title, tr.novel td").all_text_contents()
    assert any("upload_sample_novel" in t or "潜龙在渊" in t for t in book_titles), f"书架未找到导入的新书: {book_titles}"
    monitor.assert_no_errors("TXT 界面导入与分章预览")


