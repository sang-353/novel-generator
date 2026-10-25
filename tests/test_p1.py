# -*- coding: utf-8 -*-
"""P1 功能单元测试：EPUB 导出与划词 AI 辅助精修"""
import io
import json
import zipfile
import pytest

from app import app, generate_epub, write_novel


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


def test_generate_epub_structure():
    title = "测试书名"
    author = "测试作者"
    intro = "测试小说简介"
    chapters = [
        {"title": "第一章 启程", "content": "这是第一章正文内容。\n\n风从海面上吹来。"},
        {"title": "第二章 风暴", "content": "天色暗了下来。\n雷声滚滚。"}
    ]
    meta = {"words": 200, "status": "done"}

    data = generate_epub(title, author, intro, chapters, meta=meta)
    assert isinstance(data, bytes)
    assert len(data) > 1000

    with zipfile.ZipFile(io.BytesIO(data), "r") as z:
        names = z.namelist()
        assert names[0] == "mimetype"
        assert z.read("mimetype") == b"application/epub+zip"
        assert "META-INF/container.xml" in names
        assert "OEBPS/content.opf" in names
        assert "OEBPS/toc.ncx" in names
        assert "OEBPS/nav.xhtml" in names
        assert "OEBPS/cover.xhtml" in names
        assert "OEBPS/chapter_0.xhtml" in names
        assert "OEBPS/chapter_1.xhtml" in names

        # 检查封面和正文包含关键文本
        cover_text = z.read("OEBPS/cover.xhtml").decode("utf-8")
        assert "测试书名" in cover_text
        assert "测试作者" in cover_text
        assert "测试小说简介" in cover_text

        ch1_text = z.read("OEBPS/chapter_0.xhtml").decode("utf-8")
        assert "第一章 启程" in ch1_text
        assert "这是第一章正文内容。" in ch1_text


def test_export_epub_api(client, tmp_path):
    novels_dir = tmp_path / "novels"
    book_file = novels_dir / "导出测试.md"
    meta = {"title": "导出测试", "type": "original", "status": "done", "words": 150}
    chapters = [
        {"title": "第1章 诞生", "content": "故事从此展开。"}
    ]
    write_novel(book_file, meta, chapters)

    res = client.get("/api/novels/导出测试/export?fmt=epub")
    assert res.status_code == 200
    assert "application/epub+zip" in res.content_type
    assert "attachment" in res.headers.get("Content-Disposition", "")
    assert len(res.data) > 500

    with zipfile.ZipFile(io.BytesIO(res.data), "r") as z:
        assert "OEBPS/chapter_0.xhtml" in z.namelist()


def test_selection_assist_api(client, tmp_path, monkeypatch):
    novels_dir = tmp_path / "novels"
    book_file = novels_dir / "精修测试.md"
    meta = {"title": "精修测试", "type": "original", "status": "done"}
    chapters = [{"title": "第1章", "content": "周默坐在咖啡馆里，看着窗外的大雨。"}]
    write_novel(book_file, meta, chapters)

    # Mock chat
    def mock_chat(messages, max_tokens=1500, temperature=0.7, provider_id=None):
        return ("周默倚靠在咖啡馆深色的皮质卡座里，指尖摩挲着微凉的骨瓷杯沿，注视着暴雨如瀑般冲刷着玻璃窗。", "stop")

    monkeypatch.setattr("app.chat", mock_chat)

    # 1. 正常扩写请求
    payload = {
        "selected_text": "周默坐在咖啡馆里，看着窗外的大雨。",
        "instruction_type": "expand",
        "context_before": "下午三点。",
        "context_after": "服务生送来了一杯热柠檬水。"
    }
    res = client.post("/api/novels/精修测试/selection-assist", json=payload)
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert "骨瓷杯沿" in data["result"]
    assert data["original"] == payload["selected_text"]

    # 2. 空文本校验
    res_empty = client.post("/api/novels/精修测试/selection-assist", json={"selected_text": ""})
    assert res_empty.status_code == 400

    # 3. 超长文本校验 (> 4000)
    res_long = client.post("/api/novels/精修测试/selection-assist", json={"selected_text": "字" * 4001})
    assert res_long.status_code == 400
