# -*- coding: utf-8 -*-
"""测试隔离证明测试 (Task A.3)

证明所有测试均在隔离的临时目录运行，绝不读写项目根目录下真实的数据：
- 真实的 novels/
- 真实的 config.json
- 真实的 analysis_cache/
"""

import os
from pathlib import Path
import app


def test_isolation_guarantee():
    """证明测试运行时的数据目录与项目真实数据目录完全隔离。"""
    project_root = Path(__file__).resolve().parent.parent
    real_novels_dir = (project_root / "novels").resolve()
    real_config_file = (project_root / "config.json").resolve()
    real_cache_dir = (project_root / "analysis_cache").resolve()

    # 1. 断言当前运行时路径绝不是项目真实路径
    current_novels = Path(app.NOVELS_DIR).resolve()
    current_config = Path(app.CONFIG_FILE).resolve()
    current_cache = Path(app.CACHE_DIR).resolve()

    assert current_novels != real_novels_dir, f"app.NOVELS_DIR 仍指向真实目录: {current_novels}"
    assert current_config != real_config_file, f"app.CONFIG_FILE 仍指向真实配置: {current_config}"
    assert current_cache != real_cache_dir, f"app.CACHE_DIR 仍指向真实缓存: {current_cache}"

    # 2. 记录真实目录与配置的初始快照（时间戳与内容）
    real_config_content = real_config_file.read_bytes() if real_config_file.exists() else None
    real_novels_snapshot = {
        f.name: (f.stat().st_mtime, f.stat().st_size)
        for f in real_novels_dir.glob("*.md")
    } if real_novels_dir.exists() else {}

    # 3. 在测试环境中执行写操作（创建小说、保存配置、写入章节）
    test_book = "isolation_proof_novel"
    test_p = app.NOVELS_DIR / f"{test_book}.md"
    app.write_novel(test_p, {"title": "隔离证明小说", "type": "original"}, [
        {"title": "第一章", "content": "这绝不能写入真实的 novels 目录。"}
    ])
    app.save_config({"providers": [{"id": "isolated_test_id"}], "active_provider": "isolated_test_id"})

    # 4. 断言写入成功且落在临时隔离区
    assert test_p.exists()
    assert (app.CONFIG_FILE).exists()
    saved_cfg = app.load_config()
    assert saved_cfg.get("active_provider") == "isolated_test_id"

    # 5. 核心铁证：真实目录完全未受任何影响
    if real_config_file.exists():
        assert real_config_file.read_bytes() == real_config_content, "真实 config.json 被测试篡改！"

    if real_novels_dir.exists():
        current_real_snapshot = {
            f.name: (f.stat().st_mtime, f.stat().st_size)
            for f in real_novels_dir.glob("*.md")
        }
        assert current_real_snapshot == real_novels_snapshot, "真实 novels/ 目录被测试写入或修改！"
        assert not (real_novels_dir / f"{test_book}.md").exists(), "测试小说泄漏到了真实 novels/ 目录！"
