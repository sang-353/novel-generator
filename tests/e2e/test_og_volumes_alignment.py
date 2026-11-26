"""E2E tests for Original Studio volume outline alignment (vol 1, 2, 3+)."""

from playwright.sync_api import expect

from tests.e2e.conftest import PageMonitor


def test_volume_1_2_3_actions_aligned_and_removable(page, live_server):
    """验证第 1、2 卷与新增第 3 卷均具备 重写锚点/编辑锚点/去写作台/移除，且至少保留一卷。"""
    monitor = PageMonitor(page, "og_volumes_alignment")

    page.goto(live_server)
    page.wait_for_load_state("networkidle")

    # 切到工位 3：航线路标
    page.locator("#step_tab_3").click()
    page.wait_for_timeout(200)

    # 新增第 3 卷
    page.locator("#btn_add_og_vol").click()
    page.wait_for_timeout(200)
    expect(page.locator("#og_route_list .og-vol")).to_have_count(3)

    # 1. 第 1、2、3 卷都应同时拥有 rewrite-vol / edit-vol / remove-vol，且均有 4 个锚点框
    for st in ("1", "2", "3"):
        vol = page.locator(f"#og_route_list .og-vol[data-stage='{st}']")
        expect(vol.locator(f"[data-act='rewrite-vol'][data-stage='{st}']")).to_be_visible()
        expect(vol.locator(f"[data-act='edit-vol'][data-stage='{st}']")).to_be_visible()
        expect(vol.locator("[data-act='remove-vol']")).to_be_visible()
        expect(vol.locator(".og-anchor")).to_have_count(4)

    # 2. 第 1 卷可进入编辑并保存
    v1_edit = page.locator("#og_route_list .og-vol[data-stage='1'] [data-act='edit-vol']")
    v1_edit.click()
    expect(v1_edit).to_have_text("完成编辑")
    page.locator("#st1_title").fill("第一卷：已对齐编辑")
    v1_edit.click()
    expect(v1_edit).to_have_text("编辑锚点")
    expect(page.locator("#st1_title")).to_have_text("第一卷：已对齐编辑")

    # 3. 移除第 2 卷与第 1 卷，仅剩第 3 卷；再点移除第 3 卷应触发保底保留 1 卷
    page.locator("#og_route_list .og-vol[data-stage='2'] [data-act='remove-vol']").click()
    expect(page.locator("#og_route_list .og-vol")).to_have_count(2)

    page.locator("#og_route_list .og-vol[data-stage='1'] [data-act='remove-vol']").click()
    expect(page.locator("#og_route_list .og-vol")).to_have_count(1)

    page.locator("#og_route_list .og-vol[data-stage='3'] [data-act='remove-vol']").click()
    expect(page.locator("#og_route_list .og-vol")).to_have_count(1)

    # 4. 切回演示预设，确认第 1、2 卷卡片被正常补建恢复
    page.locator("#btn_demo_romance").click()
    page.wait_for_timeout(200)
    expect(page.locator("#og_route_list .og-vol[data-stage='1']")).to_be_visible()
    expect(page.locator("#og_route_list .og-vol[data-stage='2']")).to_be_visible()
    expect(page.locator("#st1_title")).to_have_text("第一卷：试探同居与薄荷微风")

    # 5. 移除第 2 卷仅剩第 1 卷后，点击“增加一卷”应创建第 2 卷（而非第 3 卷）
    page.locator("#og_route_list .og-vol[data-stage='2'] [data-act='remove-vol']").click()
    expect(page.locator("#og_route_list .og-vol")).to_have_count(1)
    page.locator("#btn_add_og_vol").click()
    page.wait_for_timeout(200)
    expect(page.locator("#og_route_list .og-vol")).to_have_count(2)
    expect(page.locator("#og_route_list .og-vol[data-stage='2']")).to_be_visible()
    expect(page.locator("#st2_title")).to_contain_text("第2卷")
    expect(page.locator("#og_route_list .og-vol[data-stage='2'] .og-anchor")).to_have_count(4)

    monitor.assert_no_errors("og_volumes_alignment")
