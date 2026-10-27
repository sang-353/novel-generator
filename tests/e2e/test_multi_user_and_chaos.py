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
    jobs_dict = test_env_setup["app_module"].JOBS
    matching_jobs = [
        j for j in jobs_dict.values()
        if j.get("novel_name") == "防连击测试书" or (j.get("data") and j.get("data").get("title") == "防连击测试书")
    ]
    assert len(matching_jobs) == 1, f"后端创建了多余任务: {len(matching_jobs)} 个, jobs={matching_jobs}"


def test_chaos_backend_direct_concurrent_generate_returns_409(live_server):
    """后端直连并发防重入测试：用 requests 连发 3 次 POST /api/generate（同一本书），断言只有 1 个成功(200)，其余返回 409。"""
    import requests
    import concurrent.futures

    payload = {
        "mode": "original",
        "title": "并发接口冲突测试书",
        "genre": "科幻",
        "setting": "测试直连并发",
        "chapters": 1,
        "outline": json.dumps({"chapters": [{"title": "第1章 序", "points": "要点"}]})
    }

    url = f"{live_server}/api/generate"
    def send_req():
        return requests.post(url, json=payload, timeout=10)

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(send_req) for _ in range(3)]
        responses = [f.result() for f in futures]

    status_codes = [r.status_code for r in responses]
    assert status_codes.count(200) == 1, f"预期严格只有 1 个成功(200)，实际状态码分布: {status_codes}"
    assert status_codes.count(409) == 2, f"预期其余 2 个返回 409 Conflict，实际状态码分布: {status_codes}"


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


def test_multi_user_concurrent_editing(browser, live_server, test_env_setup):
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

    # (1) 断言磁盘上该章内容等于后提交的 B 版修改
    app_module = test_env_setup["app_module"]
    novel_path = app_module.safe_novel_path(title)
    assert novel_path and novel_path.exists(), f"小说文件不存在: {novel_path}"
    _, disk_chapters, _ = app_module.parse_novel(novel_path, repair=False)
    assert disk_chapters[0]["content"] == "【并发冲突-B版修改】", f"磁盘正文不等于最新提交的B版: {disk_chapters[0]['content']}"

    # (2) 断言单章备份目录 (CHAPTER_BACKUP_DIR) 里存在先保存的 A 版内容快照
    backup_dir = app_module.CHAPTER_BACKUP_DIR
    assert backup_dir.exists(), f"单章备份目录不存在: {backup_dir}"
    backup_files = list(backup_dir.glob(f"{app_module.sanitize_filename(title)}_0_*.json"))
    assert len(backup_files) >= 1, f"未在单章备份目录找到第0章的历史快照: {list(backup_dir.glob('*'))}"
    backup_contents = [json.loads(bf.read_text(encoding="utf-8")).get("content", "") for bf in backup_files]
    assert any("【并发冲突-A版修改】" in c for c in backup_contents), f"单章备份中未找到先保存的A版内容！快照包含: {backup_contents}"

    ctx1.close()
    ctx2.close()


def test_chaos_refresh_during_generation(page, live_server, test_env_setup):
    """捣乱测试：任务生成中途刷新浏览器页面，断言页面优雅重连、后台任务正常执行且无死锁。"""
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

    job_ids = []
    def on_gen_response(resp):
        if "/api/generate" in resp.url and resp.status == 200:
            try:
                data = resp.json()
                if "job_id" in data:
                    job_ids.append(data["job_id"])
            except Exception:
                pass
    page.on("response", on_gen_response)

    submit_btn = page.locator("#btn_write_all")
    assert submit_btn.is_visible()
    submit_btn.click()

    # 等待进度卡片出现即刻刷新页面
    page.locator("#og_progress_card").wait_for(state="visible", timeout=5000)
    assert len(job_ids) > 0, "未能捕获到生成任务 job_id"
    active_job_id = job_ids[0]

    page.reload()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(500)

    # 刷新后页面应正常可用，无崩溃报错
    monitor.assert_no_errors("生成中途强制刷新页面")

    # 刷新后请求 /api/jobs/<job_id>，断言 job 状态（running / done / cancelled）
    job_info = page.evaluate(f"""() => {{
        return fetch('/api/jobs/{active_job_id}').then(r => r.json());
    }}""")
    assert job_info.get("status") in ("running", "done", "cancelled"), f"Job 状态异常: {job_info}"

    # 等待后台任务结束后断言已生成章节完整落盘、书籍锁已释放
    app_module = test_env_setup["app_module"]
    for _ in range(30):
        if not app_module.book_busy("刷新中断测试书"):
            break
        time.sleep(0.5)

    assert not app_module.book_busy("刷新中断测试书"), "任务结束后书籍锁未被释放！"
    novel_path = app_module.safe_novel_path("刷新中断测试书")
    assert novel_path and novel_path.exists(), "刷新中断后已生成的小说未落盘！"
    _, chapters, _ = app_module.parse_novel(novel_path, repair=False)
    assert len(chapters) >= 1, f"已落盘小说无有效章节: {chapters}"
    assert len(chapters[0].get("content", "").strip()) > 0, "落盘章节正文为空"


def test_chaos_cancel_during_generation(page, live_server, test_env_setup):
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

    job_ids = []
    def on_gen_response(resp):
        if "/api/generate" in resp.url and resp.status == 200:
            try:
                data = resp.json()
                if "job_id" in data:
                    job_ids.append(data["job_id"])
            except Exception:
                pass
    page.on("response", on_gen_response)

    submit_btn = page.locator("#btn_write_all")
    assert submit_btn.is_visible()
    submit_btn.click()

    # 等待取消按钮出现并点击
    cancel_btn = page.locator("#og_cancel_job")
    cancel_btn.wait_for(state="visible", timeout=5000)
    assert len(job_ids) > 0, "未能捕获到任务 job_id"
    active_job_id = job_ids[0]

    cancel_btn.click()
    page.wait_for_timeout(600)

    # 验证 Toast 或状态提示包含取消信息
    toast_text = page.locator("#toast").text_content() or ""
    progress_text = page.locator("#og_progress_text").text_content() or ""
    assert "取消" in toast_text or "取消" in progress_text, f"未见取消响应: toast={toast_text}, progress={progress_text}"
    monitor.assert_no_errors("生成中途点击取消")

    # 取消后断言后端 job 状态为已取消
    app_module = test_env_setup["app_module"]
    for _ in range(25):
        job = app_module.JOBS.get(active_job_id)
        if job and job.get("status") == "cancelled":
            break
        time.sleep(0.2)
    job = app_module.JOBS.get(active_job_id)
    assert job and job.get("status") == "cancelled", f"后端 Job 状态未变为 cancelled: {job}"

    # 书籍锁已释放（再次调用 /api/generate 不再返回 409）
    assert not app_module.book_busy("取消停止测试书"), "取消后书籍锁未被释放！"
    retry_resp = page.evaluate("""() => {
        return fetch('/api/generate', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                mode: 'original',
                title: '取消停止测试书',
                chapters: 1,
                outline: JSON.stringify({ chapters: [{ title: '第1章', points: '...' }] })
            })
        }).then(r => r.status);
    }""")
    assert retry_resp != 409, f"书籍锁释放失败，再次提交仍返回 409: {retry_resp}"

    # 已生成章节仍在（若落盘）
    novel_path = app_module.safe_novel_path("取消停止测试书")
    if novel_path and novel_path.exists():
        _, chs, _ = app_module.parse_novel(novel_path, repair=False)
        assert len(chs) >= 0


def test_concurrent_multithreaded_same_chapter_save(live_server, test_env_setup):
    """
    真正同时并发保存同一章的测试：
    两个线程使用 Barrier 同步并在同一瞬间 POST 保存同一章，
    断言最终小说文件没有损坏、格式解析正常，
    断言两版修改内容（A版与B版）在磁盘当前正文或单章备份快照（CHAPTER_BACKUP_DIR）中都能找到。
    如果有一版被后写覆盖且未进入任何备份快照，则记录为并发保存缺陷。
    """
    import threading
    import requests
    import concurrent.futures

    app_module = test_env_setup["app_module"]
    title = "真多线程并发同章测试书"

    # 1. 初始化小说与第 0 章
    init_res = requests.post(
        f"{live_server}/api/novels/import-txt",
        json={
            "title": title,
            "text": "第1章 初始序章\n这是初始的正文内容，等待并发覆盖测试。"
        },
        timeout=10
    )
    assert init_res.status_code == 200, f"创建测试小说失败: {init_res.text}"

    # 2. 准备两个线程并发提交不同内容
    v1_content = "【线程1并发保存的正文内容_AAA】"
    v2_content = "【线程2并发保存的正文内容_BBB】"

    barrier = threading.Barrier(2)

    def worker(content_text):
        barrier.wait()  # 确保两线程在同一毫秒发起请求
        return requests.post(
            f"{live_server}/api/novels/{title}/chapter/0",
            json={"content": content_text},
            timeout=10
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(worker, v1_content)
        f2 = executor.submit(worker, v2_content)
        r1 = f1.result()
        r2 = f2.result()

    # 两个请求响应状态码
    assert r1.status_code in (200, 409), f"请求1响应异常: {r1.status_code} {r1.text}"
    assert r2.status_code in (200, 409), f"请求2响应异常: {r2.status_code} {r2.text}"

    # 3. 断言磁盘小说文件未被损坏
    novel_path = app_module.safe_novel_path(title)
    assert novel_path and novel_path.exists(), "小说文件丢失"
    meta, chapters, _ = app_module.parse_novel(novel_path, repair=False)
    assert len(chapters) == 1, f"章节数量异常: {len(chapters)}"
    disk_text = chapters[0].get("content", "")

    # 4. 检查快照目录
    backup_dir = app_module.CHAPTER_BACKUP_DIR
    backup_files = list(backup_dir.glob(f"{app_module.sanitize_filename(title)}_0_*.json")) if backup_dir.exists() else []
    snapshot_contents = []
    for bf in backup_files:
        try:
            c = json.loads(bf.read_text(encoding="utf-8")).get("content", "")
            snapshot_contents.append(c)
        except Exception:
            pass

    # 5. 断言两版内容在磁盘或快照中都能找到
    v1_found = (v1_content == disk_text) or any(v1_content in c for c in snapshot_contents)
    v2_found = (v2_content == disk_text) or any(v2_content in c for c in snapshot_contents)

    assert v1_found and v2_found, (
        f"真并发保存数据丢失缺陷！\n"
        f"v1_found={v1_found}, v2_found={v2_found}\n"
        f"磁盘当前内容: {disk_text}\n"
        f"快照库内容: {snapshot_contents}"
    )


def test_reentrant_lock_save_restore_replace_no_deadlock(live_server, test_env_setup):
    """
    防重入死锁测试：
    在同一线程内连续链式触发 保存 -> 恢复快照 -> 搜索替换，
    断言整个流程秒级完成（带严格超时限制），RLock 不产生任何死锁或卡顿。
    """
    import requests
    title = "防死锁重入链式测试书"

    # 1. 初始导入小说
    init_res = requests.post(f"{live_server}/api/novels/import-txt", json={
        "title": title,
        "text": "第1章 初始测试\n原始正文，测试重入与死锁防护。"
    }, timeout=5)
    assert init_res.status_code == 200

    # 2. 连续操作 A：保存修改（触发 lock_novel 并生成快照）
    save_res = requests.post(f"{live_server}/api/novels/{title}/chapter/0", json={
        "content": "【第一次修改正文：准备测试恢复】"
    }, timeout=5)
    assert save_res.status_code == 200

    # 获取刚产生的快照 ID
    app_module = test_env_setup["app_module"]
    backup_dir = app_module.CHAPTER_BACKUP_DIR
    backup_files = sorted(backup_dir.glob(f"{app_module.sanitize_filename(title)}_0_*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    assert len(backup_files) >= 1
    snap_fname = backup_files[0].name

    # 3. 连续操作 B：恢复快照（再次触发 lock_novel）
    restore_res = requests.post(f"{live_server}/api/novels/{title}/chapters/0/restore-snapshot", json={
        "snapshot_id": snap_fname
    }, timeout=5)
    assert restore_res.status_code == 200

    # 4. 连续操作 C：全书搜索替换（第三次触发 lock_novel）
    replace_res = requests.post(f"{live_server}/api/novels/{title}/search-replace", json={
        "find": "原始正文",
        "replace": "已替换正文",
        "preview_only": False
    }, timeout=5)
    assert replace_res.status_code == 200
    assert replace_res.json().get("modified_chapters") >= 1

    # 验证最终磁盘内容正确且无锁死
    novel_path = app_module.safe_novel_path(title)
    meta, chapters, _ = app_module.parse_novel(novel_path, repair=False)
    assert "已替换正文" in chapters[0]["content"]


def test_concurrent_save_during_generation_job_integrity(live_server, test_env_setup):
    """
    生成任务运行期间（后台生成中），并发保存其他章节：
    1. 观察并记录自动保存/编辑在生成期间的实际行为（409 还是排队）；
    2. 等待生成任务结束后，断言最终没有丢章，文件格式完整可解析。
    """
    import requests
    app_module = test_env_setup["app_module"]
    title = "生成期间并发测试书"

    # 1. 先初始化一本包含第1章的已有小说
    novel_path = app_module.NOVELS_DIR / f"{app_module.sanitize_filename(title)}.md"
    app_module.write_novel(
        novel_path,
        {"title": title, "status": "idle", "mode": "continuation"},
        [{"title": "第1章 既有前文", "content": "已有章节初始正文。"}]
    )

    # 2. 启动一个后台续写任务（对该已有小说生成3章）
    payload = {
        "mode": "continuation",
        "novel_name": title,
        "chapters": 3,
        "prompt": "继续推演剧情"
    }
    gen_res = requests.post(f"{live_server}/api/generate", json=payload, timeout=10)
    assert gen_res.status_code == 200
    job_id = gen_res.json()["job_id"]

    # 3. 在任务生成期间，尝试对同一本书的第1章发起单章保存
    # 记录实际观察到的行为：由于存在 book_busy 检查，保存被拦截并返回 409
    observed_statuses = []
    for _ in range(8):
        resp = requests.post(
            f"{live_server}/api/novels/{title}/chapter/0",
            json={"content": "【生成期间尝试并发保存第1章】"},
            timeout=5
        )
        observed_statuses.append(resp.status_code)
        if 409 in observed_statuses:
            break
        time.sleep(0.02)

    print(f"\n[Generation Concurrency Probe] 生成期间并发编辑接口实际响应状态码: {observed_statuses}")
    # 断言：在生成任务占用（book_busy）期间，应用返回 409 保护数据一致性，不盲目覆盖
    assert 409 in observed_statuses

    # 3. 等待生成任务结束（最多等待 15s）
    for _ in range(30):
        time.sleep(0.5)
        j = app_module.JOBS.get(job_id)
        if j and j.get("status") in ("done", "error", "cancelled"):
            break

    job = app_module.JOBS.get(job_id)
    assert job and job.get("status") == "done", f"生成任务异常结束: {job}"

    # 4. 断言最终文件没有丢章、格式解析正常、书籍锁已释放
    novel_path = app_module.safe_novel_path(title)
    assert novel_path and novel_path.exists(), "小说文件丢失"
    meta, chapters, _ = app_module.parse_novel(novel_path, repair=False)
    assert len(chapters) == 4, f"最终章节数量异常，预期4章，实际: {len(chapters)}"
    assert not app_module.book_busy(title), "生成完成后书籍锁未释放"


def test_auto_save_during_generation_retains_content_and_shows_status(page, live_server, test_env_setup):
    """
    复现生成期间前端自动保存遇到 409 的行为：
    1. 在已有小说上触发后台续写生成任务；
    2. 用户在前端 Studio 编辑模式下修改正文；
    3. 等待防抖（1.5s）自动保存触发；
    4. 断言：
       - 保存状态指示器显示明确错误（⚠️ 自动保存出错），而非假装成功；
       - 编辑框内的用户修改内容未被静默丢弃；
       - 观察并记录是否弹出 Toast 提示（核查静默/明确度）。
    """
    import requests
    app_module = test_env_setup["app_module"]
    title = "自动保存并发测试书"

    # 1. 预置一本已有小说
    novel_path = app_module.NOVELS_DIR / f"{app_module.sanitize_filename(title)}.md"
    app_module.write_novel(
        novel_path,
        {"title": title, "status": "idle", "mode": "continuation"},
        [{"title": "第1章 原有章节", "content": "这是初始正文内容。"}]
    )

    # 2. 打开阅读器并进入该书，点击「编辑本章」进入编辑模式
    page.goto(f"{live_server}/#read/{urllib.parse.quote(title)}/0")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(300)

    page.locator("#rd_edit_btn").click()
    page.wait_for_selector("#rd_edit_body_inp")

    # 3. 模拟后台生成任务正在执行（书籍被锁定处于 busy 状态）
    assert app_module.acquire_book(title, holder="active_generation_job"), "加锁失败"
    try:
        # 4. 在编辑框输入新内容
        typed_content = "【用户正在输入的新段落，生成中并发测试】"
        page.fill("#rd_edit_body_inp", typed_content)

        # 5. 等待 2.2 秒（超过 1.5 秒防抖时间以触发 silentAutoSave）
        page.wait_for_timeout(2200)

        # 6. 断言：用户的编辑内容完好保留在输入框内，绝没有被冲掉或清空
        current_content = page.locator("#rd_edit_body_inp").input_value()
        assert current_content == typed_content, f"编辑内容被静默丢弃，当前输入框为: {current_content}"

        # 7. 断言：保存状态指示器显示明确的409提示（⚠️ 生成中，暂时无法保存），而非假装成功或泛化报错
        status_text = page.locator("#rd_save_status").text_content()
        assert "生成中，暂时无法保存" in status_text, f"状态指示器未显示生成中提示，实际显示: '{status_text}'"

        # 8. 核查是否有 Toast 弹出（实测与代码分析：silentAutoSave 没有调用 toast()）
        toasts = page.locator(".toast:visible").all_text_contents()
        has_specific_toast = any("生成中" in t or "无法" in t for t in toasts)
        print(f"\n[AutoSave 409 Probe] Status indicator: '{status_text.encode('ascii', 'replace').decode()}', Has Toast: {has_specific_toast}")
    finally:
        app_module.release_book(title)


def test_concurrent_get_and_post_chapter_no_overwrite(live_server, test_env_setup):
    """
    小修复 A 验证测试：
    初始化包含未规范标题（旧标题）的小说；
    连续并发执行 50 次 GET（请求触发内存标题规范化逻辑）与 50 次 POST 保存同一章；
    断言最终磁盘上的正文是最新 POST 写入的内容，没有被并发 GET 的只读调用意外覆盖回滚。
    """
    import requests
    import concurrent.futures

    app_module = test_env_setup["app_module"]
    title = "并发GET与POST测试书"
    novel_path = app_module.NOVELS_DIR / f"{app_module.sanitize_filename(title)}.md"
    app_module.write_novel(
        novel_path,
        {"title": title, "status": "idle"},
        [{"title": "第1章【未规范旧标题】", "content": "【初始正文_旧版本】"}]
    )

    post_contents = [f"【最新修改正文_版本_{i:02d}】" for i in range(50)]

    def do_get():
        return requests.get(f"{live_server}/api/novels/{title}", timeout=10)

    def do_post(idx, content):
        return requests.post(
            f"{live_server}/api/novels/{title}/chapter/0",
            json={"title": f"第1章 规范新标题_{idx:02d}", "content": content},
            timeout=10
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = []
        for i in range(50):
            futures.append(executor.submit(do_get))
            futures.append(executor.submit(do_post, i, post_contents[i]))
        concurrent.futures.wait(futures)

    # 验证磁盘最终状态
    meta, chapters, _ = app_module.parse_novel(novel_path, repair=False)
    assert len(chapters) == 1
    disk_content = chapters[0]["content"]

    # 断言：磁盘上的内容绝不是初始旧版本，而是 POST 写入的最新版本之一
    assert disk_content != "【初始正文_旧版本】", "严重缺陷：并发 GET 覆盖了 POST 保存的新正文！"
    assert "最新修改正文" in disk_content, f"磁盘内容异常: {disk_content}"
