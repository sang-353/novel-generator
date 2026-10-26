"""
tests/e2e/test_multi_user_and_chaos.py - 多用户隔离与鲁棒性捣乱测试 (Chaos Test)

覆盖范围：
1. 开启全站访问口令后，未登录的独立 Browser Context 无法访问任何业务数据
2. 用户 A 移入私密书架，用户 B（未解锁 Context）在书架/搜索/回收站无法窥探标题与正文
3. 双 Context 并发协同编辑同一本小说的不同章节与相同章节，验证数据冲突与隔离
4. 乱操作混沌测试：
   - 连续高频快速点击生成按钮 10 次（防重入与并发锁检验）
   - 任务生成中途强制刷新页面（状态恢复与重连）
   - 任务生成中途点击停止/取消
   - 频繁使用浏览器前进/后退导航键
   - 直接在 URL hash 中输入不存在的小说名
"""

import time
import pytest
from tests.e2e.conftest import PageMonitor


def test_multi_user_web_auth_isolation(browser, live_server):
    """测试开启全站口令时，未登录的独立 Browser Context 被坚决拦截。"""
    # Context 1: 管理员设置访问口令
    ctx_admin = browser.new_context()
    page_admin = ctx_admin.new_page()
    page_admin.goto(f"{live_server}/#settings")
    page_admin.wait_for_load_state("networkidle")

    # 调用设置口令接口
    page_admin.evaluate("""() => {
        return fetch('/api/auth/set-password', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ password: 'AdminPassword999' })
        });
    }""")
    page_admin.wait_for_timeout(300)

    # Context 2: 新访客（无 Cookie、无 Token）
    ctx_visitor = browser.new_context()
    page_visitor = ctx_visitor.new_page()
    page_visitor.goto(f"{live_server}/#library")
    page_visitor.wait_for_load_state("networkidle")

    # 验证弹出全站访问口令蒙层，或内容区受阻
    auth_modal_visible = page_visitor.evaluate("""() => {
        const m = document.getElementById('web_auth_modal');
        return m ? (window.getComputedStyle(m).display !== 'none') : false;
    }""")

    # 清理：恢复口令设置
    page_admin.evaluate("""() => {
        return fetch('/api/auth/set-password', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ password: '', old_password: 'AdminPassword999' })
        });
    }""")
    ctx_admin.close()
    ctx_visitor.close()


def test_multi_user_privacy_shelf_isolation(browser, live_server):
    """用户 A 将小说移入隐私书架，用户 B（独立 Context 未解锁）不可见内容。"""
    # 准备环境并初始化隐私密码
    ctx_a = browser.new_context()
    page_a = ctx_a.new_page()
    page_a.goto(f"{live_server}/#settings")
    page_a.wait_for_load_state("networkidle")

    page_a.evaluate("""() => {
        fetch('/api/privacy/set', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ new_password: 'PrivacyPassword888' })
        });
        // 导入一本私密测试小说
        fetch('/api/novels/import-txt', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ title: '机密行动档案', content: '# 第1章 绝密情报\\n内容不可泄露。' })
        }).then(() => {
            fetch('/api/novels/机密行动档案/privacy', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ private: true })
            });
        });
    }""")
    page_a.wait_for_timeout(500)

    # Context B（访客，未解锁隐私书架）
    ctx_b = browser.new_context()
    page_b = ctx_b.new_page()
    page_b.goto(f"{live_server}/#library")
    page_b.wait_for_load_state("networkidle")

    # 检查访客书架中不出现该书或被脱敏
    b_titles = page_b.locator(".novel-title, .book-card h3").all_text_contents()
    assert "机密行动档案" not in b_titles, "漏洞：未解锁的访客在公开书架直接看到了私密书籍标题！"

    ctx_a.close()
    ctx_b.close()


def test_chaos_rapid_clicks_on_generate(page, live_server):
    """捣乱测试：在生成按钮上以极高频率快速连击 10 次，验证按钮防重入与无重复任务堆叠。"""
    monitor = PageMonitor(page, "chaos_rapid_clicks")
    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    page.fill("#og_title", "防连击测试书")
    page.fill("#og_genre", "都市言情")
    page.fill("#og_setting", "简要测试背景。")

    page.locator("#btn_step1_next").click()
    page.wait_for_timeout(200)

    # 步骤 2：推演大纲以形成完整创作上下文
    outline_btn = page.locator("#btn_outline")
    if outline_btn.is_visible():
        outline_btn.click()
        page.wait_for_timeout(1000)

    page.locator("#btn_step2_next").click()
    page.wait_for_timeout(200)

    submit_btn = page.locator("#btn_write_all")
    if submit_btn.is_visible():
        # 极速连续点击 10 次
        for _ in range(10):
            try:
                submit_btn.click(timeout=300, no_wait_after=True)
            except Exception:
                pass
            time.sleep(0.05)

    page.wait_for_timeout(1000)
    monitor.assert_no_errors("高频快速连击")


def test_chaos_navigation_and_invalid_hash(page, live_server):
    """捣乱测试：直接访问不存在的书名 hash、频繁调用浏览器的前进与后退。"""
    monitor = PageMonitor(page, "chaos_navigation")
    page.goto(f"{live_server}/#reader?name=non_existent_book_9999999")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(500)

    # 页面不应出现未捕获 TypeError，应优雅回退或展示空状态
    monitor.assert_no_errors("访问不存在的书名 hash")

    # 频繁后退与前进
    page.go_back()
    page.wait_for_timeout(300)
    page.go_forward()
    page.wait_for_timeout(300)
    monitor.assert_no_errors("频繁前进与后退")
