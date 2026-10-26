"""
tests/test_gap_analysis.py - 补充接口缺口分析与安全鲁棒性测试

覆盖范围：
1. 全站口令访问拦截与白名单机制
2. 隐私书籍在未提供/提供错误 privacy_token 时的端点级权限隔离
3. 路径穿越、特殊字符、Emoji、引号与边界越界下标
4. 缺少必要参数、类型错误与畸形 Payload 校验
5. 磁盘物理文件落盘一致性与 Frontmatter 元数据完整性
6. 并发竞态冲突 (生成中与编辑/删除互斥)
7. Markdown 语法鲁棒性 ("---", "## 卷：", "# ")
8. LLM 异常格式防御性解析 (代码块包裹、字段漂移、顶层数组、超时)
"""

import io
import json
import re
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import app as app_module


@pytest.fixture
def client():
    return app_module.app.test_client()


def create_sample_novel(name="测试小说", private=False, chapters_count=3, extra_meta=None):
    p = app_module.NOVELS_DIR / f"{name}.md"
    meta = {
        "title": name,
        "type": "original",
        "genre": "都市",
        "status": "done",
        "created": app_module.now_iso(),
        "updated": app_module.now_iso(),
        "words": 1500,
        "chapters_count": chapters_count,
    }
    if private:
        meta["private"] = True
    if extra_meta:
        meta.update(extra_meta)

    chapters = []
    for i in range(1, chapters_count + 1):
        chapters.append({
            "title": f"第{i}章 章节标题{i}",
            "content": f"这是第{i}章的正文内容，包含一些文字描述。",
            "volume": "正文",
        })
    app_module.write_novel(p, meta, chapters)
    return p, meta, chapters


# =========================================================================
# 1. 全站口令拦截与白名单测试 (Web Auth)
# =========================================================================
def test_web_auth_all_endpoints_gate(client):
    """验证开启全站访问口令时，未携带有效 token 的请求统一被拦截为 401。"""
    # 模拟开启 web_auth
    app_module.save_config({
        "providers": [app_module.DEFAULT_PROVIDER],
        "web_auth": {"hash": "dummyhash", "salt": "dummysalt"},
    })

    protected_endpoints = [
        ("GET", "/api/novels"),
        ("GET", "/api/novels/private"),
        ("GET", "/api/novels/test"),
        ("GET", "/api/novels/test/chapters/0"),
        ("POST", "/api/novels/test/chapters/0"),
        ("DELETE", "/api/novels/test"),
        ("POST", "/api/novels/test/rename"),
        ("GET", "/api/novels/test/bible"),
        ("POST", "/api/novels/test/bible"),
        ("POST", "/api/novels/test/preferences"),
        ("POST", "/api/novels/test/reorder-chapters"),
        ("GET", "/api/novels/test/chapters/0/history"),
        ("POST", "/api/novels/test/chapters/0/restore-snapshot"),
        ("POST", "/api/novels/import-txt"),
        ("POST", "/api/novels/test/search-replace"),
        ("GET", "/api/settings"),
        ("POST", "/api/settings"),
        ("GET", "/api/settings/prompts"),
        ("POST", "/api/settings/prompts"),
        ("GET", "/api/trash"),
        ("POST", "/api/trash/test/restore"),
        ("DELETE", "/api/trash/test"),
        ("GET", "/api/trash/chapters"),
        ("POST", "/api/trash/chapters/test/restore"),
        ("DELETE", "/api/trash/chapters/test"),
        ("GET", "/api/novels/test/search?q=abc"),
        ("DELETE", "/api/cache"),
        ("GET", "/api/cache/stats"),
        ("GET", "/api/novels/test/export?format=txt"),
        ("POST", "/api/novels/test/selection-assist"),
        ("POST", "/api/novels/test/chapters/delete"),
        ("POST", "/api/novels/test/chapters/rewrite"),
        ("POST", "/api/suggest-titles"),
        ("GET", "/api/suggest-tropes"),
        ("POST", "/api/suggest-tropes"),
        ("POST", "/api/generate-bible"),
        ("POST", "/api/outline"),
        ("POST", "/api/analyze-style"),
        ("POST", "/api/analyze"),
        ("POST", "/api/generate-variants"),
        ("POST", "/api/generate"),
        ("GET", "/api/jobs/dummy"),
        ("POST", "/api/jobs/dummy/cancel"),
        ("GET", "/api/jobs/dummy/stream"),
        ("POST", "/api/test"),
        ("GET", "/api/privacy"),
        ("POST", "/api/privacy/set"),
        ("POST", "/api/privacy/unlock"),
        ("POST", "/api/privacy/lock"),
        ("POST", "/api/auth/logout"),
        ("POST", "/api/auth/set-password"),
    ]

    for method, path in protected_endpoints:
        if method == "GET":
            r = client.get(path)
        elif method == "POST":
            r = client.post(path, json={})
        elif method == "DELETE":
            r = client.delete(path)
        assert r.status_code == 401, f"{method} {path} 未被 401 拦截，实际返回 {r.status_code}"

    # 白名单端点放行
    r_status = client.get("/api/auth/status")
    assert r_status.status_code == 200
    r_login = client.post("/api/auth/login", json={"password": "wrong"})
    assert r_login.status_code == 403


# =========================================================================
# 2. 隐私书籍权限隔离测试
# =========================================================================
def test_privacy_book_protection_standard_endpoints(client):
    """测试标准 Studio 端点对未授权隐私访问的拦截。"""
    # 开启隐私密码
    client.post("/api/privacy/set", json={"new_password": "Password123!"})
    create_sample_novel("绝密隐私书", private=True)

    endpoints_to_test = [
        ("GET", "/api/novels/绝密隐私书", None),
        ("GET", "/api/novels/绝密隐私书/chapters/0", None),
        ("POST", "/api/novels/绝密隐私书/chapters/0", {"content": "篡改"}),
        ("DELETE", "/api/novels/绝密隐私书", None),
        ("POST", "/api/novels/绝密隐私书/rename", {"new_title": "新名字"}),
        ("GET", "/api/novels/绝密隐私书/bible", None),
        ("POST", "/api/novels/绝密隐私书/bible", {"bible": {}}),
        ("POST", "/api/novels/绝密隐私书/preferences", {}),
        ("POST", "/api/novels/绝密隐私书/reorder-chapters", {"new_order": [0, 1, 2]}),
        ("GET", "/api/novels/绝密隐私书/chapters/0/history", None),
        ("POST", "/api/novels/绝密隐私书/chapters/0/restore-snapshot", {"timestamp": "123"}),
        ("POST", "/api/novels/绝密隐私书/search-replace", {"find": "正文", "replace": "改"}),
        ("GET", "/api/novels/绝密隐私书/search?q=正文", None),
        ("GET", "/api/novels/绝密隐私书/export?format=txt", None),
        ("POST", "/api/novels/绝密隐私书/chapters/delete", {"index": 0}),
        ("POST", "/api/novels/绝密隐私书/chapters/rewrite", {"index": 0}),
    ]

    for method, url, body in endpoints_to_test:
        if method == "GET":
            r = client.get(url)
        elif method == "POST":
            r = client.post(url, json=body or {})
        elif method == "DELETE":
            r = client.delete(url)
        assert r.status_code in [401, 403, 404], f"{method} {url} 未拦截，返回 {r.status_code}"


def test_privacy_leak_selection_assist(client):
    """测试 selection-assist 对隐私小说的鉴权防护。"""
    client.post("/api/privacy/set", json={"new_password": "Password123!"})
    create_sample_novel("绝密书精修", private=True)
    with patch("app.chat", return_value=("润色文本", "stop")):
        r = client.post("/api/novels/绝密书精修/selection-assist", json={"selected_text": "正文片段"})
        assert r.status_code == 403, f"未拦截隐私书籍精修请求，返回 {r.status_code}"


def test_privacy_leak_trash_restore(client):
    """测试回收站恢复对隐私小说的鉴权防护。"""
    client.post("/api/privacy/set", json={"new_password": "Password123!"})
    p_trash = app_module.TRASH_DIR / "绝密回收书.md"
    app_module.write_novel(p_trash, {"title": "绝密回收书", "private": True}, [{"title": "第1章", "content": "密"}])

    r = client.post("/api/trash/绝密回收书/restore", json={})
    assert r.status_code == 403, f"未拦截无凭据恢复隐私书籍，返回 {r.status_code}"


def test_privacy_leak_trash_purge(client):
    """测试回收站彻底删除对隐私小说的鉴权防护。"""
    client.post("/api/privacy/set", json={"new_password": "Password123!"})
    p_trash = app_module.TRASH_DIR / "绝密粉碎书.md"
    app_module.write_novel(p_trash, {"title": "绝密粉碎书", "private": True}, [{"title": "第1章", "content": "密"}])

    r = client.delete("/api/trash/绝密粉碎书")
    assert r.status_code == 403, f"未拦截无凭据彻底删除隐私书籍，返回 {r.status_code}"


def test_privacy_leak_delete_chapter_backup(client):
    """测试单章回收站删除对隐私小说的鉴权防护。"""
    client.post("/api/privacy/set", json={"new_password": "Password123!"})
    create_sample_novel("绝密单章备份书", private=True)
    app_module._backup_chapter("绝密单章备份书", 0, {"title": "隐私章", "content": "密"})

    fname = None
    for p in app_module.CHAPTER_BACKUP_DIR.glob("*.json"):
        if "绝密单章备份书" in p.name:
            fname = p.name
            break
    assert fname is not None

    r = client.delete(f"/api/trash/chapters/{fname}")
    assert r.status_code == 403, f"未拦截无凭据删除隐私快照，返回 {r.status_code}"


def test_privacy_leak_generate_continuation_and_variants(client):
    """测试续写启动与剧情小样对隐私小说的鉴权防护。"""
    client.post("/api/privacy/set", json={"new_password": "Password123!"})
    create_sample_novel("绝密生成书", private=True)

    r_gen = client.post("/api/generate", json={"source_title": "绝密生成书", "mode": "continuation"})
    assert r_gen.status_code == 403, f"未拦截隐私书续写生成，返回 {r_gen.status_code}"

    r_var = client.post("/api/generate-variants", json={"novel_name": "绝密生成书"})
    assert r_var.status_code == 403, f"未拦截隐私书剧情小样，返回 {r_var.status_code}"


# =========================================================================
# 3. 边界、特殊字符与路径安全测试
# =========================================================================
def test_path_traversal_on_novels_rejected(client):
    """验证安全小说路径函数拦截路径穿越请求。"""
    r = client.get("/api/novels/..%2f..%2fconfig")
    assert r.status_code == 404


def test_path_traversal_on_trash_purge(client):
    """验证回收站彻底删除端点的路径穿越防护。"""
    r = client.delete("/api/trash/..%2f..%2fconfig")
    assert r.status_code == 404


def test_special_characters_and_emoji_support(client):
    """验证 Emoji 书名与特殊符号能够正确读写。"""
    emoji_title = "🚀宇宙奇缘✨逆风翻盘🔥"
    create_sample_novel(emoji_title)
    r = client.get(f"/api/novels/{emoji_title}")
    assert r.status_code == 200
    assert r.get_json()["name"] == emoji_title


def test_rename_novel_validation(client):
    """验证重命名空书名与非法字符校验。"""
    create_sample_novel("重命名测试书")
    r_empty = client.post("/api/novels/重命名测试书/rename", json={"new_title": "   "})
    assert r_empty.status_code == 400


# =========================================================================
# 4. 缺少参数、类型校验与越界索引测试
# =========================================================================
def test_edit_chapter_missing_content(client):
    create_sample_novel("参数测试书")
    r = client.post("/api/novels/参数测试书/chapters/0", json={})
    assert r.status_code == 400


def test_reorder_chapters_invalid_type_and_bounds(client):
    create_sample_novel("重排测试书", chapters_count=3)
    r_type = client.post("/api/novels/重排测试书/reorder-chapters", json={"new_order": "not-list"})
    assert r_type.status_code == 400

    r_bounds = client.post("/api/novels/重排测试书/reorder-chapters", json={"new_order": [0, 999]})
    assert r_bounds.status_code == 400


def test_search_replace_empty_find_and_bad_regex(client):
    create_sample_novel("查找测试书")
    r_empty = client.post("/api/novels/查找测试书/search-replace", json={"find": ""})
    assert r_empty.status_code == 400

    r_regex = client.post("/api/novels/查找测试书/search-replace", json={"find": "[a-", "regex": True})
    assert r_regex.status_code == 400


def test_save_prompt_settings_non_dict_payload(client):
    """测试 settings/prompts 传入非 dict 请求体时返回 400。"""
    r = client.post("/api/settings/prompts", json=["not", "a", "dict"])
    assert r.status_code == 400, f"未拦截非 dict payload，返回 {r.status_code}"


def test_migrate_legacy_config_preserves_web_auth_and_privacy():
    """测试旧版配置迁移逻辑不得丢弃 web_auth 和 privacy 等关键安全配置。"""
    legacy_data = {
        "base_url": "https://api.example.com",
        "api_key": "sk-legacy-test",
        "model": "deepseek-chat",
        "web_auth": {"hash": "auth_hash_123", "salt": "auth_salt_456"},
        "privacy": {"hash": "priv_hash_789", "salt": "priv_salt_012"},
        "custom_key": "custom_val"
    }
    migrated = app_module._migrate_legacy_config(legacy_data)
    assert "providers" in migrated, "缺失 providers 列表"
    assert migrated.get("web_auth") == {"hash": "auth_hash_123", "salt": "auth_salt_456"}, f"web_auth 被丢弃: {migrated}"
    assert migrated.get("privacy") == {"hash": "priv_hash_789", "salt": "priv_salt_012"}, f"privacy 被丢弃: {migrated}"


def test_extract_json_supports_top_level_array():
    """测试 extract_json 对顶层 JSON Array 列表的原生支持。"""
    raw_array = '[{"title": "书1"}, {"title": "书2"}]'
    parsed = app_module.extract_json(raw_array)
    assert isinstance(parsed, list), f"期望返回 list，实际得到: {type(parsed)}"
    assert len(parsed) == 2

    raw_fence = '```json\n[{"name": "卡片1"}, {"name": "卡片2"}]\n```'
    parsed_fence = app_module.extract_json(raw_fence)
    assert isinstance(parsed_fence, list)
    assert len(parsed_fence) == 2


def test_llm_top_level_array_resilience(client):
    """测试 LLM 顶层直接输出数组时 suggest-tropes 能够正常提取不报 500。"""
    with patch("app.chat", return_value=('[{"title": "顶层数组书", "label": "顶层标签"}]', "stop")):
        r = client.post("/api/suggest-tropes", json={"genre": "都市"})
        assert r.status_code == 200
        assert len(r.get_json()["tropes"]) == 1


def test_generate_variants_top_level_array_resilience(client):
    """测试 LLM 顶层直接输出数组时 generate-variants 不触发 AttributeError 崩溃。"""
    create_sample_novel("小样数组测试书")
    with patch("app.chat", return_value=('[{"id": "A", "title": "走向A", "preview": "片段A"}, {"id": "B", "title": "走向B", "preview": "片段B"}]', "stop")):
        r = client.post("/api/generate-variants", json={"novel_name": "小样数组测试书"})
        assert r.status_code == 200, f"返回状态码 {r.status_code}: {r.get_json()}"
        assert len(r.get_json().get("variants", [])) >= 2


def test_chapter_indexing_bounds(client):
    create_sample_novel("越界测试书", chapters_count=2)
    # 负数
    assert client.get("/api/novels/越界测试书/chapters/-1").status_code == 404
    # 越界
    assert client.get("/api/novels/越界测试书/chapters/999").status_code == 404
    # 不存在的书
    assert client.get("/api/novels/不存在的书名/chapters/0").status_code == 404


def test_job_not_found(client):
    assert client.get("/api/jobs/not_found_12345").status_code == 404
    assert client.post("/api/jobs/not_found_12345/cancel").status_code == 404


# =========================================================================
# 5. 磁盘落盘物理写入校验
# =========================================================================
def test_disk_mutation_and_frontmatter_preservation(client):
    p, _, _ = create_sample_novel("落盘测试书", chapters_count=2)

    # 1. 编辑章节正文
    r = client.post("/api/novels/落盘测试书/chapters/0", json={
        "title": "已更名的第1章",
        "content": "写入磁盘的真实全新正文内容",
    })
    assert r.status_code == 200

    # 检查磁盘文件内容
    meta, chapters, _ = app_module.parse_novel(p)
    assert chapters[0]["title"] == "已更名的第1章"
    assert "写入磁盘的真实全新正文内容" in chapters[0]["content"]
    assert meta["title"] == "落盘测试书"

    # 2. 搜索替换落盘
    r_rep = client.post("/api/novels/落盘测试书/search-replace", json={
        "find": "真实全新正文",
        "replace": "替换后物理确认",
        "preview_only": False,
    })
    assert r_rep.status_code == 200
    meta2, chapters2, _ = app_module.parse_novel(p)
    assert "替换后物理确认" in chapters2[0]["content"]

    # 3. 删除移入回收站
    r_del = client.delete("/api/novels/落盘测试书")
    assert r_del.status_code == 200
    assert not p.exists()
    assert (app_module.TRASH_DIR / "落盘测试书.md").exists()


def test_write_novel_atomic_replace_cleanup(client):
    """测试 write_novel 原子写入不会残留临时文件，且成功更新目标文件。"""
    p, meta, chs = create_sample_novel("原子写测试书", chapters_count=1)
    chs[0]["content"] = "全新原子内容写入"
    app_module.write_novel(p, meta, chs)

    # 验证没有残留的 .tmp 文件
    tmp_files = list(p.parent.glob(".tmp_原子写测试书_*.tmp"))
    assert len(tmp_files) == 0, f"写盘后残留了临时文件: {tmp_files}"

    # 验证文件正常读取
    _, reloaded, _ = app_module.parse_novel(p)
    assert reloaded[0]["content"] == "全新原子内容写入"


# =========================================================================
# 6. 专项测试：并发互斥与冲突防护
# =========================================================================
def test_concurrency_busy_lock_protection_edit(client):
    """测试生成中 (book_busy) 时 edit_chapter 正常拦截 409。"""
    create_sample_novel("并发繁忙书")
    app_module.acquire_book("并发繁忙书")
    try:
        r = client.post("/api/novels/并发繁忙书/chapters/0", json={"content": "修改"})
        assert r.status_code == 409
    finally:
        app_module.release_book("并发繁忙书")


def test_concurrency_busy_lock_protection_delete_chapter(client):
    create_sample_novel("并发删章书", chapters_count=3)
    app_module.acquire_book("并发删章书")
    try:
        r = client.post("/api/novels/并发删章书/chapters/delete", json={"index": 1})
        assert r.status_code == 409, f"未拦截生成中删章请求，返回 {r.status_code}"
    finally:
        app_module.release_book("并发删章书")


def test_concurrency_busy_lock_protection_delete_novel(client):
    create_sample_novel("并发整本删书")
    app_module.acquire_book("并发整本删书")
    try:
        r = client.delete("/api/novels/并发整本删书")
        assert r.status_code == 409, f"未拦截生成中删书请求，返回 {r.status_code}"
    finally:
        app_module.release_book("并发整本删书")


def test_concurrency_busy_lock_protection_rewrite(client):
    create_sample_novel("并发重写书", chapters_count=3)
    app_module.acquire_book("并发重写书")
    try:
        r = client.post("/api/novels/并发重写书/chapters/rewrite", json={"index": 1})
        assert r.status_code == 409, f"未拦截生成中重写请求，返回 {r.status_code}"
    finally:
        app_module.release_book("并发重写书")


# =========================================================================
# 7. 专项测试：Markdown 语法解析鲁棒性
# =========================================================================
def test_markdown_horizontal_rule_preservation(client):
    """测试正文中带有分割线 --- 能够完整保留。"""
    p, _, _ = create_sample_novel("语法分割线书", chapters_count=1)
    content = "段落一\n\n---\n\n段落二（分割线之下）\n\n---"
    client.post("/api/novels/语法分割线书/chapters/0", json={"content": content})
    _, chs, _ = app_module.parse_novel(p)
    assert chs[0]["content"] == content


def test_markdown_volume_syntax_in_content_data_loss(client):
    """测试正文中包含类似 '## 卷：' 文本时的数据丢失隐患。"""
    p, _, _ = create_sample_novel("假卷名测试书", chapters_count=1)
    content = "第一段情节\n## 卷：伪卷名文本\n卷名下方的后续重要情节文本"
    client.post("/api/novels/假卷名测试书/chapters/0", json={"content": content})
    _, chs, _ = app_module.parse_novel(p)
    assert "卷名下方的后续重要情节文本" in chs[0]["content"], "后续正文被静默丢弃！"


def test_markdown_heading_in_content_split(client):
    """测试正文中包含一级标题语法 '# ' 时误切分章节的问题。"""
    p, _, _ = create_sample_novel("标题语法书", chapters_count=1)
    content = "第一段\n# 引用标题：天龙八部\n第二段内容"
    client.post("/api/novels/标题语法书/chapters/0", json={"content": content})
    _, chs, _ = app_module.parse_novel(p)
    assert len(chs) == 1, f"正文包含一级标题导致单章被意外切分为 {len(chs)} 章！"


# =========================================================================
# 8. 专项测试：LLM 异常响应容错与防御性提取 (全部 Mock)
# =========================================================================
def test_llm_markdown_fence_extraction_resilience(client):
    """测试 LLM 输出带 ```json 代码块时的提取能力。"""
    with patch("app.chat", return_value=('```json\n{"tropes": [{"title": "代码块书", "label": "标签"}]}\n```', "stop")):
        r = client.post("/api/suggest-tropes", json={"genre": "都市"})
        assert r.status_code == 200
        assert len(r.get_json()["tropes"]) == 1

    with patch("app.chat", return_value=('```json\n{"suggested_title": "设定书", "setting": "宏大"}\n```', "stop")):
        r = client.post("/api/generate-bible", json={"genre": "玄幻"})
        assert r.status_code == 200
        assert r.get_json()["bible"]["suggested_title"] == "设定书"

    with patch("app.chat", return_value=('```json\n{"logline": "梗概", "chapters": [{"title": "第1章"}]}\n```', "stop")):
        r = client.post("/api/outline", json={"genre": "都市", "chapters": 5})
        assert r.status_code == 200
        assert "outline" in r.get_json()


def test_llm_field_name_mutation_resilience(client):
    """测试 LLM 输出字段漂移 (tropes -> templates / list) 时的容错。"""
    with patch("app.chat", return_value=('{"templates": [{"book_name": "漂移书", "tag": "新标签"}]}', "stop")):
        r = client.post("/api/suggest-tropes", json={"genre": "都市"})
        assert r.status_code == 200
        assert len(r.get_json()["tropes"]) == 1


def test_llm_timeout_and_empty_handling(client):
    """测试 LLM 发生超时与空内容时，优雅返回 500 结构化错误而非抛未捕获异常。"""
    with patch("app.chat", side_effect=RuntimeError("Connection Timeout")):
        r = client.post("/api/suggest-tropes", json={"genre": "都市"})
        assert r.status_code == 500
        assert "error" in r.get_json()

    with patch("app.chat", return_value=("", "stop")):
        r = client.post("/api/generate-bible", json={"genre": "玄幻"})
        assert r.status_code == 500
        assert "error" in r.get_json()
