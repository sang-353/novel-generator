"""E2E tests for Original Novel Studio Drafts Box (save, list, blank, restore, delete)."""

from tests.e2e.conftest import PageMonitor


def test_original_studio_draft_box_lifecycle(page, live_server):
    """验证：填写半成品 -> 保存草稿 -> 新建空白 -> 从草稿箱恢复 -> 删除草稿。"""
    monitor = PageMonitor(page, "og_draft_box_lifecycle")

    page.goto(live_server)
    page.wait_for_load_state("networkidle")

    # 1. 填写一半内容
    page.fill("#val_title", "未完待续草稿测试")
    page.fill("#val_logline", "写了一半的一句话核心创意")

    # 2. 点击“保存草稿”
    page.locator("#btn_og_save_draft").click()
    page.wait_for_timeout(400)
    assert "已存草稿箱" in page.locator("#og_draft_status").inner_text()

    # 3. 打开草稿箱，确认列表中有该草稿
    page.locator("#btn_og_draft_box").click()
    page.wait_for_timeout(400)
    assert page.locator("#og_drafts_modal").is_visible()
    assert "未完待续草稿测试" in page.locator("#og_drafts_list").inner_text()

    # 4. 点击“新建空白草稿”，确认表单被清空且弹窗关闭
    page.locator("#og_drafts_new_btn").click()
    page.wait_for_timeout(300)
    assert not page.locator("#og_drafts_modal").is_visible()
    assert page.input_value("#val_title") == ""

    # 5. 重新打开草稿箱并点击“继续编辑”，确认内容完整恢复
    page.locator("#btn_og_draft_box").click()
    page.wait_for_timeout(400)
    target_item = page.locator("#og_drafts_list .og-draft-item", has_text="未完待续草稿测试").first
    target_item.locator("[data-draft-act='load']").click()
    page.wait_for_timeout(400)
    assert not page.locator("#og_drafts_modal").is_visible()
    assert page.input_value("#val_title") == "未完待续草稿测试"
    assert page.input_value("#val_logline") == "写了一半的一句话核心创意"

    # 6. 再次打开草稿箱并删除该草稿
    page.locator("#btn_og_draft_box").click()
    page.wait_for_timeout(400)
    page.locator("#og_drafts_list .og-draft-item", has_text="未完待续草稿测试").first.locator("[data-draft-act='delete']").click()
    page.wait_for_timeout(400)
    assert "未完待续草稿测试" not in page.locator("#og_drafts_list").inner_text()

    page.locator("#og_drafts_cancel_btn").click()
    page.wait_for_timeout(250)
    assert not page.locator("#og_drafts_modal").is_visible()

    monitor.assert_no_errors("og_draft_box_lifecycle")
