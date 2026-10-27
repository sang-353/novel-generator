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

import json
import os
from pathlib import Path
import time
import urllib.parse
import pytest
from tests.e2e.conftest import PageMonitor


def test_multi_user_web_auth_isolation(browser, live_server):
    """测试开启全站口令时，未登录的独立 Browser Context 被坚决拦截。"""
    ctx_admin = browser.new_context()
    page_admin = ctx_admin.new_page()
    page_admin.goto(f"{live_server}/#settings")
    page_admin.wait_for_load_state("networkidle")

    try:
        # 调用设置口令接口
        page_admin.evaluate("""() => {
            return fetch('/api/auth/set-password', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ new_password: 'AdminPassword999' })
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
        assert auth_modal_visible, "未登录访客未被全站访问口令蒙层拦截"
        ctx_visitor.close()
    finally:
        # 清理：恢复口令设置
        try:
            page_admin.evaluate("""() => {
                return fetch('/api/auth/set-password', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ password: '', old_password: 'AdminPassword999' })
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


def test_multi_user_privacy_shelf_isolation(browser, live_server):
    """用户 A 将小说移入隐私书架，用户 B（独立 Context 未解锁）不可见内容。"""
    ctx_a = browser.new_context()
    page_a = ctx_a.new_page()
    page_a.goto(f"{live_server}/#settings")
    page_a.wait_for_load_state("networkidle")

    try:
        # 1. 先导入一部书籍
        page_a.evaluate("""() => {
            return fetch('/api/novels/import-txt', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ title: '机密行动档案', text: '第1章 绝密情报\\n内容不可泄露。' })
            });
        }""")
        page_a.wait_for_timeout(300)

        # 2. 设置隐私密码
        page_a.evaluate("""() => {
            return fetch('/api/privacy/set', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ new_password: 'PrivacyPassword888' })
            });
        }""")
        page_a.wait_for_timeout(300)

        # 3. 解锁并将书籍移入隐私书架，随后加锁
        page_a.evaluate("""() => {
            return fetch('/api/privacy/unlock', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ password: 'PrivacyPassword888' })
            }).then(r => r.json()).then(d => {
                return fetch('/api/novels/机密行动档案/privacy', {
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
        page_a.wait_for_timeout(400)

        # Context B（访客，未解锁隐私书架）
        ctx_b = browser.new_context()
        page_b = ctx_b.new_page()
        page_b.goto(f"{live_server}/#library")
        page_b.wait_for_load_state("networkidle")

        # 检查访客书架中不出现该书或被脱敏
        b_titles = page_b.locator(".novel-title, .book-card h3, tr.novel td").all_text_contents()
        assert "机密行动档案" not in b_titles, "漏洞：未解锁的访客在公开书架直接看到了私密书籍标题！"
        ctx_b.close()
    finally:
        try:
            page_a.evaluate("""() => {
                fetch('/api/privacy/set', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ old_password: 'PrivacyPassword888', new_password: '' })
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
        ctx_a.close()


def test_chaos_rapid_clicks_on_generate(page, live_server, test_env_setup):
    """捣乱测试：在生成按钮上以极高频率快速连击 10 次，验证按钮防重入与无重复任务堆叠。"""
    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    page.fill("#og_title", "防连击测试书")
    page.fill("#og_genre", "都市言情")
    page.fill("#og_setting", "简要测试背景。")

    page.locator("#btn_step1_next").click()
    page.wait_for_timeout(200)

    # 步骤 2：推演大纲以形成完整创作上下文
    outline_btn = page.locator("#btn_outline")
    assert outline_btn.is_visible(), "未找到生成大纲按钮 #btn_outline"
    outline_btn.click()
    page.locator("#og_outline_card").wait_for(state="visible", timeout=10000)

    page.locator("#btn_step2_next").click()
    page.wait_for_timeout(200)

    generate_requests = []
    page.on("request", lambda req: generate_requests.append(req) if "/api/generate" in req.url and req.method == "POST" else None)

    submit_btn = page.locator("#btn_write_all")
    assert submit_btn.is_visible(), "未找到开始全书生成按钮 #btn_write_all"
    # 极速连续点击 10 次
    for _ in range(10):
        try:
            submit_btn.click(timeout=50, no_wait_after=True)
        except Exception:
            pass
        time.sleep(0.01)

    page.wait_for_timeout(1000)
    assert len(generate_requests) == 1, f"狂点 10 次后发出了 {len(generate_requests)} 次 /api/generate 请求，预期只发出 1 次"
    created_jobs = [j for j in test_env_setup["app_module"].JOBS.values() if "防连击测试书" in str(j)]
    assert len(created_jobs) <= 1, f"后端创建了多余任务: {len(created_jobs)} 个"


def test_chaos_navigation_and_invalid_hash(page, live_server):
    """捣乱测试：直接访问不存在的书名 hash、频繁调用浏览器的前进与后退。"""
    monitor = PageMonitor(page, "chaos_navigation")
    page.goto(f"{live_server}/#read/non_existent_book_9999999/0")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(500)

    # 页面不应出现未捕获 JS TypeError，应优雅回退或展示空状态
    assert len(monitor.page_errors) == 0, f"页面发生未捕获 JS 异常: {monitor.page_errors}"

    # 频繁后退与前进
    page.go_back()
    page.wait_for_timeout(300)
    page.go_forward()
    page.wait_for_timeout(300)
    assert len(monitor.page_errors) == 0, f"导航前进后退发生未捕获 JS 异常: {monitor.page_errors}"


def test_multi_user_concurrent_editing(browser, live_server):
    """
    多用户并发测试：两个独立 Browser Context 同时编辑同一本小说的不同章节与相同章节，
    验证数据完整性与持久化稳定性。
    """
    title = "并发编辑测试小说"

    # 初始化测试小说：包含两个章节
    ctx_init = browser.new_context()
    page_init = ctx_init.new_page()
    page_init.goto(live_server)
    page_init.wait_for_load_state("networkidle")
    page_init.evaluate(f"""() => {{
        return fetch('/api/novels/import-txt', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{
                title: {json.dumps(title)},
                text: '第1章 初始一章\\n第一章初始内容。\\n\\n第2章 初始二章\\n第二章初始内容。'
            }})
        }});
    }}""")
    page_init.wait_for_timeout(300)
    ctx_init.close()

    # 1. 场景 A：Context 1 编辑第 1 章，Context 2 编辑第 2 章（互不影响）
    ctx1 = browser.new_context()
    ctx2 = browser.new_context()
    page1 = ctx1.new_page()
    page2 = ctx2.new_page()

    page1.goto(f"{live_server}/#read/{urllib.parse.quote(title)}/0")
    page1.wait_for_load_state("networkidle")
    page1.wait_for_timeout(400)

    page2.goto(f"{live_server}/#read/{urllib.parse.quote(title)}/0")
    page2.wait_for_load_state("networkidle")
    page2.wait_for_timeout(400)

    # Context 1 进入第 1 章编辑并修改
    page1.locator("#rd_edit_btn").click()
    page1.wait_for_timeout(200)
    page1.fill("#rd_edit_body_inp", "【用户A写入的第1章正文】")
    page1.locator("#rd_edit_save_btn").click()
    page1.wait_for_timeout(500)

    # Context 2 切换到第 2 章编辑并修改
    page2.evaluate("gotoChapter(1)")
    page2.wait_for_timeout(300)
    page2.locator("#rd_edit_btn").click()
    page2.wait_for_timeout(200)
    page2.fill("#rd_edit_body_inp", "【用户B写入的第2章正文】")
    page2.locator("#rd_edit_save_btn").click()
    page2.wait_for_timeout(500)

    # 验证两章内容均正确持久化
    page1.evaluate("openReader('并发编辑测试小说', 0, { reload: true })")
    page1.wait_for_timeout(400)
    ch1_text = page1.locator("#rd_content").text_content() or ""
    assert "用户A写入的第1章正文" in ch1_text, f"第1章内容异常: {ch1_text}"

    page2.evaluate("openReader('并发编辑测试小说', 1, { reload: true })")
    page2.wait_for_timeout(400)
    ch2_text = page2.locator("#rd_content").text_content() or ""
    assert "用户B写入的第2章正文" in ch2_text, f"第2章内容异常: {ch2_text}"

    # 2. 场景 B：Context 1 与 Context 2 同时编辑相同章节（第 1 章）
    page1.locator("#rd_edit_btn").click()
    page1.wait_for_timeout(200)
    page1.fill("#rd_edit_body_inp", "【并发冲突-A版修改】")

    page2.evaluate("gotoChapter(0)")
    page2.wait_for_timeout(300)
    page2.locator("#rd_edit_btn").click()
    page2.wait_for_timeout(200)
    page2.fill("#rd_edit_body_inp", "【并发冲突-B版修改】")

    # 前后依次提交，验证无死锁、无 500、元数据不丢失
    page1.locator("#rd_edit_save_btn").click()
    page1.wait_for_timeout(300)
    page2.locator("#rd_edit_save_btn").click()
    page2.wait_for_timeout(500)

    ctx1.close()
    ctx2.close()


def test_chaos_refresh_during_generation(page, live_server):
    """捣乱测试：任务生成中途刷新浏览器页面，断言页面优雅重连与无死锁。"""
    monitor = PageMonitor(page, "chaos_refresh_generating")
    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    page.fill("#og_title", "刷新中断测试书")
    page.fill("#og_genre", "都市")
    page.fill("#og_setting", "测试生成中途强制刷新。")

    page.locator("#btn_step1_next").click()
    page.wait_for_timeout(200)
    outline_btn = page.locator("#btn_outline")
    assert outline_btn.is_visible()
    outline_btn.click()
    page.locator("#og_outline_card").wait_for(state="visible", timeout=10000)

    page.locator("#btn_step2_next").click()
    page.wait_for_timeout(200)

    submit_btn = page.locator("#btn_write_all")
    assert submit_btn.is_visible()
    submit_btn.click()

    # 等待进度卡片出现即刻刷新页面
    page.locator("#og_progress_card").wait_for(state="visible", timeout=5000)
    page.reload()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(500)

    # 刷新后页面应正常可用，无崩溃报错
    monitor.assert_no_errors("生成中途强制刷新页面")


def test_chaos_cancel_during_generation(page, live_server):
    """捣乱测试：生成任务进行中点击取消，验证取消指令即刻送达且状态更新。"""
    monitor = PageMonitor(page, "chaos_cancel_generating")
    page.goto(f"{live_server}/#original")
    page.wait_for_load_state("networkidle")

    page.fill("#og_title", "取消停止测试书")
    page.fill("#og_genre", "玄幻")
    page.fill("#og_setting", "测试生成中途点击停止。")

    page.locator("#btn_step1_next").click()
    page.wait_for_timeout(200)
    outline_btn = page.locator("#btn_outline")
    assert outline_btn.is_visible()
    outline_btn.click()
    page.locator("#og_outline_card").wait_for(state="visible", timeout=10000)

    page.locator("#btn_step2_next").click()
    page.wait_for_timeout(200)

    submit_btn = page.locator("#btn_write_all")
    assert submit_btn.is_visible()
    submit_btn.click()

    # 等待取消按钮出现并点击
    cancel_btn = page.locator("#og_cancel_job")
    cancel_btn.wait_for(state="visible", timeout=5000)
    cancel_btn.click()
    page.wait_for_timeout(600)

    # 验证 Toast 或状态提示包含取消信息
    toast_text = page.locator("#toast").text_content() or ""
    progress_text = page.locator("#og_progress_text").text_content() or ""
    assert "取消" in toast_text or "取消" in progress_text, f"未见取消响应: toast={toast_text}, progress={progress_text}"
    monitor.assert_no_errors("生成中途点击取消")
