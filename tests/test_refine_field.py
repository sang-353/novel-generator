# -*- coding: utf-8 -*-
"""
tests/test_refine_field.py - 测试 POST /api/refine-field 接口及相关纯函数
覆盖：
1. 6 种 field × mode 组合各一个成功用例（断言 text 非空，且提示词包含对应上下文）
2. 参数校验与 400 拦截（field/mode 非法、类型非字符串、单字段 > 4000 字、polish/expand 空文本、regen 同时缺题材和书名，且均不调用 LLM）
3. 文本清洗（代码块围栏、外层引号、废话前缀、标题符号去除，返回空文本时 502 拦截）
4. LLM 异常与超时 502 拦截（非 500、无堆栈），未配置 API Key 400 拦截
5. 全站访问口令 401 门禁保护拦截
6. 接口只读不写盘验证（调用前后 novels 目录与 config.json 零变更）
"""

import hashlib
import json
import pytest
import app
from app import build_refine_field_prompt, clean_refine_text


def _dir_checksum(dir_path):
    """计算目录下所有文件的哈希指纹，用于断言无磁盘变动。"""
    fingerprints = {}
    for p in sorted(dir_path.rglob("*")):
        if p.is_file():
            fingerprints[str(p.relative_to(dir_path))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return fingerprints


@pytest.fixture
def client():
    """获取 Flask 单元测试客户端。"""
    app.app.config["TESTING"] = True
    return app.app.test_client()


# =========================================================================
# 1. 纯函数单元测试
# =========================================================================
def test_clean_refine_text():
    """测试 clean_refine_text 对各类代码块、引号、前缀的清洗能力。"""
    assert clean_refine_text("") == ""
    assert clean_refine_text("   \n\t  ") == ""

    # 代码块围栏
    raw1 = "```markdown\n废土世界建立在机械残骸之上。\n```"
    assert clean_refine_text(raw1) == "废土世界建立在机械残骸之上。"

    # 外层引号与废话前缀
    raw2 = "好的，以下是为您润色后的设定：\n“在九大星环崩解的时代，主角坚守最后的防线。”"
    assert clean_refine_text(raw2) == "在九大星环崩解的时代，主角坚守最后的防线。"

    # 包含标题与列表符号
    raw3 = "【故事主线】\n1. 主角为了复仇踏上征程，揭开深层阴谋。"
    assert clean_refine_text(raw3) == "主角为了复仇踏上征程，揭开深层阴谋。"


# =========================================================================
# 2. 6 种 field × mode 成功组合测试
# =========================================================================
@pytest.mark.parametrize("field,mode,genre,title,setting,storyline,expected_in_prompt", [
    (
        "setting",
        "regen",
        "科幻修真",
        "赛博道祖",
        "旧的赛博背景",
        "",
        ["科幻修真", "赛博道祖", "原有内容", "旧的赛博背景"],
    ),
    (
        "setting",
        "polish",
        "都市异能",
        "天选之子",
        "主角生活在一个充满异能觉醒的现代都市。",
        "",
        ["待润色原文", "主角生活在一个充满异能觉醒的现代都市"],
    ),
    (
        "setting",
        "expand",
        "废土科幻",
        "深空守望",
        "地表辐射严重，幸存者生活在悬空城。",
        "",
        ["待扩充原文", "地表辐射严重，幸存者生活在悬空城"],
    ),
    (
        "storyline",
        "regen",
        "悬疑刑侦",
        "深渊回响",
        "海滨小城接连发生离奇失踪案。",
        "旧的复仇主线",
        ["海滨小城接连发生离奇失踪案", "原有内容", "旧的复仇主线"],
    ),
    (
        "storyline",
        "polish",
        "无限流",
        "致命轮盘",
        "神秘列车穿梭于各个诡异副本。",
        "主角被选中进入列车，凭借极高智商解开每一个关卡的致命谜题。",
        ["神秘列车穿梭于各个诡异副本", "待润色原文", "主角被选中进入列车"],
    ),
    (
        "storyline",
        "expand",
        "古风权谋",
        "九重春华",
        "帝京暗流涌动，夺嫡之战一触即发。",
        "女主步步为营，以女官身份查明灭门惨案。",
        ["帝京暗流涌动", "待扩充原文", "女主步步为营"],
    ),
])
def test_refine_field_success_matrix(client, monkeypatch, field, mode, genre, title, setting, storyline, expected_in_prompt):
    """测试 6 种 field × mode 组合各一个成功用例：返回 text 非空，且提示词包含对应上下文。"""
    captured_messages = []

    def mock_chat(messages, **kwargs):
        captured_messages.extend(messages)
        return "这是 AI 辅助写作生成的正文内容，富有戏剧张力与画面感。", "stop"

    monkeypatch.setattr("app.chat", mock_chat)

    payload = {
        "field": field,
        "mode": mode,
        "genre": genre,
        "title": title,
        "setting": setting,
        "storyline": storyline,
    }
    resp = client.post("/api/refine-field", json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert "text" in data
    assert data["text"] == "这是 AI 辅助写作生成的正文内容，富有戏剧张力与画面感。"

    # 验证提示词中包含所要求的全部上下文关键词
    full_prompt_text = " ".join([m["content"] for m in captured_messages])
    for exp in expected_in_prompt:
        assert exp in full_prompt_text, f"提示词中缺少期望上下文：{exp}"


# =========================================================================
# 3. 参数校验与 400 拦截（且绝不调用 LLM）
# =========================================================================
@pytest.mark.parametrize("payload,expected_err", [
    ({"field": "characters", "mode": "regen"}, "参数 field 必须为 setting 或 storyline"),
    ({"field": "setting", "mode": "invalid_mode"}, "参数 mode 必须为 regen、polish 或 expand"),
    ({"field": "setting", "mode": "regen", "genre": 12345}, "字段 genre 必须为字符串类型"),
    ({"field": "setting", "mode": "regen", "setting": ["list"]}, "字段 setting 必须为字符串类型"),
    ({"field": "setting", "mode": "regen", "provider_id": 999}, "字段 provider_id 必须为字符串类型"),
    ({"field": "setting", "mode": "regen", "genre": "a" * 4001}, "字段 genre 长度超出限制"),
    ({"field": "setting", "mode": "polish", "setting": "   "}, "请先写一点内容"),
    ({"field": "storyline", "mode": "expand", "storyline": ""}, "请先写一点内容"),
    ({"field": "setting", "mode": "regen", "genre": "", "title": ""}, "请先选择题材或填写书名"),
])
def test_refine_field_validation_400(client, monkeypatch, payload, expected_err):
    """参数错误时应返回 400，并给出友好中文提示，且绝对不触发 LLM 调用。"""
    called = []

    def mock_chat(*args, **kwargs):
        called.append(True)
        return "should not be called", "stop"

    monkeypatch.setattr("app.chat", mock_chat)

    resp = client.post("/api/refine-field", json=payload)
    assert resp.status_code == 400
    data = resp.get_json()
    assert expected_err in data.get("error", "")
    assert len(called) == 0, "400 校验失败时绝不能触发 LLM 调用！"


# =========================================================================
# 4. LLM 输出清洗与空内容 502 拦截
# =========================================================================
def test_refine_field_cleaning_resilience(client, monkeypatch):
    """LLM 输出带围栏、引号、前缀时能被正确清洗；清洗后若为空则返回 502。"""
    # 场景 1：复杂包裹清洗
    dirty_output = (
        "```markdown\n"
        "好的！以下是为您润色后的设定：\n"
        "“在机械神教统治的时代，血肉被视为原罪，流民们在地底苟延残喘。”\n"
        "```"
    )
    monkeypatch.setattr("app.chat", lambda *args, **kwargs: (dirty_output, "stop"))

    resp = client.post("/api/refine-field", json={
        "field": "setting",
        "mode": "polish",
        "setting": "在机械神教时代，血肉是原罪。",
    })
    assert resp.status_code == 200
    assert resp.get_json()["text"] == "在机械神教统治的时代，血肉被视为原罪，流民们在地底苟延残喘。"

    # 场景 2：LLM 返回仅有空白或废话，清洗后为空 → 返回 502
    empty_outputs = ["", "   \n\t  ", "```\n```", "好的，以下是：\n"]
    for empty_raw in empty_outputs:
        monkeypatch.setattr("app.chat", lambda *args, **kwargs: (empty_raw, "stop"))
        resp_empty = client.post("/api/refine-field", json={
            "field": "setting",
            "mode": "regen",
            "genre": "科幻",
        })
        assert resp_empty.status_code == 502
        assert "为空" in resp_empty.get_json().get("error", "")


# =========================================================================
# 5. LLM 异常、超时与配置缺失拦截（502 / 400，非 500，无堆栈）
# =========================================================================
def test_refine_field_llm_exception_502(client, monkeypatch):
    """LLM 抛出异常或超时时返回 502，绝不返回 500，且不含 Python traceback。"""
    def mock_chat_fail(*args, **kwargs):
        raise RuntimeError("Connection timed out after 300 seconds")

    monkeypatch.setattr("app.chat", mock_chat_fail)

    resp = client.post("/api/refine-field", json={
        "field": "setting",
        "mode": "regen",
        "genre": "科幻未来",
    })
    assert resp.status_code == 502
    err_text = resp.get_json().get("error", "")
    assert "AI 辅助写作失败" in err_text
    assert "Traceback" not in resp.text
    assert "File \"" not in resp.text


def test_refine_field_missing_api_key_400(client, monkeypatch):
    """未配置有效 provider 或缺少 API Key 时返回 400 友好提示，而非 500。"""
    monkeypatch.setattr("app.get_provider", lambda *args, **kwargs: {"id": "test", "api_key": ""})

    resp = client.post("/api/refine-field", json={
        "field": "setting",
        "mode": "regen",
        "genre": "科幻未来",
    })
    assert resp.status_code == 400
    assert "未配置 API Key" in resp.get_json().get("error", "")


# =========================================================================
# 6. 全站访问口令 401 门禁保护
# =========================================================================
def test_refine_field_web_auth_gate(client):
    """当开启全站访问口令且未授权时，POST /api/refine-field 应返回 401。"""
    # 开启全站密码门禁（会顺带设置 access_token cookie）
    set_resp = client.post("/api/auth/set-password", json={"new_password": "AccessPassword123!"})
    assert set_resp.status_code == 200

    # 清空 cookie 模拟未授权新客户端
    client.set_cookie("access_token", "")

    try:
        # 未携带口令请求
        resp = client.post("/api/refine-field", json={
            "field": "setting",
            "mode": "regen",
            "genre": "科幻",
        })
        assert resp.status_code == 401
        data = resp.get_json()
        assert data.get("auth_required") is True
    finally:
        # 清除口令，恢复环境
        client.post("/api/auth/logout")
        cfg = app.load_config()
        cfg.pop("web_auth", None)
        app.save_config(cfg)


# =========================================================================
# 7. 接口只读不写盘验证（零磁盘变动）
# =========================================================================
def test_refine_field_zero_disk_mutation(client, monkeypatch):
    """接口只读，绝不读写小说文件，不更新 config.json，调用前后磁盘零改动。"""
    monkeypatch.setattr("app.chat", lambda *args, **kwargs: ("全新的设定文本", "stop"))

    novels_dir = app.NOVELS_DIR
    config_file = app.CONFIG_FILE

    # 记录调用前指纹
    before_novels = _dir_checksum(novels_dir)
    before_cfg = config_file.read_text(encoding="utf-8") if config_file.exists() else None

    # 调用接口
    resp = client.post("/api/refine-field", json={
        "field": "setting",
        "mode": "regen",
        "genre": "科幻未来",
        "title": "星际纪元",
    })
    assert resp.status_code == 200

    # 记录调用后指纹
    after_novels = _dir_checksum(novels_dir)
    after_cfg = config_file.read_text(encoding="utf-8") if config_file.exists() else None

    assert before_novels == after_novels, "接口调用导致 novels/ 目录发生了文件读写变动！"
    assert before_cfg == after_cfg, "接口调用导致 config.json 发生了变动！"


# =========================================================================
# 8. 假 LLM 服务（fake_llm_server）模式支持验证
# =========================================================================
def test_fake_llm_server_refine_modes():
    """验证 fake_llm_server 对 refine-field 及 error/empty/fenced 模式的正确响应。"""
    from tests.e2e.fake_llm_server import FakeLLMHandler

    handler = FakeLLMHandler.__new__(FakeLLMHandler)
    messages = [{"role": "user", "content": "请为小说构思一段故事背景与核心设定"}]

    # 1. 正常模式
    normal_text = handler._generate_response_content(messages, mode="normal", custom_response=None)
    assert "悬空浮岛" in normal_text
    assert len(normal_text) > 30

    # 2. fenced 模式
    fenced_text = handler._generate_response_content(messages, mode="fenced", custom_response=None)
    assert "```markdown" in fenced_text
    assert "“" in fenced_text

    # 3. empty 模式
    empty_text = handler._generate_response_content(messages, mode="empty", custom_response=None)
    assert empty_text == ""
