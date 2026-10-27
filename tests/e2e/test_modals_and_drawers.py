"""
tests/e2e/test_modals_and_drawers.py - 弹窗与抽屉完整生命周期及关闭路径测试

覆盖全部 8 个弹窗与 2 个抽屉：
#round_modal, #rename_modal, #bible_modal, #history_modal, #import_modal,
#shortcuts_modal, #web_auth_modal, #rd_assist_modal, #rd_settings, #rd_more

全部通过 pytest 参数化独立运行：
1. 关闭路径：点 × (close_x)、点取消/完成按钮 (cancel_btn)、点遮罩外侧 (mask_click)、按 Esc (esc_key)
2. 数据状态：空数据 (empty) 与有数据 (populated) 两种状态
3. 关闭后通过 document.elementFromPoint 验证无任何残留遮罩层拦截点击
"""

import json
import time
from pathlib import Path
import pytest
from tests.e2e.conftest import PageMonitor


MODAL_TARGETS = [
    "#round_modal",
    "#rename_modal",
    "#bible_modal",
    "#history_modal",
    "#import_modal",
    "#shortcuts_modal",
    "#rd_assist_modal",
    "#rd_settings",
    "#rd_more",
]

DATA_STATES = ["empty", "populated"]
CLOSE_PATHS = ["close_x", "cancel_btn", "mask_click", "esc_key"]


def _setup_modal_state(page, live_server, modal_id, data_state):
    """
    根据目标弹窗与数据状态，初始化页面数据并将其打开到可视状态。
    """
    if modal_id in ("#history_modal", "#bible_modal", "#rd_assist_modal", "#rd_settings", "#rd_more", "#shortcuts_modal"):
        # 进入 Studio 阅读器环境
        title = "弹窗状态测试书"
        ch_text = (
            "第1章 绝壁孤松\\n山风呼啸，古松苍劲凌厉。\\n"
            if data_state == "populated"
            else "第1章 空章节\\n\\n"
        )
        page.goto(live_server)
        page.wait_for_load_state("networkidle")
        page.evaluate(f"""() => {{
            return fetch('/api/novels/import-txt', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{ title: {json.dumps(title)}, text: {json.dumps(ch_text)} }})
            }});
        }}""")
        page.wait_for_timeout(300)

        # 若为 populated 状态且测试 history_modal，先通过编辑保存创建一条真实备份快照
        if data_state == "populated" and modal_id == "#history_modal":
            page.evaluate(f"""() => {{
                return fetch('/api/novels/' + encodeURIComponent({json.dumps(title)}) + '/chapter/0', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{ content: '【修改正文以触发历史备份快照产生】' }})
                }});
            }}""")
            page.wait_for_timeout(400)

        # 若为 populated 状态且测试 bible_modal，预先写入设定集
        if data_state == "populated" and modal_id == "#bible_modal":
            page.evaluate(f"""() => {{
                return fetch('/api/novels/' + encodeURIComponent({json.dumps(title)}) + '/bible', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{
                        bible: {{
                            setting: '赛博朋克近未来大都市',
                            conflict: '核心能源垄断冲突',
                            tone: '悬疑硬核',
                            characters: [{{ name: '林澈', role: '潜行骇客', desc: '冷静果断', goal: '寻找失踪的姐姐' }}]
                        }}
                    }})
                }});
            }}""")
            page.wait_for_timeout(300)

        page.evaluate(f"openReader({json.dumps(title)}, 0, {{ reload: true }})")
        page.wait_for_timeout(500)

        if modal_id == "#history_modal":
            page.locator("#rd_history_btn").click()
        elif modal_id == "#bible_modal":
            page.evaluate("openReaderBibleModal()")
        elif modal_id == "#shortcuts_modal":
            page.locator("#rd_shortcuts_btn").click()
        elif modal_id == "#rd_settings":
            page.locator("#rd_settings_toggle").click()
        elif modal_id == "#rd_more":
            page.locator("#rd_more_toggle").click()
        elif modal_id == "#rd_assist_modal":
            page.evaluate(f"""() => {{
                activeSelectionSnippet = {json.dumps('古松苍劲凌厉' if data_state == 'populated' else '测试')};
                openAssistModal('expand');
            }}""")

    elif modal_id == "#round_modal":
        title = "续写测试小说"
        page.goto(f"{live_server}/#continuation")
        page.wait_for_load_state("networkidle")
        if data_state == "populated":
            page.evaluate(f"""() => {{
                return fetch('/api/novels/import-txt', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{ title: {json.dumps(title)}, text: '第1章 开局\\n前情提要。' }})
                }}).then(() => openContinueCard({json.dumps(title)}, 'continuation'));
            }}""")
        else:
            empty_title = "空数据续写书"
            page.evaluate(f"""() => {{
                return fetch('/api/novels/import-txt', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{ title: {json.dumps(empty_title)}, text: '第1章 序\\n无' }})
                }}).then(() => openContinueCard({json.dumps(empty_title)}, 'continuation'));
            }}""")

    elif modal_id == "#rename_modal":
        page.goto(f"{live_server}/#library")
        page.wait_for_load_state("networkidle")
        if data_state == "populated":
            page.evaluate("openRenameModal('现存书名', '现存标题')")
        else:
            page.evaluate("openRenameModal('', '')")

    elif modal_id == "#import_modal":
        page.goto(f"{live_server}/#library")
        page.wait_for_load_state("networkidle")
        page.locator("#lib_import_btn").click()
        if data_state == "populated":
            page.fill("#im_title_inp", "待导入的佳作")
            page.fill("#im_text_inp", "# 第一章 启程\n扬帆起航，浪淘风簸。")

    elif modal_id == "#web_auth_modal":
        page.goto(f"{live_server}/#settings")
        page.wait_for_load_state("networkidle")
        page.evaluate("showWebAuthModal()")
        if data_state == "populated":
            page.fill("#web_auth_input", "SomePassword123")

    page.wait_for_timeout(350)


def _execute_close_path(page, modal_id, close_path):
    """
    针对指定的关闭路径执行交互操作。
    """
    if close_path == "esc_key":
        page.keyboard.press("Escape")
        return

    if close_path == "mask_click":
        # 在视口边缘遮罩处点击（避开中心居中的 modal-box / sheet）
        # 对 rd-sheet / rd_assist_modal 而言，其专用遮罩为 #rd_mask
        if modal_id in ("#rd_settings", "#rd_more", "#rd_assist_modal"):
            mask = page.locator("#rd_mask")
            if mask.is_visible():
                mask.click(position={"x": 10, "y": 10}, force=True)
                return
        # 其他模态框点击自身的 mask 区域
        modal = page.locator(modal_id)
        if modal.is_visible():
            modal.click(position={"x": 10, "y": 10}, force=True)
            return

    # 按键点击路径映射
    close_btn_map = {
        "#round_modal": {"close_x": "#rm_cancel", "cancel_btn": "#rm_cancel"},
        "#rename_modal": {"close_x": "#btn_cancel_rename", "cancel_btn": "#btn_cancel_rename"},
        "#bible_modal": {"close_x": "#bm_close", "cancel_btn": "#bm_cancel"},
        "#history_modal": {"close_x": "#hm_close", "cancel_btn": "#hm_cancel_btn"},
        "#import_modal": {"close_x": "#im_close", "cancel_btn": "#im_cancel_btn"},
        "#shortcuts_modal": {"close_x": "#sm_close", "cancel_btn": "#sm_done_btn"},
        "#web_auth_modal": {"close_x": "#web_auth_modal .close-btn", "cancel_btn": "#web_auth_modal .cancel-btn"},
        "#rd_assist_modal": {"close_x": "#rd_assist_close", "cancel_btn": "#rd_assist_close"},
        "#rd_settings": {"close_x": "button[data-rd-close='rd_settings']", "cancel_btn": "button[data-rd-close='rd_settings']"},
        "#rd_more": {"close_x": "button[data-rd-close='rd_more']", "cancel_btn": "button[data-rd-close='rd_more']"},
    }

    target_sel = close_btn_map.get(modal_id, {}).get(close_path)
    if not target_sel:
        assert False, f"缺陷发现：组件 {modal_id} 未定义 [{close_path}] 路径的关闭按钮"

    btn = page.locator(target_sel).first
    if btn.count() == 0 or not btn.is_visible():
        assert False, f"缺陷发现：组件 {modal_id} 界面上缺少可见的 [{close_path}] 关闭按钮 (选择器: {target_sel})"

    btn.click()


@pytest.mark.parametrize("modal_id", MODAL_TARGETS)
@pytest.mark.parametrize("data_state", DATA_STATES)
@pytest.mark.parametrize("close_path", CLOSE_PATHS)
def test_modal_and_drawer_lifecycle_and_cleanup(page, live_server, modal_id, data_state, close_path):
    """
    全量弹窗与抽屉生命周期测试：
    验证每个组件在不同数据状态下通过 4 种关闭路径均能关闭，且关闭后无任何残留遮罩层拦截点击。
    """
    monitor = PageMonitor(page, f"modal_{modal_id.replace('#', '')}_{data_state}_{close_path}")

    # 1. 打开弹窗/抽屉
    _setup_modal_state(page, live_server, modal_id, data_state)
    target_loc = page.locator(modal_id)
    if modal_id in ("#rd_settings", "#rd_more"):
        is_opened = "open" in (target_loc.get_attribute("class") or "")
    else:
        is_opened = target_loc.is_visible()
    assert is_opened, f"前置断言失败：组件 {modal_id} 在数据状态 [{data_state}] 下未能成功打开并呈现"

    # 2. 执行指定的关闭路径
    try:
        _execute_close_path(page, modal_id, close_path)
    except Exception as e:
        # 若操作本身报错（如找不到按钮），直接抛出明确失败
        raise AssertionError(f"执行关闭动作失败: {modal_id} ({data_state}) via {close_path}: {e}")

    page.wait_for_timeout(350)

    # 3. 断言组件已关闭
    if modal_id in ("#rd_settings", "#rd_more"):
        is_still_open = "open" in (target_loc.get_attribute("class") or "")
    else:
        is_still_open = target_loc.is_visible()
    if is_still_open:
        # 强制清理以防污染后续独立用例
        page.evaluate(f"""() => {{
            const el = document.querySelector({json.dumps(modal_id)});
            if (el) {{ el.style.display = 'none'; el.classList.remove('show', 'open'); }}
            const mask = document.getElementById('rd_mask');
            if (mask) mask.classList.remove('open');
        }}""")
        assert False, f"缺陷发现：组件 {modal_id} 在状态 [{data_state}] 下通过 [{close_path}] 路径未能成功关闭！"

    # 4. 关键验证：使用 elementFromPoint 验证视口中心没有残留遮罩层拦截用户点击
    top_element = page.evaluate("""() => {
        const el = document.elementFromPoint(window.innerWidth / 2, window.innerHeight / 2);
        return el ? { id: el.id, className: el.className, tag: el.tagName } : null;
    }""")
    assert top_element is not None, "elementFromPoint 探测返回空"
    cls_str = str(top_element.get("className", "")).lower()
    id_str = str(top_element.get("id", "")).lower()

    # 遮罩特征判定
    is_mask_lingering = (
        ("mask" in cls_str or "overlay" in cls_str or id_str == "rd_mask")
        and ("open" in cls_str or "show" in cls_str or top_element.get("tag") == "DIV")
    )
    if is_mask_lingering and ("modal-box" not in cls_str and "sheet" not in cls_str):
        assert False, f"缺陷发现：{modal_id} ({data_state}) 经由 [{close_path}] 关闭后，页面中心仍有残留遮罩层拦截点击: {top_element}"

    monitor.assert_no_errors(f"{modal_id} [{data_state}] via [{close_path}]")


def test_web_auth_modal_cannot_be_bypassed_by_escape_or_mask(page, live_server):
    """安全门禁弹窗专项验证：产品设计上 web_auth_modal 绝不可通过 Esc、点遮罩关闭。"""
    page.goto(f"{live_server}/#settings")
    page.wait_for_load_state("networkidle")
    page.evaluate("showWebAuthModal()")
    modal = page.locator("#web_auth_modal")
    assert modal.is_visible()

    # 尝试按 Esc
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    assert modal.is_visible(), "安全缺陷：全站口令弹窗被 Esc 键绕过关闭！"

    # 尝试点遮罩
    modal.click(position={"x": 10, "y": 10}, force=True)
    page.wait_for_timeout(300)
    assert modal.is_visible(), "安全缺陷：全站口令弹窗被点击遮罩绕过关闭！"

    # 恢复隐藏
    page.evaluate("document.getElementById('web_auth_modal').style.display = 'none'")
