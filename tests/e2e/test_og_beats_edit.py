"""E2E tests for Original Studio beat drawer caching and manual editing."""

import json
from playwright.sync_api import expect

from tests.e2e.conftest import PageMonitor


def test_beat_drawer_no_redundant_regen_and_manual_edit(page, live_server):
    """验证：1) 首次打开生成1次，二次打开不重推；2) 支持手动编辑/增删并保存；3) 点重新推演才再次生成。"""
    monitor = PageMonitor(page, "og_beats_edit")
    beat_calls = []

    def handle_beats(route):
        req = route.request
        data = req.post_data_json or {}
        action = data.get("action") or "generate"
        st_idx = int(data.get("stage_index") or 1)
        beat_calls.append((action, st_idx))
        if action == "save":
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({
                    "code": 200,
                    "msg": "beats saved",
                    "data": {"stage_index": st_idx, "beats": data.get("beats") or []},
                }),
            )
            return
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "code": 200,
                "msg": "beats generated",
                "data": {
                    "stage_index": st_idx,
                    "beats": [
                        {"chapter_offset": 1, "title": "第1章 原有节拍", "beat_type": "setup", "summary": "初始梗概", "planted_clues": []},
                        {"chapter_offset": 2, "title": "第2章 阶段爆发", "beat_type": "climax", "summary": "高潮梗概", "planted_clues": []},
                    ],
                },
            }),
        )

    page.route("**/api/novel/original/stage/beats", handle_beats)
    page.goto(live_server)
    page.wait_for_load_state("networkidle")

    page.locator("#step_tab_4").click()
    page.wait_for_timeout(200)

    # 1. 首次打开抽屉 -> 触发 1 次 generate
    page.locator("#station_4 button:has-text('在抽屉中编辑')").click()
    expect(page.locator("#beat_drawer")).to_be_visible()
    expect(page.locator("#beat_items_list .og-beat")).to_have_count(2)
    assert [c for c in beat_calls if c[0] == "generate"] == [("generate", 1)]

    # 2. 关闭后再次打开 -> 命中缓存，不触发 generate
    page.locator("#beat_drawer button[aria-label='关闭']").click()
    expect(page.locator("#beat_drawer")).to_be_hidden()
    page.locator("#station_4 button:has-text('在抽屉中编辑')").click()
    expect(page.locator("#beat_drawer")).to_be_visible()
    expect(page.locator("#beat_items_list .og-beat")).to_have_count(2)
    assert [c for c in beat_calls if c[0] == "generate"] == [("generate", 1)]

    # 3. 手动修改第 1 章标题与梗概，并新增一章，然后点确认节拍
    first_card = page.locator("#beat_items_list .og-beat").first
    first_card.locator(".og-beat-title-inp").fill("第1章 手动修改标题")
    first_card.locator(".og-beat-summary-inp").fill("手动填写的章节梗概")
    page.locator("#btn_add_beat_item").click()
    expect(page.locator("#beat_items_list .og-beat")).to_have_count(3)

    page.locator("#beat_drawer button:has-text('确认节拍')").click()
    expect(page.locator("#beat_drawer")).to_be_hidden()
    assert any(c[0] == "save" for c in beat_calls)
    expect(page.locator("#beats_list li")).to_have_count(3)
    expect(page.locator("#beats_list li").first).to_contain_text("第1章 手动修改标题")

    # 4. 再次打开抽屉并点击「重新推演节拍」-> 显式触发第 2 次 generate
    page.locator("#station_4 button:has-text('在抽屉中编辑')").click()
    page.locator("#beat_drawer button:has-text('重新推演节拍')").click()
    expect(page.locator("#beat_items_list .og-beat")).to_have_count(2)
    assert len([c for c in beat_calls if c[0] == "generate"]) == 2

    monitor.assert_no_errors("og_beats_edit")
