# -*- coding: utf-8 -*-
"""
tests/e2e/test_og_redesigned_buttons.py

针对重新设计的「稿纸工坊」#view-original 进行逐项按钮级真浏览器测试，
覆盖工位导航、预设切换、题材与灵感、SpecField AI工具条（重写/润色/指令/锁/历史/保留/撤回）、
人物增删精修、分卷锚点编辑与增删、节拍抽屉、推演弹窗、阶段写作台与检查点回写。
"""

import json
import re
from playwright.sync_api import expect


def _attach_error_listeners(page):
    errors = []

    def on_console(msg):
        if msg.type == "error":
            errors.append(f"console.error: {msg.text}")

    def on_pageerror(err):
        errors.append(f"pageerror: {err}")

    page.on("console", on_console)
    page.on("pageerror", on_pageerror)
    return errors


def test_redesigned_original_studio_every_button(page, live_server):
    errors = _attach_error_listeners(page)

    # 拦截长耗时/多阶段 LLM 组合接口以做确定性测试，其余如 /api/suggest-tropes 与 /api/novel/original/refine-field 走真实后端 + FakeLLMServer
    def handle_deduce(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "code": 200,
                "msg": "推演成功",
                "data": {
                    "schema_version": "2.0.0",
                    "locked_fields": [],
                    "meta": {"title": "推演星海契约", "genre": "科幻未来", "selected_trope": "星际遗迹"},
                    "ideation": {
                        "logline": "星际矿工拾获远古星图芯片，开启星海逃亡。",
                        "hook": "硬核星舰改装",
                        "reader_expectation": "爽快节奏",
                        "theme": "逆境求生",
                        "tone": "冷峻明快",
                    },
                    "worldview": {"background": "外星殖民废墟", "special_rules": "跃迁消耗灵魂晶石"},
                    "protagonist": {
                        "id": "char_protagonist",
                        "name": "林星河",
                        "want": "修复跃迁引擎逃离死星",
                        "need": "学会信任流亡船员",
                        "flaw": "极度多疑",
                        "arc": "成为星海领航员",
                    },
                    "characters": [
                        {
                            "id": "char_key_1",
                            "name": "艾琳",
                            "relation_type": "ally_friend",
                            "role_desc": "机械师，寻回失踪哥哥",
                            "bond_or_conflict": "掌握引擎核心钥匙",
                        }
                    ],
                    "ending": {"climax_vision": "舰队冲破引力锁跃迁至新星域。"},
                    "stages": [
                        {
                            "stage_index": 1,
                            "title": "第一卷：死星潜逃",
                            "expected_chapters": 6,
                            "anchors": {
                                "stage_goal": "集齐跃迁核心零件",
                                "main_obstacle": "星盗围剿",
                                "climax_hook": "引擎超频强行起飞",
                                "transition_springboard": "发现第二份星图坐标",
                            },
                        },
                        {
                            "stage_index": 2,
                            "title": "第二卷：深空暗流",
                            "expected_chapters": 8,
                            "anchors": {
                                "stage_goal": "潜入中立空间站补给",
                                "climax_hook": "空间站叛变爆发",
                            },
                        },
                    ],
                },
            }),
        )

    def handle_beats(route):
        req_data = route.request.post_data_json or {}
        if req_data.get("action") == "save":
            route.continue_()
            return
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "code": 200,
                "data": {
                    "stage_index": 1,
                    "beats": [
                        {"chapter_offset": 1, "title": "废墟拾荒夜", "beat_type": "setup", "summary": "发现古老星图芯片"},
                        {"chapter_offset": 2, "title": "引擎点火爆发", "beat_type": "climax", "summary": "击退追兵突破封锁"},
                        {"chapter_offset": 3, "title": "深空坐标显影", "beat_type": "transition", "summary": "指向未知星域"},
                    ],
                },
            }),
        )

    def handle_stage_start(route):
        route.fulfill(
            status=202,
            content_type="application/json",
            body=json.dumps({
                "code": 202,
                "data": {"job_id": "mock_stage_job_1", "stream_url": "/api/novel/original/stage/stream/mock_stage_job_1"},
            }),
        )

    def handle_stage_stream(route):
        sse_body = (
            'event: chapter_start\ndata: {"global_chapter_idx": 1, "title": "废墟拾荒夜"}\n\n'
            'event: token\ndata: {"token": "星舰引擎发出了沉闷的轰鸣，\\n舱门在真空中缓缓合拢。"}\n\n'
            'event: stage_complete\ndata: {"stage_index": 1}\n\n'
        )
        route.fulfill(status=200, content_type="text/event-stream", body=sse_body)

    def handle_checkpoint(route):
        req_data = route.request.post_data_json or {}
        if req_data.get("action") == "evaluate":
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({
                    "code": 200,
                    "data": {
                        "goal_achievement_pct": 95,
                        "deviation_summary": "主线节奏紧凑，高潮燃点顺利落位。",
                        "character_growth_notes": "主角完成从独狼到船长的蜕变。",
                        "suggested_next_stage_adjustments": {"advice": "第二卷增加反派空间站势力的压迫感"},
                    },
                }),
            )
        else:
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"code": 200, "data": {"next_stage_index": 2}}),
            )

    page.route("**/api/novel/original/deduce", handle_deduce)
    page.route("**/api/novel/original/stage/beats", handle_beats)
    page.route("**/api/novel/original/stage/start", handle_stage_start)
    page.route("**/api/novel/original/stage/stream/**", handle_stage_stream)
    page.route("**/api/novel/original/stage/checkpoint", handle_checkpoint)

    page.goto(live_server)
    page.wait_for_selector("#view-original.active")

    # =========================================================================
    # 1. 左侧栏按钮：设定速览、演示预设、工位标签、模型配置跳转
    # =========================================================================
    # 设定速览开关 + 关闭按钮
    page.locator("button:has-text('设定速览')").click()
    expect(page.locator("#og_shell")).to_have_class(re.compile("aside-off"))
    page.locator("button:has-text('设定速览')").click()
    expect(page.locator("#og_shell")).not_to_have_class(re.compile("aside-off"))
    page.locator("#og_aside button[aria-label='收起速览']").click()
    expect(page.locator("#og_shell")).to_have_class(re.compile("aside-off"))
    page.locator("button:has-text('设定速览')").click()

    # 演示预设切换：赛博修真 -> 都市言情（验证全工位字段同步刷新）
    page.locator("#btn_demo_fantasy").click()
    expect(page.locator("#val_title")).to_have_value("赛博道祖")
    expect(page.locator("#c1_name_badge")).to_have_text("陈拙")
    expect(page.locator("#c1_mono")).to_have_text("陈")
    expect(page.locator("#c2_name_badge")).to_have_text("司徒渊")
    expect(page.locator("#st1_title")).to_have_text("第一卷：铁锈城寨与走私符箓")

    page.locator("#btn_demo_romance").click()
    expect(page.locator("#val_title")).to_have_value("微醺心跳定律")
    expect(page.locator("#c1_name_badge")).to_have_text("陆承舟")
    expect(page.locator("#c2_name_badge")).to_have_text("姜幼柠")
    expect(page.locator("#st1_title")).to_have_text("第一卷：试探同居与薄荷微风")

    # =========================================================================
    # 2. 工位 1 按钮：题材药丸、灵感脑洞（不使用/随机/换一批）、SpecField 工具条
    # =========================================================================
    page.locator("#station_1 .og-chip:has-text('科幻未来')").click()
    expect(page.locator("#val_genre")).to_have_value("科幻未来")
    expect(page.locator("#sum_genre")).to_have_text("科幻未来")

    page.locator("#station_1 .og-chip:has-text('都市言情')").click()
    expect(page.locator("#val_genre")).to_have_value("都市言情")

    # 灵感脑洞：点击卡片 -> 不使用灵感 -> 随机选用 -> 换一批（真实走后端 + FakeLLMServer）
    page.locator("#trope_cards_container .og-trope").nth(1).click()
    expect(page.locator("#trope_cards_container .og-trope").nth(1)).to_have_class(re.compile("active"))
    expect(page.locator("#selected_trope_val")).not_to_have_value("")

    page.locator("#btn_clear_trope").click()
    expect(page.locator("#trope_cards_container .og-trope.active")).to_have_count(0)
    expect(page.locator("#selected_trope_val")).to_have_value("")

    page.locator("button[onclick='randomTrope()']").click()
    expect(page.locator("#trope_cards_container .og-trope.active")).to_have_count(1)

    page.locator("#btn_refresh_tropes").click()
    expect(page.locator("#trope_cards_container .og-trope")).to_have_count(3)

    # SpecField：+ 指令 -> 按此方向重写 -> 保留此版 -> 锁定 -> 历史 -> 解锁 -> 润色 -> 撤回
    page.locator("[data-act='directive'][data-field='logline']").click()
    expect(page.locator("#dir_logline")).to_be_visible()
    page.fill("#dir_input_logline", "突出气味通感与暧昧拉扯")
    page.locator("[data-act='submit-directive'][data-field='logline']").click()
    expect(page.locator("#review_logline")).to_be_visible()
    expect(page.locator("#proposal_text_logline")).to_be_visible(timeout=10000)

    proposal_txt = page.locator("#proposal_text_logline").text_content().strip()
    page.locator("#review_logline [data-act='accept'][data-field='logline']").click()
    expect(page.locator("#val_logline")).to_have_value(proposal_txt)
    expect(page.locator("#review_logline")).to_be_hidden()

    # 锁定按钮 & 历史按钮
    page.locator("#lock_logline").click()
    expect(page.locator("#lock_logline")).to_have_attribute("aria-pressed", "true")
    page.locator("[data-act='history'][data-field='logline']").click()
    page.locator("#lock_logline").click()
    expect(page.locator("#lock_logline")).to_have_attribute("aria-pressed", "false")

    # 其余工位 1 字段按钮（title / hook / reader / theme / tone）测试润色与撤回
    for fld in ("title", "hook", "reader", "theme", "tone"):
        page.locator(f"#station_1 [data-act='polish'][data-field='{fld}']").click()
        expect(page.locator(f"#proposal_text_{fld}")).to_be_visible(timeout=10000)
        page.locator(f"#review_{fld} [data-act='reject'][data-field='{fld}']").click()
        expect(page.locator(f"#review_{fld}")).to_be_hidden()

    # 进入工位 2
    page.locator("#station_1 button:has-text('舞台与群像')").click()
    expect(page.locator("#station_2")).to_be_visible()

    # =========================================================================
    # 3. 工位 2 按钮：rules/micro 重写润色、添加人物/移除、人物重写/润色
    # =========================================================================
    page.locator("#station_2 [data-act='rewrite'][data-field='rules']").click()
    expect(page.locator("#proposal_text_rules")).to_be_visible(timeout=10000)
    page.locator("#review_rules [data-act='reject'][data-field='rules']").click()

    page.locator("#station_2 [data-act='polish'][data-field='micro']").click()
    expect(page.locator("#proposal_text_micro")).to_be_visible(timeout=10000)
    page.locator("#review_micro [data-act='accept'][data-field='micro']").click()

    # 添加人物 & 移除人物
    page.locator("#btn_add_og_char").click()
    expect(page.locator("#station_2 .og-extra-char")).to_have_count(1)
    page.locator("#station_2 .og-extra-char [data-act='remove-char']").click()
    expect(page.locator("#station_2 .og-extra-char")).to_have_count(0)

    # 人物整卡重写 / 润色
    page.locator("#station_2 [data-act='refine-char'][data-field='char1'][data-mode='polish']").click()
    page.locator("#station_2 [data-act='refine-char'][data-field='char2'][data-mode='rewrite']").click()

    # 进入工位 3
    page.locator("#station_2 button:has-text('航线路标')").click()
    expect(page.locator("#station_3")).to_be_visible()

    # =========================================================================
    # 4. 工位 3 按钮：ending 重写、增加一卷/移除、重写锚点、编辑锚点
    # =========================================================================
    page.locator("#station_3 [data-act='rewrite'][data-field='ending']").click()
    expect(page.locator("#proposal_text_ending")).to_be_visible(timeout=10000)
    page.locator("#review_ending [data-act='reject'][data-field='ending']").click()

    page.locator("#btn_add_og_vol").click()
    expect(page.locator("#og_route_list .og-extra-vol")).to_have_count(1)
    page.locator("#og_route_list .og-extra-vol [data-act='remove-vol']").click()
    expect(page.locator("#og_route_list .og-extra-vol")).to_have_count(0)

    page.locator("#station_3 [data-act='rewrite-vol'][data-stage='1']").click()
    edit_btn = page.locator("#station_3 [data-act='edit-vol'][data-stage='2']")
    edit_btn.click()
    expect(edit_btn).to_have_text("完成编辑")
    edit_btn.click()
    expect(edit_btn).to_have_text("编辑锚点")

    # 去写作台（工位 4）
    page.locator("#station_3 button:has-text('去写作台')").click()
    expect(page.locator("#station_4")).to_be_visible()

    # =========================================================================
    # 5. 工位 4 与三大浮层：节拍表抽屉、重新推演、一键推演全案、开始本卷写作与检查点
    # =========================================================================
    # 打开节拍表抽屉 -> 重新推演节拍 -> 确认节拍
    page.locator("#station_4 button:has-text('在抽屉中编辑')").click()
    expect(page.locator("#beat_drawer")).to_be_visible()
    expect(page.locator("#beat_items_list .og-beat")).to_have_count(3, timeout=10000)
    page.locator("#beat_drawer button:has-text('重新推演节拍')").click()
    page.locator("#beat_drawer button:has-text('确认节拍')").click()
    expect(page.locator("#beat_drawer")).to_be_hidden()

    # 工位 4 重新推演按钮
    page.locator("#btn_regen_beats").click()
    expect(page.locator("#beats_list li")).to_have_count(3, timeout=10000)

    # 一键推演全案弹窗
    page.locator("button:has-text('一键推演全案')").click()
    expect(page.locator("#chained_modal")).to_be_visible()
    expect(page.locator("#chained_modal")).to_be_hidden(timeout=10000)
    expect(page.locator("#val_title")).to_have_value("推演星海契约")

    # 切回工位 4 并启动本卷写作
    page.locator("#step_tab_4").click()
    page.locator("#btn_run_stage").click()
    expect(page.locator("#stage_runner_view")).to_be_visible()
    expect(page.locator("#box_checkpoint")).to_be_visible(timeout=10000)
    expect(page.locator("#checkpoint_modal")).to_be_visible(timeout=10000)

    # 检查点弹窗关闭 & 回写
    page.locator("#checkpoint_modal button:has-text('稍后处理')").click()
    expect(page.locator("#checkpoint_modal")).to_be_hidden()
    page.locator("#box_checkpoint [data-act='writeback']").click()

    # 管理模型跳转按钮
    page.locator("#btn_manage_og").click()
    expect(page.locator("#view-settings")).to_be_visible()

    assert len(errors) == 0, f"发现前端控制台或脚本错误: {errors}"
