# -*- coding: utf-8 -*-
"""app.py 纯逻辑单元测试（不联网）"""
import json
import os
import shutil
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import (  # noqa: E402
    chapter_number_from,
    chapter_title_from,
    chunk_text,
    extract_json,
    get_provider,
    max_chapter_number,
    maybe_rollup_summary,
    parse_novel,
    repair_chapter_title,
    sanitize_filename,
    select_sampled_chunks,
    unique_path,
    write_novel,
)


def _tmp_base():
    """测试临时根目录：优先系统临时区（沙箱下可建目录），失败回退工作区 .tmp。"""
    candidates = [
        Path(tempfile.gettempdir()) / "novel-generator-tests",
        Path(__file__).resolve().parent.parent / ".tmp" / "pytest-data",
    ]
    for base in candidates:
        try:
            base.mkdir(parents=True, exist_ok=True)
            probe = base / f".probe-{uuid.uuid4().hex[:6]}"
            probe.mkdir()
            probe.rmdir()
            return base
        except Exception:
            continue
    return candidates[-1]


@pytest.fixture
def tmpdir():
    """沙箱环境下 pytest 内置 tmp_path 不可用，改用可写的临时目录。"""
    d = _tmp_base() / uuid.uuid4().hex[:12]
    d.mkdir(parents=True, exist_ok=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


def test_sanitize_filename():
    assert sanitize_filename('a/b\\c:d*e?f"g<h>i|j') == "a_b_c_d_e_f_g_h_i_j"
    assert sanitize_filename("   ") == "未命名小说"
    assert len(sanitize_filename("x" * 200)) <= 60


def test_unique_path(tmpdir, monkeypatch):
    monkeypatch.setattr("app.NOVELS_DIR", tmpdir)
    p1 = unique_path("测试书")
    assert p1.name == "测试书.md"
    p1.write_text("x", encoding="utf-8")
    p2 = unique_path("测试书")
    assert p2.name == "测试书(2).md"


def test_extract_json():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('前面有废话 {"a": 1} 后面也有') == {"a": 1}


def test_chapter_title_from():
    title, body = chapter_title_from("第3章 相遇\n\n山间的风很冷。", 3)
    assert title == "第3章 相遇"
    assert body == "山间的风很冷。"
    title2, body2 = chapter_title_from("这里没有标题行，直接是正文。", 2)
    assert title2 == "第2章"
    assert body2 == "这里没有标题行，直接是正文。"


def test_write_and_parse_novel_roundtrip(tmpdir):
    path = tmpdir / "书.md"
    meta = {"title": "测试书", "type": "original", "status": "done"}
    chapters = [
        {"title": "第1章 开端", "content": "这是第一章内容。"},
        {"title": "第2章 发展", "content": "这是第二章内容，稍长一些。"},
    ]
    write_novel(path, meta, chapters)
    meta2, chapters2, words = parse_novel(path)
    assert meta2["title"] == "测试书"
    assert meta2["status"] == "done"
    assert meta2["updated"]
    assert [c["title"] for c in chapters2] == ["第1章 开端", "第2章 发展"]
    assert chapters2[0]["content"] == "这是第一章内容。"
    assert words == 21  # 去掉空白后的字符数


def test_parse_novel_without_front_matter(tmpdir):
    path = tmpdir / "plain.md"
    path.write_text("# 标题一\n\n正文一\n\n# 标题二\n\n正文二\n", encoding="utf-8")
    meta, chapters, _ = parse_novel(path)
    assert meta.get("title") == "plain"
    assert len(chapters) == 2
    assert chapters[0]["title"] == "标题一"


def test_chunk_text():
    assert chunk_text("短文本") == ["短文本"]
    text = "字" * 10000
    chunks = chunk_text(text, chunk_size=4000, overlap=500)
    assert len(chunks) == 3
    assert chunks[0][-500:] == chunks[1][:500]  # 重叠
    assert "".join(chunks).count("字") == len(text) + 500 * (len(chunks) - 1)  # 重叠部分重复计入


def test_original_chapter_heading_escaped(tmpdir):
    """原文含 # 标题行时写入原作章节，不应被解析为多个章节。"""
    path = tmpdir / "书.md"
    meta = {"title": "测试", "type": "continuation", "original_count": 1}
    source = "开头文字\n# 原书章节标题\n正文内容"
    orig_body = __import__("re").sub(r"^#\s+", "## ", source.strip(), flags=__import__("re").M)
    chapters = [{"title": "原作", "content": orig_body},
                {"title": "第1章 续写", "content": "续写正文"}]
    write_novel(path, meta, chapters)
    meta2, chapters2, _ = parse_novel(path)
    assert len(chapters2) == 2
    assert chapters2[0]["title"] == "原作"
    assert "## 原书章节标题" in chapters2[0]["content"]


def test_continuation_meta_roundtrip(tmpdir):
    """追加续写后：meta 保留 style_profile/instructions/original_count/rounds。"""
    path = tmpdir / "书.md"
    meta = {
        "title": "原作·续写", "type": "continuation", "status": "done",
        "style_profile": {"文风": "细腻"},
        "instructions": ["第一轮指示"],
        "original_count": 1,
        "rounds": [{"start": 1, "end": 1, "instruction": "第一轮指示", "ts": "t"}],
        "story_summary": "", "summary_upto": 0,
    }
    chapters = [
        {"title": "原作", "content": "原文"},
        {"title": "第1章 风起", "content": "续写一"},
    ]
    write_novel(path, meta, chapters)
    # 模拟追加一轮
    meta2, chapters2, _ = parse_novel(path)
    assert meta2["style_profile"]["文风"] == "细腻"
    assert meta2["instructions"] == ["第一轮指示"]
    assert meta2["original_count"] == 1
    meta2["instructions"].append("第二轮指示")
    meta2["rounds"].append({"start": 2, "end": 2, "instruction": "第二轮指示", "ts": "t2"})
    chapters2.append({"title": "第2章 云涌", "content": "续写二"})
    write_novel(path, meta2, chapters2)
    meta3, chapters3, _ = parse_novel(path)
    assert [c["title"] for c in chapters3] == ["原作", "第1章 风起", "第2章 云涌"]
    assert meta3["instructions"] == ["第一轮指示", "第二轮指示"]
    assert len(meta3["rounds"]) == 2


def test_rollup_threshold_logic(monkeypatch):
    """续写内容未超阈值时不触发摘要；超阈值且新增章节时尝试摘要（网络失败静默）。"""
    monkeypatch.setattr("app.ROLLUP_THRESHOLD", 100)  # 调低阈值便于测试
    # 未超阈值
    meta = {"original_count": 1, "story_summary": "", "summary_upto": 0}
    chapters = [{"title": "原作", "content": "x"},
                {"title": "第1章", "content": "短" * 10}]
    maybe_rollup_summary(meta, chapters)
    assert meta["story_summary"] == ""  # 未触发
    # 超阈值但无新增（summary_upto 已到末尾）——不调用网络
    meta2 = {"original_count": 1, "story_summary": "已有摘要", "summary_upto": 1}
    chapters2 = [{"title": "原作", "content": "x"},
                 {"title": "第1章", "content": "长" * 100}]
    maybe_rollup_summary(meta2, chapters2)
    assert meta2["summary_upto"] == 1  # 保持不变
    # 超阈值且有新增：chat 抛异常时应静默失败，不抛异常、不更新进度
    def boom(*a, **k):
        raise RuntimeError("模拟网络失败")
    monkeypatch.setattr("app.chat", boom)
    meta3 = {"original_count": 1, "story_summary": "", "summary_upto": 0}
    chapters3 = [{"title": "原作", "content": "x"},
                 {"title": "第1章", "content": "长" * 100},
                 {"title": "第2章", "content": "长" * 100}]
    maybe_rollup_summary(meta3, chapters3)  # 不应抛异常
    assert meta3["summary_upto"] == 0  # 失败则保持原状


def test_select_sampled_chunks():
    # 少量块全读
    assert select_sampled_chunks(3) == [0, 1, 2]
    assert select_sampled_chunks(4) == [0, 1, 2, 3]
    # 长文本：开头+结尾精读，中间抽样
    sel = select_sampled_chunks(30)
    assert 0 in sel and 29 in sel              # 首尾必读
    assert 1 in sel and 2 in sel and 3 in sel  # 开头 15% 精读
    assert len(sel) < 30                        # 有抽样
    assert len(set(sel)) == len(sel)            # 无重复
    # 抽样比例合理：约 15% + 10% + 中间 1/3 ≈ 40-45%
    assert 0.3 <= len(sel) / 30 <= 0.55


def test_analysis_cache_roundtrip(tmpdir, monkeypatch):
    monkeypatch.setattr("app.CACHE_DIR", tmpdir)
    key = app_cache_key("测试书", "原文内容")
    assert load_cached(key) is None
    save_cached(key, {"文风": "古风"})
    assert load_cached(key) == {"文风": "古风"}
    # 不同原文不同 key
    key2 = app_cache_key("测试书", "另一段原文")
    assert key2 != key


def app_cache_key(title, text):
    import app
    return app.analysis_cache_key(title, text)


def load_cached(key):
    import app
    return app.load_analysis_cache(key)


def save_cached(key, profile):
    import app
    app.save_analysis_cache(key, profile)


def test_legacy_config_migration(tmpdir, monkeypatch):
    """旧版单配置 config.json 自动迁移为 providers 数组。"""
    import app
    cfg_path = tmpdir / "config.json"
    cfg_path.write_text(json.dumps({
        "api_key": "sk-legacy",
        "model": "deepseek-chat",
        "temperature": 0.9,
        "base_url": "https://api.deepseek.com",
    }), encoding="utf-8")
    monkeypatch.setattr(app, "CONFIG_FILE", cfg_path)
    cfg = app.load_config()
    assert isinstance(cfg.get("providers"), list)
    assert cfg["providers"][0]["api_key"] == "sk-legacy"
    assert cfg["providers"][0]["model"] == "deepseek-chat"
    assert cfg["active_provider"] == cfg["providers"][0]["id"]


def test_get_provider(tmpdir, monkeypatch):
    """按 id 取 provider；缺省取默认；不存在的 id 回退第一个。"""
    import app
    cfg_path = tmpdir / "config.json"
    cfg_path.write_text(json.dumps({
        "providers": [
            {"id": "a", "name": "A", "base_url": "u1", "api_key": "k1", "model": "m1", "temperature": 1.0},
            {"id": "b", "name": "B", "base_url": "u2", "api_key": "k2", "model": "m2", "temperature": 0.5},
        ],
        "active_provider": "b",
    }), encoding="utf-8")
    monkeypatch.setattr(app, "CONFIG_FILE", cfg_path)
    assert get_provider("a")["name"] == "A"
    assert get_provider("b")["name"] == "B"
    assert get_provider()["name"] == "B"           # 默认
    assert get_provider("zzz")["name"] == "B"      # 不存在 -> 默认
    # 无默认 provider 时回退第一个
    cfg_path.write_text(json.dumps({
        "providers": [{"id": "a", "name": "A", "base_url": "u1", "api_key": "k1", "model": "m1", "temperature": 1.0}],
        "active_provider": "gone",
    }), encoding="utf-8")
    assert get_provider()["name"] == "A"


def test_chapter_numbering():
    assert chapter_number_from("第5章 相遇") == 5
    assert chapter_number_from("第12回 风云") == 12
    assert chapter_number_from("原作") is None
    assert chapter_number_from("无编号标题") is None
    chapters = [
        {"title": "原作", "content": "x"},
        {"title": "第1章 甲", "content": "x"},
        {"title": "第3章 丙", "content": "x"},  # 删除中间章后的空洞
    ]
    assert max_chapter_number(chapters, original_count=1) == 3
    assert max_chapter_number(chapters, original_count=1) + 1 == 4  # 续写接续编号
    assert max_chapter_number([{"title": "原作", "content": "x"}], original_count=1) == 0


def test_chapter_title_from_bracket_formats():
    """带【】括号的标题行应被正确提取，而不是丢进正文。"""
    title, body = chapter_title_from("【第58章 风雪夜归人】\n\n正文内容……", 58)
    assert title == "第58章 风雪夜归人"
    assert body == "正文内容……"
    title2, body2 = chapter_title_from("# 第3章 湖畔\n\n正文", 3)
    assert title2 == "第3章 湖畔"
    assert body2 == "正文"
    title3, _ = chapter_title_from("第7章：抉择\n\n正文", 7)
    assert title3 == "第7章 抉择"
    title4, _ = chapter_title_from("【第1章 开端】", 1)
    assert title4 == "第1章 开端"
    # 无标题行时兜底
    t5, b5 = chapter_title_from("直接是正文内容。", 9)
    assert t5 == "第9章"
    assert b5 == "直接是正文内容。"


def test_repair_chapter_title():
    """存量数据：标题为纯编号但正文首行是完整标题时，提取回目录。"""
    ch = {"title": "第58章", "content": "【第58章 风雪夜归人】\n\n正文内容……"}
    repair_chapter_title(ch)
    assert ch["title"] == "第58章 风雪夜归人"
    assert ch["content"] == "正文内容……"
    # 编号不一致时不动
    ch2 = {"title": "第58章", "content": "【第59章 别的标题】\n\n正文"}
    repair_chapter_title(ch2)
    assert ch2["title"] == "第58章"
    # 已有副标题不动
    ch3 = {"title": "第58章 已有标题", "content": "【第58章 风雪夜归人】\n\n正文"}
    repair_chapter_title(ch3)
    assert ch3["title"] == "第58章 已有标题"
    # 无编号章节（原作）不动
    ch4 = {"title": "原作", "content": "正文内容"}
    repair_chapter_title(ch4)
    assert ch4["title"] == "原作"


def test_split_source_paragraphs():
    import app
    # 空行分段优先
    paras = app.split_source_paragraphs("第一段。\n\n第二段。\n\n第三段。")
    assert paras == ["第一段。", "第二段。", "第三段。"]
    # 单换行分段（网文常见）退化为按行
    paras2 = app.split_source_paragraphs("第一行。\n第二行。\n第三行。")
    assert len(paras2) == 3
    # 混合：空行分段结果 >1 时按空行
    paras3 = app.split_source_paragraphs("甲。\n乙。\n\n丙。")
    assert len(paras3) == 2
    # 空文本
    assert app.split_source_paragraphs("") == []


def test_read_meta_only(tmpdir):
    import app
    p = tmpdir / "书.md"
    p.write_text('---\n{"title": "测试", "status": "done"}\n---\n# 第1章\n正文', encoding="utf-8")
    assert app.read_meta_only(p) == {"title": "测试", "status": "done"}
    p2 = tmpdir / "plain.md"
    p2.write_text("# 没有 front matter\n正文", encoding="utf-8")
    assert app.read_meta_only(p2) == {}


def test_find_existing_profile(tmpdir, monkeypatch):
    import app
    monkeypatch.setattr(app, "NOVELS_DIR", tmpdir)
    p = tmpdir / "三体·续写.md"
    p.write_text('---\n{"title": "三体·续写", "style_profile": {"文风": "硬核"}}\n---\n# 第1章\n正文', encoding="utf-8")
    prof = app.find_existing_profile("三体")
    assert prof and prof["文风"] == "硬核"
    assert app.find_existing_profile("不存在的书") is None


def test_backup_and_load_chapter(tmpdir, monkeypatch):
    import app
    monkeypatch.setattr(app, "NOVELS_DIR", tmpdir)
    monkeypatch.setattr(app, "TRASH_DIR", tmpdir / "_trash")
    monkeypatch.setattr(app, "CHAPTER_BACKUP_DIR", tmpdir / "_trash" / "chapters")
    fname = app._backup_chapter("测试书", 2, {"title": "第3章 旧版", "content": "旧内容"})
    assert fname
    snap = app.load_chapter_backup(fname)
    assert snap["novel"] == "测试书"
    assert snap["index"] == 2
    assert snap["title"] == "第3章 旧版"
    # 路径穿越防护
    assert app.load_chapter_backup("../../etc/passwd") is None


def test_acquire_release_book():
    import app
    assert app.acquire_book("书A")
    assert not app.acquire_book("书A")   # 同书并发被拒
    assert app.book_busy("书A")
    app.release_book("书A")
    assert app.acquire_book("书A")       # 释放后可再次获取


def test_delete_novel_moves_to_trash_and_restore(monkeypatch, tmpdir):
    """删除整本 -> 移入回收站 -> 可恢复；彻底删除 -> 不可恢复。"""
    import app
    monkeypatch.setattr(app, "NOVELS_DIR", tmpdir)
    monkeypatch.setattr(app, "TRASH_DIR", tmpdir / "_trash")
    monkeypatch.setattr(app, "CHAPTER_BACKUP_DIR", tmpdir / "_trash" / "chapters")
    p = tmpdir / "测试书.md"
    write_novel(p, {"title": "测试书", "type": "original", "status": "done"},
                [{"title": "第1章", "content": "正文"}])
    client = app.app.test_client()
    r = client.delete("/api/novels/测试书")
    assert r.status_code == 200
    assert not p.exists()                       # 原位置已无文件
    assert (tmpdir / "_trash" / "测试书.md").exists()  # 进了回收站
    # 列表接口不再包含该书，但回收站列表有
    assert client.get("/api/novels").get_json() == []
    trash = client.get("/api/trash").get_json()
    assert len(trash) == 1 and trash[0]["file"] == "测试书.md"
    # 恢复
    r2 = client.post("/api/trash/测试书/restore")
    assert r2.status_code == 200
    assert p.exists()
    # 再删除并彻底清除
    client.delete("/api/novels/测试书")
    r3 = client.delete("/api/trash/测试书")
    assert r3.status_code == 200
    assert client.get("/api/trash").get_json() == []


def test_cancel_job_api():
    import app
    job = app.new_job("original", 10)
    client = app.app.test_client()
    r = client.post(f"/api/jobs/{job['id']}/cancel")
    assert r.status_code == 200
    assert job["cancel"] is True
    # 已结束任务不可取消
    app.update_job(job, status="done")
    r2 = client.post(f"/api/jobs/{job['id']}/cancel")
    assert r2.status_code == 400


def test_search_novel(monkeypatch, tmpdir):
    import app
    monkeypatch.setattr(app, "NOVELS_DIR", tmpdir)
    p = tmpdir / "书.md"
    write_novel(p, {"title": "书"}, [
        {"title": "第1章", "content": "春天来了，花开满园。"},
        {"title": "第2章", "content": "冬天很长，雪一直下。"},
    ])
    client = app.app.test_client()
    r = client.get("/api/novels/书/search?q=雪")
    data = r.get_json()
    assert len(data["results"]) == 1
    assert data["results"][0]["index"] == 1
    assert "雪一直下" in data["results"][0]["snippet"]
    r2 = client.get("/api/novels/书/search?q=不存在词")
    assert r2.get_json()["results"] == []


# ---------------------------------------------------------------------------
# 隐私书架
# ---------------------------------------------------------------------------
def test_password_hash_and_verify():
    import app
    rec = app.hash_password("my-secret")
    assert rec["hash"] != "my-secret"          # 不存明文
    assert len(rec["salt"]) == 32
    assert app.verify_password("my-secret", rec)
    assert not app.verify_password("wrong", rec)
    assert not app.verify_password("my-secret", None)
    # 同一密码两次加盐结果不同
    rec2 = app.hash_password("my-secret")
    assert rec2["hash"] != rec["hash"]


def _privacy_env(monkeypatch, tmpdir):
    import app
    monkeypatch.setattr(app, "NOVELS_DIR", tmpdir)
    monkeypatch.setattr(app, "TRASH_DIR", tmpdir / "_trash")
    monkeypatch.setattr(app, "CHAPTER_BACKUP_DIR", tmpdir / "_trash" / "chapters")
    monkeypatch.setattr(app, "CONFIG_FILE", tmpdir / "config.json")
    with app.PRIVACY_LOCK:
        app.PRIVACY_TOKENS.clear()
    return app.app.test_client()


def test_privacy_set_change_and_unlock(monkeypatch, tmpdir):
    client = _privacy_env(monkeypatch, tmpdir)
    assert client.get("/api/privacy").get_json()["enabled"] is False
    # 不设密码时不能解锁
    assert client.post("/api/privacy/unlock", json={"password": "x"}).status_code == 400
    # 首次设置
    assert client.post("/api/privacy/set", json={"new_password": "abcd"}).status_code == 200
    assert client.get("/api/privacy").get_json()["enabled"] is True
    # 太短的新密码被拒
    assert client.post("/api/privacy/set", json={"old_password": "abcd", "new_password": "1"}).status_code == 400
    # 旧密码错误
    assert client.post("/api/privacy/set", json={"old_password": "nope", "new_password": "efgh"}).status_code == 403
    # 解锁
    assert client.post("/api/privacy/unlock", json={"password": "wrong"}).status_code == 403
    tok = client.post("/api/privacy/unlock", json={"password": "abcd"}).get_json()["token"]
    # 改密码后旧令牌失效、新密码可解锁
    assert client.post("/api/privacy/set", json={"old_password": "abcd", "new_password": "efgh"}).status_code == 200
    assert client.post("/api/privacy/lock?token=" + tok).status_code == 200
    assert client.post("/api/privacy/unlock", json={"password": "abcd"}).status_code == 403
    assert client.post("/api/privacy/unlock", json={"password": "efgh"}).status_code == 200


def test_private_shelf_flow(monkeypatch, tmpdir):
    client = _privacy_env(monkeypatch, tmpdir)
    p = tmpdir / "私密书.md"
    write_novel(p, {"title": "私密书", "type": "original", "status": "done"},
                [{"title": "第1章", "content": "秘密的正文"}])

    # 未设置密码时不允许设为隐私
    assert client.post("/api/novels/私密书/privacy", json={"private": True}).status_code == 400

    client.post("/api/privacy/set", json={"new_password": "pw1234"})
    tok = client.post("/api/privacy/unlock", json={"password": "pw1234"}).get_json()["token"]

    # 设为隐私
    r = client.post(f"/api/novels/私密书/privacy?token={tok}", json={"private": True})
    assert r.status_code == 200 and r.get_json()["private"] is True

    # 普通书架不再列出；隐私书架需令牌
    assert client.get("/api/novels").get_json() == []
    assert client.get("/api/novels/private").status_code == 403
    assert client.get(f"/api/novels/private?token={tok}").status_code == 200
    assert len(client.get(f"/api/novels/private?token={tok}").get_json()) == 1

    # 读取 / 搜索 / 导出 / 删除章节 / 删除整本：无令牌一律 403
    assert client.get("/api/novels/私密书").status_code == 403
    assert client.get("/api/novels/私密书?token=" + tok).status_code == 200
    assert client.get("/api/novels/私密书/search?q=秘密").status_code == 403
    assert client.get("/api/novels/私密书/search?q=秘密&token=" + tok).status_code == 200
    assert client.get("/api/novels/私密书/export?fmt=txt").status_code == 403
    assert client.get("/api/novels/私密书/export?fmt=txt&token=" + tok).status_code == 200
    assert client.post("/api/novels/私密书/chapters/delete", json={"index": 0}).status_code == 403
    assert client.delete("/api/novels/私密书").status_code == 403

    # 无效令牌同样被拒
    assert client.get("/api/novels/私密书?token=bogus").status_code == 403

    # 移出隐私书架后回到普通书架
    assert client.post(f"/api/novels/私密书/privacy?token={tok}", json={"private": False}).status_code == 200
    assert len(client.get("/api/novels").get_json()) == 1
    assert client.get(f"/api/novels/private?token={tok}").get_json() == []


def test_trash_and_backup_mask_private_titles(monkeypatch, tmpdir):
    client = _privacy_env(monkeypatch, tmpdir)
    p = tmpdir / "私密书.md"
    write_novel(p, {"title": "私密书", "type": "original", "status": "done", "private": True},
                [{"title": "第1章", "content": "秘密"}])
    client.post("/api/privacy/set", json={"new_password": "pw1234"})
    tok = client.post("/api/privacy/unlock", json={"password": "pw1234"}).get_json()["token"]

    # 移入回收站后：无令牌时标题脱敏，持令牌可见真名
    client.delete(f"/api/novels/私密书?token={tok}")
    masked = client.get("/api/trash").get_json()
    assert masked[0]["title"] == "（隐私书籍）"
    assert masked[0]["private"] is True
    shown = client.get(f"/api/trash?token={tok}").get_json()
    assert shown[0]["title"] == "私密书"


def test_get_novel_toc_and_single_chapter(monkeypatch, tmpdir):
    client = _privacy_env(monkeypatch, tmpdir)
    p = tmpdir / "分章测试书.md"
    write_novel(p, {"title": "分章测试书", "type": "original", "status": "done"}, [
        {"title": "第1章 启程", "content": "第一章的详细正文内容。"},
        {"title": "第2章 冒险", "content": "第二章的详细正文内容。"},
    ])

    # 1. 轻量目录模式 ?toc=1
    r_toc = client.get("/api/novels/分章测试书?toc=1")
    assert r_toc.status_code == 200
    data_toc = r_toc.get_json()
    assert data_toc["toc_only"] is True
    assert len(data_toc["chapters"]) == 2
    assert data_toc["chapters"][0]["title"] == "第1章 启程"
    assert "content" not in data_toc["chapters"][0]  # 正文已被成功剔除

    # 2. 单章获取接口
    r_ch0 = client.get("/api/novels/分章测试书/chapter/0")
    assert r_ch0.status_code == 200
    ch0 = r_ch0.get_json()
    assert ch0["index"] == 0
    assert ch0["title"] == "第1章 启程"
    assert ch0["content"] == "第一章的详细正文内容。"

    r_ch1 = client.get("/api/novels/分章测试书/chapters/1")
    assert r_ch1.status_code == 200
    assert r_ch1.get_json()["title"] == "第2章 冒险"

    # 3. 越界测试
    assert client.get("/api/novels/分章测试书/chapter/99").status_code == 404
    assert client.get("/api/novels/分章测试书/chapter/-1").status_code == 404


def test_rename_novel(tmpdir, monkeypatch):
    client = _privacy_env(monkeypatch, tmpdir)
    p = tmpdir / "旧书名.md"
    write_novel(p, {"title": "旧书名", "type": "original", "status": "done"}, [
        {"title": "第一章", "content": "内容"}
    ])

    # 1. 正常重命名
    res = client.post("/api/novels/旧书名/rename", json={"title": "我的新小说名"})
    assert res.status_code == 200
    d = res.get_json()
    assert d["ok"] is True
    assert d["new_name"] == "我的新小说名"
    assert not (tmpdir / "旧书名.md").exists()
    assert (tmpdir / "我的新小说名.md").exists()

    meta, _, _ = parse_novel(tmpdir / "我的新小说名.md", repair=False)
    assert meta["title"] == "我的新小说名"

    # 2. 空标题报错
    r_empty = client.post("/api/novels/我的新小说名/rename", json={"title": ""})
    assert r_empty.status_code == 400

    # 3. 同名冲突检测
    p2 = tmpdir / "已有书名.md"
    write_novel(p2, {"title": "已有书名"}, [])
    r_conflict = client.post("/api/novels/我的新小说名/rename", json={"title": "已有书名"})
    assert r_conflict.status_code == 409


def test_novel_bible(tmpdir, monkeypatch):
    client = _privacy_env(monkeypatch, tmpdir)
    p = tmpdir / "设定测试书.md"
    write_novel(p, {
        "title": "设定测试书",
        "job_payload": {
            "setting": "蒸汽朋克与炼金术世界",
            "characters": "爱德华：炼金术士，寻找真理之门\n阿尔方斯：铠甲少年，守护哥哥"
        }
    }, [{"title": "第1章", "content": "正文"}])

    # 1. GET 初始设定（从 job_payload 自动提取）
    r_get = client.get("/api/novels/设定测试书/bible")
    assert r_get.status_code == 200
    b1 = r_get.get_json()["bible"]
    assert b1["setting"] == "蒸汽朋克与炼金术世界"
    assert len(b1["characters"]) == 2
    assert b1["characters"][0]["name"] == "爱德华"

    # 2. POST 更新设定
    new_bible = {
        "setting": "升级版蒸汽帝国",
        "characters": [
            {"name": "爱德华", "role": "国家炼金术士", "desc": "机械义肢，天才少年", "goal": "找回弟弟的身体"},
            {"name": "温莉", "role": "机械铠技师", "desc": "青梅竹马", "goal": "打造最好的机械铠"}
        ],
        "conflict": "贤者之石的阴谋",
        "tone": "热血与成长"
    }
    r_post = client.post("/api/novels/设定测试书/bible", json={"bible": new_bible})
    assert r_post.status_code == 200
    assert r_post.get_json()["ok"] is True

    # 3. 校验写回
    meta, _, _ = parse_novel(p, repair=False)
    assert meta["bible"]["setting"] == "升级版蒸汽帝国"
    assert len(meta["bible"]["characters"]) == 2


def test_suggest_tropes_api(tmpdir, monkeypatch):
    import json
    import app
    client = _privacy_env(monkeypatch, tmpdir)

    mock_tropes_resp = json.dumps({
        "tropes": [
            {
                "icon": "🌸",
                "label": "都市言情·反向狩猎",
                "title": "失算后我成了前夫白月光",
                "genre": "都市言情",
                "setting": "现代都市金融投行圈",
                "characters": "主角A：投行总监\n主角B：建筑设计师",
                "storyline": "破镜重圆与克制拉扯",
                "style": "细腻克制",
                "perspective": "第三人称",
                "chapters": 10,
                "per_words": 2000
            }
        ]
    }, ensure_ascii=False)

    monkeypatch.setattr(app, "chat", lambda *args, **kwargs: (mock_tropes_resp, "stop"))

    res = client.post("/api/suggest-tropes", json={"category": "female", "genre": "都市言情", "count": 2})
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert len(data["tropes"]) == 1
    assert data["tropes"][0]["label"] == "都市言情·反向狩猎"
    assert data["tropes"][0]["genre"] == "都市言情"


def test_suggest_tropes_random_multiverse_prompt(tmpdir, monkeypatch):
    """验证灵感脑洞在全部分类（category=all）下，向模型请求完全随机发散的多元题材设定。"""
    import json
    import app
    client = _privacy_env(monkeypatch, tmpdir)

    captured_prompts = []
    def fake_chat(messages, **kwargs):
        captured_prompts.extend([m["content"] for m in messages])
        return (json.dumps({
            "tropes": [
                {"icon": "⚡", "label": "赛博修仙·反派夺舍", "title": "神经漫游金丹期", "genre": "赛博朋克"}
            ]
        }, ensure_ascii=False), "stop")

    monkeypatch.setattr(app, "chat", fake_chat)
    res = client.post("/api/suggest-tropes", json={"category": "all", "count": 4})
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert len(data["tropes"]) == 1

    combined_prompt = " ".join(captured_prompts)
    assert any(k in combined_prompt for k in ["策划", "灵感"]), "Prompt 必须保留触发词"
    assert any(k in combined_prompt for k in ["随机", "多元", "自由"]), "未限定分类时应提示随机多元发散"


def test_suggest_tropes_supports_count_8_and_diversity(tmpdir, monkeypatch):
    """验证灵感脑洞接口支持一次性请求8个及以上脑洞，并在 Prompt 中明确请求 8 个。"""
    import json
    import app
    client = _privacy_env(monkeypatch, tmpdir)

    captured_prompts = []
    def fake_chat(messages, **kwargs):
        captured_prompts.extend([m["content"] for m in messages])
        return (json.dumps({
            "tropes": [
                {"icon": "⚡", "label": f"标签_{i}", "title": f"书名_{i}", "genre": f"题材_{i}"}
                for i in range(8)
            ]
        }, ensure_ascii=False), "stop")

    monkeypatch.setattr(app, "chat", fake_chat)
    res = client.post("/api/suggest-tropes", json={"count": 8})
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    # 断言后端接受 count=8，未被旧上限 6 截断，且返回了 8 个灵感
    assert len(data["tropes"]) >= 8, f"返回的脑洞数量不足8个: {len(data['tropes'])}"
    combined_prompt = " ".join(captured_prompts)
    assert " 8 " in combined_prompt or "8 个" in combined_prompt, "Prompt 中应请求策划 8 个脑洞"





def test_build_continuation_setup_with_bible():
    from app import build_continuation_setup
    payload = {
        "source_title": "测试小说",
        "bible": {
            "setting": "末日废土，辐射尘埃弥漫",
            "characters": [
                {"name": "主角A", "role": "拾荒者", "desc": "冷静果敢", "goal": "寻找净水芯片"}
            ],
            "conflict": "变异生物与绿洲避难所的冲突",
            "tone": "硬核废土生存"
        }
    }
    setup_text = build_continuation_setup(payload)
    assert "末日废土，辐射尘埃弥漫" in setup_text
    assert "主角A（拾荒者）：冷静果敢 [动机/目标: 寻找净水芯片]" in setup_text
    assert "变异生物与绿洲避难所的冲突" in setup_text


def test_extract_json_object_array_resilience():
    from app import extract_json
    # 模拟大模型输出残损（缺少单个对象的闭合大括号，或存在逗号但属于对象属性）
    raw = '''{
  "logline": "一句话梗概",
  "chapters": [
    { "title": "第1章 开始", "points": "要点内容1，带有中文逗号和细节"
  ]
}'''
    res = extract_json(raw)
    assert "chapters" in res
    chs = res["chapters"]
    assert isinstance(chs, list)
    # 严禁将对象按逗号切碎成字符串片段（如 '{"title":...' 和 'points":...'）
    assert not any(isinstance(c, str) and 'points":' in c for c in chs), f"chapters 内部对象被切碎: {chs}"
    if chs:
        # 首项应为 dict 或至少完整保留标题
        if isinstance(chs[0], dict):
            assert "第1章 开始" in chs[0].get("title", "")


def test_api_generate_original_syncs_outline_chapters(monkeypatch, tmpdir):
    import app as app_module
    client = _privacy_env(monkeypatch, tmpdir)
    # 测试当 mode == 'original' 且传入了 3 章的大纲，但 chapters 参数误传为 10 时，
    # 接口与创建的 job 必须以大纲实际章节数 3 为准，绝不盲目按 10 处理
    outline_data = {
        "logline": "梗概",
        "chapters": [
            {"title": "第1章 A", "points": "要点A"},
            {"title": "第2章 B", "points": "要点B"},
            {"title": "第3章 C", "points": "要点C"}
        ]
    }
    payload = {
        "mode": "original",
        "title": "大纲章节对齐测试书",
        "outline": json.dumps(outline_data, ensure_ascii=False),
        "chapters": 10  # 前端历史残留或未同步的旧值
    }
    res = client.post("/api/generate", json=payload)
    assert res.status_code == 200
    job_id = res.get_json()["job_id"]
    job = app_module.JOBS.get(job_id)
    assert job is not None
    assert job["total"] == 3, f"job total 应为大纲的 3 章，实际为 {job['total']}"


def test_chapter_duplicate_guard():
    from app import calc_text_similarity, check_chapter_duplicate

    # 1. 相似度基础函数
    assert calc_text_similarity("", "abc") == 0.0
    assert calc_text_similarity("你好世界", "你好世界") == 1.0
    assert calc_text_similarity("今天天气真好，我们去公园散步吧！", "今天天气真好，咱们去公园走走吧！") > 0.6
    assert calc_text_similarity("修仙界浩劫降临，万道崩碎。", "现代都市金融风暴，盛氏集团陷入危机。") < 0.2

    # 2. 真实案例复现验证
    prev_chapter = {
        "title": "第7章 废纸袋",
        "content": "周一早上七点四十分，深湾市刚经历过一场夜雨，写字楼玻璃幕墙上还挂着水痕，把晨光折射成一片凌乱的碎金。盛栀在八点零五分走进核心区时，注意到何丽正在打印室门口跟保安老蔡说话。何丽手里抱着一摞待销毁的废纸，最上面几张是部门间的备忘录，中间夹着几张报销单复印件..."
    }

    # 重复章节案例：标题同为废纸袋，正文开头高度雷同
    dup_title = "第8章 废纸袋"
    dup_body = "周一早上七点四十分，深湾市刚经历过一场夜雨，写字楼玻璃幕墙上还挂着水痕，把晨光折射成一片凌乱的碎金。盛栀走进盛氏大楼四十七层核心区时，注意到何丽正抱着一摞待销毁的废纸往回收间走，最上面几张是部门备忘录..."
    is_dup, sim, reason = check_chapter_duplicate(prev_chapter, dup_title, dup_body)
    assert is_dup is True
    assert sim >= 0.70
    assert "废纸袋" in prev_chapter["title"]
    assert "标题与上一章高度重合" in reason

    # 正常章节案例：新标题，新情节推进
    normal_title = "第8章 烟与签报"
    normal_body = "林知遥把烟盒扣在玻璃茶几上，发出沉闷的一声响。盛栀端着咖啡从走廊尽头走过来，目光扫过桌上摊开的半截签报单据..."
    is_dup2, sim2, reason2 = check_chapter_duplicate(prev_chapter, normal_title, normal_body)
    assert is_dup2 is False
    assert sim2 < 0.30







