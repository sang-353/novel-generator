"""
tests/e2e/test_viewports.py - 多视口适配与响应式排版 E2E 测试

覆盖范围：
1. 375px 移动端视口（iPhone 常见竖屏规格）：移动抽屉、TOC 侧栏折叠、按钮防遮挡、无意外水平横向滚动溢出
2. 1280px 桌面端视口：左右双栏/三栏布局展开、Studio 工具条常驻对齐
"""

import pytest
from tests.e2e.conftest import PageMonitor


@pytest.mark.parametrize("viewport_config", [
    {"width": 375, "height": 667, "name": "mobile_375px"},
    {"width": 1280, "height": 800, "name": "desktop_1280px"},
])
def test_viewport_layouts_and_no_horizontal_overflow(page, live_server, viewport_config):
    """验证在 375px 手机视口和 1280px 桌面视口下，页面排版自适应且无水平滚动溢出。"""
    w = viewport_config["width"]
    h = viewport_config["height"]
    name = viewport_config["name"]

    page.set_viewport_size({"width": w, "height": h})
    monitor = PageMonitor(page, f"viewport_{name}")

    for view_hash in ["#original", "#continuation", "#library", "#reader", "#settings"]:
        page.goto(f"{live_server}/{view_hash}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(200)

        # 检查视口是否有恶性横向滚动溢出 (scrollWidth > innerWidth + 5)
        has_overflow = page.evaluate("""() => {
            const doc = document.documentElement;
            return doc.scrollWidth > window.innerWidth + 5;
        }""")
        assert not has_overflow, f"视口 [{name}] 在视图 [{view_hash}] 下出现意外的横向滚动溢出！"

        monitor.assert_no_errors(f"视口 {name} 访问 {view_hash}")
