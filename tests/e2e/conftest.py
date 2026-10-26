"""
tests/e2e/conftest.py - E2E 测试环境固件 (Fixtures)

核心职责：
1. 启动本地假 LLM 服务 (FakeLLMServer)，零额度消耗与零外网依赖
2. 启动基于独立端口和独立【临时数据目录】的 Flask app 实例
3. 提供 Playwright Page / Context 固件，监听 console error、pageerror 与请求失败
4. 任何断言失败自动捕获高保真截图至 tests/e2e/artifacts/
"""

import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest
from werkzeug.serving import make_server

# 确保导入 tests.e2e 下的假 LLM
from tests.e2e.fake_llm_server import FakeLLMServer, FakeLLMState

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


def pytest_collection_modifyitems(config, items):
    """若当前环境未安装 playwright，则优雅跳过 E2E 测试用例，避免中断常规 pytest。"""
    try:
        import playwright  # noqa: F401
    except ImportError:
        skip_marker = pytest.mark.skip(reason="Playwright 尚未安装。请先确认安装依赖后再执行 E2E 测试。")
        for item in items:
            if "e2e" in str(item.fspath):
                item.add_marker(skip_marker)


def find_free_port():
    """动态获取一个未被占用的端口。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="session")
def fake_llm():
    """会话级本地假 LLM 服务。"""
    server = FakeLLMServer(port=0)
    server.start()
    yield server
    server.stop()


@pytest.fixture(scope="session")
def test_env_setup(fake_llm):
    """为 E2E 会话准备临时数据目录与专属 config.json。"""
    tmp_data_dir = tempfile.mkdtemp(prefix="novel_e2e_data_")
    novels_dir = Path(tmp_data_dir) / "novels"
    novels_dir.mkdir(parents=True, exist_ok=True)
    trash_dir = novels_dir / "_trash"
    trash_dir.mkdir(parents=True, exist_ok=True)
    (trash_dir / "chapters").mkdir(parents=True, exist_ok=True)

    # 预写入配置，将默认 provider 的 base_url 指向本地假 LLM
    config_data = {
        "providers": [
            {
                "id": "mock_llm",
                "name": "Local Mock LLM",
                "base_url": f"http://127.0.0.1:{fake_llm.port}",
                "api_key": "mock_test_key",
                "model": "mock-model",
                "temperature": 0.7,
            }
        ],
        "active_provider": "mock_llm",
        "web_auth": {},
        "privacy": {},
    }
    config_file = Path(tmp_data_dir) / "config.json"
    config_file.write_text(json.dumps(config_data, ensure_ascii=False, indent=2), encoding="utf-8")

    # 设置环境变量并重置 app 模块目录
    os.environ["NOVEL_DATA_DIR"] = tmp_data_dir
    os.environ["NOVEL_CONFIG_FILE"] = str(config_file)
    os.environ["NOVEL_NOVELS_DIR"] = str(novels_dir)

    import app as app_module
    app_module.DATA_DIR = Path(tmp_data_dir).resolve()
    app_module.NOVELS_DIR = novels_dir.resolve()
    app_module.CONFIG_FILE = config_file.resolve()
    app_module.TRASH_DIR = trash_dir.resolve()
    app_module.CHAPTER_BACKUP_DIR = (trash_dir / "chapters").resolve()

    yield {
        "data_dir": tmp_data_dir,
        "novels_dir": novels_dir,
        "config_file": config_file,
        "fake_llm_port": fake_llm.port,
        "app_module": app_module,
    }

    # 清理临时目录
    try:
        shutil.rmtree(tmp_data_dir)
    except Exception:
        pass


@pytest.fixture(scope="session")
def live_server(test_env_setup):
    """启动运行在独立端口上的 live HTTP 服务器。"""
    app_module = test_env_setup["app_module"]
    port = find_free_port()
    server = make_server("127.0.0.1", port, app_module.app, threaded=True)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    yield base_url

    try:
        t = threading.Thread(target=server.shutdown, daemon=True)
        t.start()
        t.join(timeout=2.0)
        server.server_close()
    except Exception:
        pass


@pytest.fixture(scope="session")
def playwright_instance():
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    yield pw
    pw.stop()


@pytest.fixture(scope="session")
def browser(playwright_instance):
    """使用方案 A：本机 Edge，不下载独立 Chromium。"""
    b = playwright_instance.chromium.launch(channel="msedge", headless=True)
    yield b
    b.close()


@pytest.fixture
def context(browser):
    ctx = browser.new_context()
    yield ctx
    ctx.close()


@pytest.fixture
def page(context):
    p = context.new_page()
    yield p
    p.close()


class PageMonitor:
    """监听页面控制台错误、未捕获 JS 异常与网络失败。"""
    def __init__(self, page, test_name=""):
        self.page = page
        self.test_name = test_name
        self.console_errors = []
        self.page_errors = []
        self.failed_requests = []

        page.on("console", self._handle_console)
        page.on("pageerror", self._handle_pageerror)
        page.on("requestfailed", self._handle_requestfailed)

    def _handle_console(self, msg):
        if msg.type in ("error", "warning"):
            # 过滤非致命的 favicon 404
            text = msg.text
            if "favicon.ico" not in text:
                self.console_errors.append(f"[{msg.type}] {text}")

    def _handle_pageerror(self, err):
        self.page_errors.append(str(err))

    def _handle_requestfailed(self, req):
        url = req.url
        if "favicon.ico" not in url:
            self.failed_requests.append(f"{req.method} {url} -> {req.failure}")

    def capture_screenshot(self, name_suffix=""):
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        safe_test = "".join([c if c.isalnum() or c in ("-", "_") else "_" for c in self.test_name])
        fname = f"{safe_test}_{name_suffix}_{timestamp}.png"
        path = ARTIFACTS_DIR / fname
        try:
            self.page.screenshot(path=str(path), full_page=True)
            return str(path)
        except Exception:
            return ""

    def assert_no_errors(self, step=""):
        if self.page_errors or self.console_errors or self.failed_requests:
            shot_path = self.capture_screenshot("error")
            err_details = []
            if self.page_errors:
                err_details.append(f"JS 异常: {'; '.join(self.page_errors)}")
            if self.console_errors:
                err_details.append(f"控制台错误: {'; '.join(self.console_errors)}")
            if self.failed_requests:
                err_details.append(f"请求失败: {'; '.join(self.failed_requests)}")
            msg = f"步骤「{step}」出现严重错误！{' | '.join(err_details)} (截图: {shot_path})"
            raise AssertionError(msg)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when == "call" and rep.failed:
        page = item.funcargs.get("page")
        if page:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            safe_node = "".join([c if c.isalnum() or c in ("-", "_") else "_" for c in item.name])
            path = ARTIFACTS_DIR / f"failure_{safe_node}_{timestamp}.png"
            try:
                page.screenshot(path=str(path), full_page=True)
            except Exception:
                pass
