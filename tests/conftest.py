# -*- coding: utf-8 -*-
"""全局 pytest 配置与测试环境隔离夹具 (Fixtures)

核心保障：
所有现有与未来新增测试均在隔离的临时目录下运行，绝不读写项目根目录的真实 novels/、config.json 和 analysis_cache/。
"""

import os
import tempfile
from pathlib import Path
import pytest

# 在任何测试用例导入 app 之前，优先把 NOVEL_DATA_DIR 指向系统临时目录
_SESSION_TMP = Path(tempfile.gettempdir()) / "novel_generator_pytest_session"
_SESSION_TMP.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("NOVEL_DATA_DIR", str(_SESSION_TMP))

import app  # noqa: E402


@pytest.fixture(autouse=True)
def isolate_test_data_dirs(tmp_path, monkeypatch, request):
    """每个测试独立使用专属的 tmp_path 临时数据目录，彻底隔离文件读写。
    
    注：E2E 端到端测试使用专属的会话级隔离夹具 test_env_setup 与本地假 LLM 服务，跳过单元级夹具。
    """
    if "e2e" in request.node.nodeid:
        yield
        return

    test_data = tmp_path / "test_data"
    test_novels = test_data / "novels"
    test_novels.mkdir(parents=True, exist_ok=True)
    test_cfg = test_data / "config.json"
    test_cache = test_data / "analysis_cache"
    test_cache.mkdir(parents=True, exist_ok=True)
    test_trash = test_novels / "_trash"
    test_backups = test_trash / "chapters"
    test_trash.mkdir(parents=True, exist_ok=True)
    test_backups.mkdir(parents=True, exist_ok=True)

    # 写入基础测试配置（避免文件不存在时读不到 provider）
    test_cfg.write_text(
        '{"providers": [{"id": "deepseek", "name": "DeepSeek", "base_url": "https://api.deepseek.com", "api_key": "sk-test", "model": "deepseek-chat", "temperature": 1.0}], "active_provider": "deepseek"}',
        encoding="utf-8",
    )

    monkeypatch.setenv("NOVEL_DATA_DIR", str(test_data))
    monkeypatch.setattr(app, "DATA_DIR", test_data)
    monkeypatch.setattr(app, "NOVELS_DIR", test_novels)
    monkeypatch.setattr(app, "CONFIG_FILE", test_cfg)
    monkeypatch.setattr(app, "CACHE_DIR", test_cache)
    monkeypatch.setattr(app, "TRASH_DIR", test_trash)
    monkeypatch.setattr(app, "CHAPTER_BACKUP_DIR", test_backups)

    # 如果 test_p3_studio 已加载，同步 monkeypatch 其局部引用的变量
    import sys
    if "tests.test_p3_studio" in sys.modules:
        m = sys.modules["tests.test_p3_studio"]
        monkeypatch.setattr(m, "NOVELS_DIR", test_novels, raising=False)
        monkeypatch.setattr(m, "CHAPTER_BACKUP_DIR", test_backups, raising=False)
    if "test_p3_studio" in sys.modules:
        m = sys.modules["test_p3_studio"]
        monkeypatch.setattr(m, "NOVELS_DIR", test_novels, raising=False)
        monkeypatch.setattr(m, "CHAPTER_BACKUP_DIR", test_backups, raising=False)

    yield {
        "data_dir": test_data,
        "novels_dir": test_novels,
        "config_file": test_cfg,
        "cache_dir": test_cache,
        "trash_dir": test_trash,
        "backups_dir": test_backups,
    }
