# -*- coding: utf-8 -*-
"""
tests/e2e/test_og_steps23_controls.py
比对快照 tests/snapshots/og_steps23_controls.json，断言第 2、3 步及各相关卡片的所有控件：
1. 依然全部存在，ID 与标签名完全一致。
2. 初始可见状态与初始启用状态与基准一致，功能无遗失。
3. 文本中核心文案保留，且无 emoji 残留。
"""

import json
import os
import re
from pathlib import Path
import pytest

SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "snapshots" / "og_steps23_controls.json"

EMOJI_PATTERN = re.compile(r"[\U00010000-\U0010ffff]|[\u2600-\u27bf]")


def clean_text(text: str) -> str:
    """去除 emoji 与多余空白便于核心文案核对"""
    no_emoji = EMOJI_PATTERN.sub("", text)
    return "".join(no_emoji.split())


def test_og_steps23_controls_against_snapshot(page, live_server):
    """断言第 2、3 步所有控件相对于基准快照完整无缺。"""
    assert SNAPSHOT_PATH.exists(), f"未找到基准快照文件: {SNAPSHOT_PATH}"
    snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))

    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    for item in snapshot:
        cid = item["container"]
        eid = item["id"]
        tag = item["tagName"]
        expected_enabled = item["isEnabled"]
        expected_visible = item["isVisible"]
        expected_text = item["visibleText"]

        container = page.locator(f"#{cid}")
        assert container.count() == 1, f"容器 #{cid} 不存在！"

        control = container.locator(f"#{eid}")
        assert control.count() == 1, f"控件 #{eid} 在容器 #{cid} 中丢失！"

        actual_tag = control.evaluate("e => e.tagName.toLowerCase()")
        assert actual_tag == tag, f"控件 #{eid} 标签名变动: 预期 {tag}, 实际 {actual_tag}"

        actual_enabled = control.is_enabled()
        assert actual_enabled == expected_enabled, f"控件 #{eid} 初始启用状态不符: 预期 {expected_enabled}, 实际 {actual_enabled}"

        actual_visible = control.is_visible()
        assert actual_visible == expected_visible, f"控件 #{eid} 初始可见状态不符: 预期 {expected_visible}, 实际 {actual_visible}"

        # 检查核心文案完整性
        if expected_text:
            actual_text = control.evaluate("e => (e.innerText || e.value || e.placeholder || '').trim()")
            clean_expected = clean_text(expected_text)
            clean_actual = clean_text(actual_text)
            assert clean_expected in clean_actual or clean_actual in clean_expected, (
                f"控件 #{eid} 核心文案丢失: 预期包含 '{clean_expected}', 实际为 '{clean_actual}'"
            )


def test_og_steps23_step_transition_and_activation(page, live_server):
    """验证从步骤 1 到步骤 2、3 以及卡片展示时，各步骤控件如期激活显示。"""
    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    # 进入步骤 2
    page.evaluate("window.goToOriginalStep(2)")
    page.wait_for_timeout(200)

    # 步骤 2 控件应全部可见
    step2_ids = ["og_characters", "og_style", "og_perspective", "btn_outline", "btn_step2_prev", "btn_step2_next"]
    for eid in step2_ids:
        assert page.locator(f"#{eid}").is_visible(), f"进入步骤 2 后 #{eid} 应可见"

    # 展示设定集与大纲卡片
    page.evaluate("""() => {
        document.getElementById('og_bible_card').style.display = 'block';
        document.getElementById('og_outline_card').style.display = 'block';
    }""")
    page.wait_for_timeout(200)

    bible_visible_ids = ["btn_toggle_bible_raw", "og_bible_setting", "btn_add_bible_char", "og_bible_conflict", "og_bible_tone"]
    for eid in bible_visible_ids:
        assert page.locator(f"#{eid}").is_visible(), f"展示设定集卡片后 #{eid} 应可见"

    outline_visible_ids = ["og_logline_input", "btn_add_outline_ch", "btn_regenerate"]
    for eid in outline_visible_ids:
        assert page.locator(f"#{eid}").is_visible(), f"展示大纲卡片后 #{eid} 应可见"

    # 进入步骤 3
    page.evaluate("window.goToOriginalStep(3)")
    page.wait_for_timeout(200)

    step3_ids = ["og_provider", "btn_manage_og", "og_chapters", "og_per_words", "og_extra", "btn_step3_prev", "btn_write_all"]
    for eid in step3_ids:
        assert page.locator(f"#{eid}").is_visible(), f"进入步骤 3 后 #{eid} 应可见"


def test_og_zero_emoji_in_view_original(page, live_server):
    """
    从 Unicode 层面扫描 #view-original 内部各步骤及渲染卡片后的所有文本，断言零 emoji。
    """
    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    def assert_zero_emoji_in_view(state_desc: str):
        full_text = page.locator("#view-original").inner_text()
        emojis = EMOJI_PATTERN.findall(full_text)
        assert len(emojis) == 0, f"在 {state_desc} 下 #view-original 中发现 emoji 残留: {emojis}"

    # 1. 步骤 1 状态
    assert_zero_emoji_in_view("步骤 1 (初始态)")

    # 2. 步骤 2 状态并渲染设定集与大纲
    page.evaluate("window.goToOriginalStep(2)")
    page.evaluate("""() => {
        renderBibleEditor({
            setting: '修仙大世界',
            characters: [{ name: '叶天', role: '主角', desc: '天灵根少年', goal: '飞升仙界' }],
            conflict: '正魔大战',
            tone: '热血玄幻'
        });
        renderOutlineEditor({
            logline: '少年修仙逆天改命',
            chapters: [
                { title: '第 1 章 灵根觉醒', points: '家族测灵大典惊现极品天灵根' },
                { title: '第 2 章 初入宗门', points: '拜入太虚门遭外门弟子嫉恨' }
            ]
        });
    }""")
    page.wait_for_timeout(200)
    assert_zero_emoji_in_view("步骤 2 (含设定集与大纲)")

    # 3. 步骤 3 状态并展开进度与流式预览
    page.evaluate("window.goToOriginalStep(3)")
    page.evaluate("""() => {
        const card = document.getElementById('og_progress_card');
        card.style.display = 'block';
        document.getElementById('og_cancel_job').style.display = 'inline-block';
        document.getElementById('og_open_reader').style.display = 'inline-block';
        document.getElementById('og_stream_wrap').style.display = 'block';
        document.getElementById('og_stream_body').textContent = '风雪呼啸，少年踏上修行之路。';
    }""")
    page.wait_for_timeout(200)
    assert_zero_emoji_in_view("步骤 3 (含全书生成与进度打字机)")


def test_og_steps23_touch_targets_and_no_horizontal_scroll(page, live_server):
    """
    验证触控区尺寸（桌面端 >= 32px，移动端 >= 36px）及 375px 下零横向滚动。
    """
    # 1. 桌面端触控区 (1280px)
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    page.evaluate("window.goToOriginalStep(2)")
    page.evaluate("""() => {
        renderBibleEditor({
            setting: '设定',
            characters: [{ name: '角色1', role: '主角' }]
        });
        renderOutlineEditor({
            chapters: [{ title: '第1章', points: '要点' }]
        });
    }""")
    page.wait_for_timeout(200)

    # 步骤 2、3 及相关卡片中所有可见按钮 touch target >= 32px
    step23_containers = ["#og_step_2", "#og_step_3", "#og_bible_card", "#og_outline_card", "#og_progress_card"]
    for c_sel in step23_containers:
        for btn in page.locator(f"{c_sel} button").all():
            if btn.is_visible():
                box = btn.bounding_box()
                if box:
                    assert box["width"] >= 31.5 and box["height"] >= 31.5, f"桌面端按钮触控区不足 32px: {box} (text: {btn.inner_text()})"

    # 2. 移动端 (375px)
    page.set_viewport_size({"width": 375, "height": 667})
    page.wait_for_timeout(200)

    # 验证无横向滚动条
    scroll_w = page.evaluate("document.documentElement.scrollWidth")
    client_w = page.evaluate("document.documentElement.clientWidth")
    assert scroll_w <= client_w + 1, f"375px 移动端存在横向滚动: scrollWidth={scroll_w}, clientWidth={client_w}"

    # 移动端步骤 2、3 及相关卡片内所有可见按钮 touch target >= 36px
    for c_sel in step23_containers:
        for btn in page.locator(f"{c_sel} button").all():
            if btn.is_visible():
                box = btn.bounding_box()
                if box:
                    assert box["width"] >= 35.5 and box["height"] >= 35.5, f"移动端按钮触控区不足 36px: {box} (text: {btn.inner_text()})"


def test_og_steps23_screenshots_capture(page, live_server):
    """
    在 tests/e2e/artifacts/23/ 输出完整的 8 张验收截图（1280px 下 5 张，375px 下 3 张）。
    """
    art_dir = Path(__file__).resolve().parent / "artifacts" / "23"
    art_dir.mkdir(parents=True, exist_ok=True)

    # ---------------- 1280px 桌面端 ----------------
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    # 1. 1280_step2_empty.png (进入第 2 步未生成大纲设定集)
    page.evaluate("window.goToOriginalStep(2)")
    page.fill("#og_characters", "林辰：苍云宗外门弟子，性格隐忍坚毅，身负九阳神脉\n苏清寒：冰魄谷圣女，清冷孤高，追查宗门叛徒")
    page.fill("#og_style", "热血激昂，快节奏玄幻升级流")
    page.wait_for_timeout(200)
    page.screenshot(path=str(art_dir / "1280_step2_empty.png"))

    # 2. 1280_step2_with_bible_and_outline.png (大纲和设定集生成后)
    page.evaluate("""() => {
        renderBibleEditor({
            setting: '苍玄界九州大地，宗门林立，强者飞天遁地。神脉觉醒者可引动天地异象。',
            characters: [
                { name: '林辰', role: '主角', desc: '隐忍果决，悟性超群', goal: '破除封印，重振九阳一脉' },
                { name: '苏清寒', role: '女主角/盟友', desc: '天生极寒之体，剑术通玄', goal: '寻得九阳本源以调和极阴' }
            ],
            conflict: '九阳残脉与幽冥古教的万年宿怨',
            tone: '宏大跌宕，激燃热血'
        });
        renderOutlineEditor({
            logline: '外门弃徒偶得残碑，逆脉修真剑斩诸天',
            chapters: [
                { title: '第 1 章 潜龙困渊', points: '家族测灵受尽冷眼，寒潭绝境偶获残碑' },
                { title: '第 2 章 九阳初醒', points: '打破经脉桎梏，一招败宗门恶霸' },
                { title: '第 3 章 寒潭剑影', points: '初遇冰魄圣女，联手斩杀双头魔蛟' }
            ]
        });
    }""")
    page.wait_for_timeout(200)
    page.screenshot(path=str(art_dir / "1280_step2_with_bible_and_outline.png"))

    # 3. 1280_step3_idle.png (进入第 3 步未开始生成)
    page.evaluate("window.goToOriginalStep(3)")
    page.fill("#og_chapters", "10")
    page.fill("#og_per_words", "1800")
    page.fill("#og_extra", "重点突出主角战斗智谋，避免无脑装逼。")
    page.wait_for_timeout(200)
    page.screenshot(path=str(art_dir / "1280_step3_idle.png"))

    # 4. 1280_step3_generating.png (生成中，有进度条与流式打字机)
    page.evaluate("""() => {
        const card = document.getElementById('og_progress_card');
        card.style.display = 'block';
        document.getElementById('og_live_badge').style.display = 'inline-flex';
        setBar('og_progress_bar', 40);
        document.getElementById('og_progress_text').textContent = '正在创作 第 4 章：幽冥暗刺（4/10）';
        document.getElementById('og_progress_msg').textContent = 'AI 思考中，正结合前文伏笔推演激战细节…';
        document.getElementById('og_cancel_job').style.display = 'inline-block';
        document.getElementById('og_open_reader').style.display = 'none';

        const wrap = document.getElementById('og_stream_wrap');
        wrap.style.display = 'block';
        document.getElementById('og_stream_ch').textContent = '第 4 章：幽冥暗刺';
        document.getElementById('og_stream_words').textContent = '已输出 1,280 字';
        document.getElementById('og_stream_body').textContent =
`剑鸣铮铮，撕裂了古庙内死一般的沉寂。

黑衣刺客的短刃在离林辰心口仅剩三寸之处戛然而止，一层淡金色的烈阳火纹从林辰胸口骤然激荡开来，宛如实质的琉璃神甲，将森然杀意硬生生震散！

“幽冥教的‘无影遁’确实神妙，但你千不该万不该，在踏入此殿时踏碎了地上的落叶。”林辰眼神冰冷如铁，右手并指如剑，赤焰流光在指尖吞吐不定。

殿顶之上，苏清寒轻纱掠动，寒霜剑意早已无声封锁了四周退路……`;
    }""")
    page.locator("#og_progress_card").scroll_into_view_if_needed()
    page.wait_for_timeout(200)
    page.screenshot(path=str(art_dir / "1280_step3_generating.png"))

    # 5. 1280_step3_completed.png (生成完成)
    page.evaluate("""() => {
        document.getElementById('og_live_badge').style.display = 'none';
        setBar('og_progress_bar', 100);
        document.getElementById('og_progress_text').textContent = '全书生成完成（共 10 章）';
        document.getElementById('og_progress_msg').textContent = '总计 18,650 字，已完整归档至书架。';
        document.getElementById('og_cancel_job').style.display = 'none';
        const rd = document.getElementById('og_open_reader');
        rd.style.display = 'inline-block';
        rd.textContent = '打开阅读';
    }""")
    page.locator("#og_progress_card").scroll_into_view_if_needed()
    page.wait_for_timeout(200)
    page.screenshot(path=str(art_dir / "1280_step3_completed.png"))

    # ---------------- 375px 移动端 ----------------
    page.set_viewport_size({"width": 375, "height": 667})

    # 6. 375_step2_with_bible_and_outline.png
    page.evaluate("window.goToOriginalStep(2)")
    page.wait_for_timeout(200)
    page.screenshot(path=str(art_dir / "375_step2_with_bible_and_outline.png"))

    # 7. 375_step3_idle.png
    page.evaluate("""() => {
        window.goToOriginalStep(3);
        document.getElementById('og_progress_card').style.display = 'none';
    }""")
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(200)
    page.screenshot(path=str(art_dir / "375_step3_idle.png"))

    # 8. 375_step3_generating.png
    page.evaluate("""() => {
        const card = document.getElementById('og_progress_card');
        card.style.display = 'block';
        document.getElementById('og_live_badge').style.display = 'inline-flex';
        setBar('og_progress_bar', 50);
        document.getElementById('og_progress_text').textContent = '正在创作 第 5 章（5/10）';
        document.getElementById('og_cancel_job').style.display = 'inline-block';
        document.getElementById('og_open_reader').style.display = 'none';
    }""")
    page.locator("#og_progress_card").scroll_into_view_if_needed()
    page.wait_for_timeout(200)
    page.screenshot(path=str(art_dir / "375_step3_generating.png"))

    # 验证全部 8 张截图文件存在
    expected_files = [
        "1280_step2_empty.png",
        "1280_step2_with_bible_and_outline.png",
        "1280_step3_idle.png",
        "1280_step3_generating.png",
        "1280_step3_completed.png",
        "375_step2_with_bible_and_outline.png",
        "375_step3_idle.png",
        "375_step3_generating.png"
    ]
    for fn in expected_files:
        p = art_dir / fn
        assert p.exists() and p.stat().st_size > 1000, f"截图文件 {fn} 未正确生成或文件过小"


