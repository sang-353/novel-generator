# -*- coding: utf-8 -*-
"""P0 功能单元测试：就地编辑单章、生成流式状态与任务中断"""
import json
import shutil
import tempfile
import time
from pathlib import Path

import pytest

from app import (
    JOBS,
    JOBS_LOCK,
    NOVELS_DIR,
    acquire_book,
    app,
    new_job,
    parse_novel,
    release_book,
    update_job,
    write_novel,
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    test_novels = tmp_path / "novels"
    test_novels.mkdir()
    monkeypatch.setattr("app.NOVELS_DIR", test_novels)
    monkeypatch.setattr("app.TRASH_DIR", test_novels / "_trash")
    monkeypatch.setattr("app.CHAPTER_BACKUP_DIR", test_novels / "_trash" / "chapters")
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_edit_chapter_success(client, tmp_path):
    # 建立一本书
    novels_dir = tmp_path / "novels"
    book_file = novels_dir / "测试小说.md"
    meta = {"title": "测试小说", "type": "original", "status": "done", "words": 100}
    chapters = [
        {"title": "第一章 初始", "content": "这是第一章初始内容。"},
        {"title": "第二章 初始", "content": "这是第二章初始内容。"},
    ]
    write_novel(book_file, meta, chapters)

    # 1. 成功修改第二章正文与标题
    res = client.post("/api/novels/测试小说/chapter/1", json={
        "title": "第二章 修改后标题",
        "content": "这是全新编写的第二章内容，字数变多了！"
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert data["index"] == 1
    assert data["title"] == "第二章 修改后标题"
    assert "全新编写" in data["content"]

    # 验证磁盘持久化结果
    m2, ch2, w2 = parse_novel(book_file)
    assert ch2[1]["title"] == "第二章 修改后标题"
    assert ch2[1]["content"] == "这是全新编写的第二章内容，字数变多了！"

    # 验证是否自动备份了快照
    backup_dir = tmp_path / "novels" / "_trash" / "chapters"
    backups = list(backup_dir.glob("*.json"))
    assert len(backups) == 1
    snap = json.loads(backups[0].read_text(encoding="utf-8"))
    assert snap["title"] == "第二章 初始"
    assert snap["content"] == "这是第二章初始内容。"


def test_edit_chapter_errors(client, tmp_path):
    novels_dir = tmp_path / "novels"
    book_file = novels_dir / "测试小说.md"
    write_novel(book_file, {"title": "测试小说"}, [{"title": "第1章", "content": "正文"}])

    # 1. 章节下标越界
    r404 = client.post("/api/novels/测试小说/chapter/5", json={"content": "新正文"})
    assert r404.status_code == 404

    # 2. 书籍不存在
    r_no_book = client.post("/api/novels/不存在的书/chapter/0", json={"content": "新正文"})
    assert r_no_book.status_code == 404

    # 3. 正文为空 (content is None)
    r_empty = client.post("/api/novels/测试小说/chapter/0", json={})
    assert r_empty.status_code == 400

    # 4. 书籍正在生成中 (busy 保护)
    acquire_book("测试小说")
    try:
        r_busy = client.post("/api/novels/测试小说/chapter/0", json={"content": "尝试修改"})
        assert r_busy.status_code == 409
    finally:
        release_book("测试小说")


def test_job_streaming_text(client):
    job = new_job("original", 3, "流式测试书")
    assert job["streaming_text"] == ""

    update_job(job, streaming_text="第一段流式文字")
    res = client.get(f"/api/jobs/{job['id']}")
    assert res.status_code == 200
    assert res.get_json()["streaming_text"] == "第一段流式文字"


def test_job_stream_sse_endpoint(client):
    job = new_job("original", 1, "SSE测试")
    update_job(job, streaming_text="流式输出内容", status="done")

    res = client.get(f"/api/jobs/{job['id']}/stream")
    assert res.status_code == 200
    assert "text/event-stream" in res.content_type
    data = res.get_data(as_text=True)
    assert "流式输出内容" in data
    assert '"status": "done"' in data


def test_extract_json_resilience():
    from app import extract_json

    # 1. 常见 Markdown 包裹
    t1 = '```json\n{"文风": "幽默", "视角": "第一人称"}\n```'
    assert extract_json(t1) == {"文风": "幽默", "视角": "第一人称"}

    # 2. 中文弯引号与中文逗号
    t2 = '{"文风"：“悬疑”，"叙事视角"：“第三人称”}'
    res2 = extract_json(t2)
    assert res2["文风"] == "悬疑"
    assert res2["叙事视角"] == "第三人称"

    # 3. 截断未闭合的双引号与大括号/方括号
    t3 = '{"文风": "科幻硬核", "人物表": [{"姓名": "陈博士", "身份": "物理学家"'
    res3 = extract_json(t3)
    assert res3.get("文风") == "科幻硬核"

    # 4. 尾随逗号与乱入文字
    t4 = '以下是创作档案：\n{"文风": "治愈", "人物表": ["小明", "小红", ], }\n希望对你有帮助！'
    res4 = extract_json(t4)
    assert res4["文风"] == "治愈"


def test_continuation_fallback_on_original_book(tmp_path, monkeypatch):
    from app import run_continuation_job

    test_novels = tmp_path / "novels"
    test_novels.mkdir()
    monkeypatch.setattr("app.NOVELS_DIR", test_novels)

    book_file = test_novels / "幽居测试.md"
    meta = {
        "title": "幽居测试",
        "type": "original",
        "status": "done",
        "job_payload": {
            "style": "悬疑风格，幽默风趣",
            "perspective": "第三人称",
            "bible": {"tone": "悬疑幽默", "characters": [{"name": "周默"}]}
        }
    }
    chapters = [{"title": "第1章 遇险", "content": "周默在雨夜前行。"}]
    write_novel(book_file, meta, chapters)

    # 模拟 analyze_style 抛出异常（例如 LLM 返回畸变文本或超长）
    def mock_analyze_fail(*args, **kwargs):
        raise RuntimeError("模型返回的不是有效 JSON")

    # 模拟 generate_text 正常生成新章节
    def mock_generate_text(mk_msgs, max_chars, provider_id=None, on_chunk=None):
        if on_chunk:
            on_chunk("第2章 续写正文。")
        return "第2章 迷局\n\n这是续写的正文内容。"

    monkeypatch.setattr("app.analyze_style", mock_analyze_fail)
    monkeypatch.setattr("app.generate_text", mock_generate_text)

    job = new_job("continuation", 1, "幽居测试")
    payload = {
        "novel_name": "幽居测试",
        "mode": "continuation",
        "instruction": "接续探案",
        "chapters": 1,
        "per_chapter_words": 1000,
    }

    # 执行续写任务
    run_continuation_job(job, payload)

    assert job["status"] == "done"
    # 验证档案成功回退并持久化
    m_after, ch_after, _ = parse_novel(book_file)
    assert len(ch_after) == 2
    assert "style_profile" in m_after
    assert m_after["style_profile"]["文风"] == "悬疑幽默"
    assert m_after["style_profile"]["人物表"] == [{"name": "周默"}]


