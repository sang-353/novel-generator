# -*- coding: utf-8 -*-
"""P2 功能单元测试：全站访问门禁 (Web Auth) 与 续写候选小样 (Variants)"""
import json
import pytest

from app import app, hash_password, write_novel


@pytest.fixture
def client(tmp_path, monkeypatch):
    test_novels = tmp_path / "novels"
    test_novels.mkdir()
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text("{}", encoding="utf-8")

    monkeypatch.setattr("app.NOVELS_DIR", test_novels)
    monkeypatch.setattr("app.CONFIG_FILE", cfg_file)
    monkeypatch.setattr("app.TRASH_DIR", test_novels / "_trash")
    monkeypatch.setattr("app.CHAPTER_BACKUP_DIR", test_novels / "_trash" / "chapters")
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_web_auth_lifecycle(client):
    # 1. 初始状态：未启用全站口令
    st = client.get("/api/auth/status").get_json()
    assert st["enabled"] is False
    assert st["authorized"] is True

    # 未启用口令时，正常访问 API 应该通过
    res = client.get("/api/novels")
    assert res.status_code == 200

    # 2. 设置全站访问口令 "safe2026"
    res_set = client.post("/api/auth/set-password", json={"new_password": "safe2026"})
    assert res_set.status_code == 200
    data_set = res_set.get_json()
    assert data_set["ok"] is True
    assert data_set["enabled"] is True
    token = data_set["token"]

    # 3. 此时若不带 token 访问受保护的 API，应当被拦截并返回 401
    # 清空 cookie 模拟新客户端
    client.set_cookie("access_token", "")
    r_unauth = client.get("/api/novels")
    assert r_unauth.status_code == 401
    assert r_unauth.get_json()["auth_required"] is True

    # 静态资源与根路径不拦截（允许用户加载页面进行登录）
    r_root = client.get("/")
    assert r_root.status_code == 200

    # 4. 登录验证（错误密码拦截，正确密码通过）
    r_fail = client.post("/api/auth/login", json={"password": "wrongpassword"})
    assert r_fail.status_code == 403

    r_ok = client.post("/api/auth/login", json={"password": "safe2026"})
    assert r_ok.status_code == 200
    login_tok = r_ok.get_json()["token"]
    assert login_tok != ""

    # 带 token 访问受保护 API（通过 Authorization 或 Cookie）
    r_authed = client.get("/api/novels", headers={"Authorization": f"Bearer {login_tok}"})
    assert r_authed.status_code == 200

    # 5. 关闭全站访问口令（需提供原密码）
    r_close_fail = client.post("/api/auth/set-password", json={"new_password": "", "old_password": "wrong"})
    assert r_close_fail.status_code == 403

    r_close = client.post("/api/auth/set-password", json={"new_password": "", "old_password": "safe2026"})
    assert r_close.status_code == 200
    assert r_close.get_json()["enabled"] is False

    # 验证恢复免密访问
    r_no_auth_needed = client.get("/api/novels")
    assert r_no_auth_needed.status_code == 200


def test_generate_variants_api(client, tmp_path, monkeypatch):
    novels_dir = tmp_path / "novels"
    book_file = novels_dir / "小样测试.md"
    meta = {"title": "小样测试", "type": "original", "status": "done"}
    chapters = [{"title": "第1章 惊变", "content": "周默停下了脚步，前方是一条死胡同。"}]
    write_novel(book_file, meta, chapters)

    # Mock chat 返回小样 JSON
    mock_resp = json.dumps({
        "variants": [
            {
                "id": "A",
                "title": "正面硬刚",
                "synopsis": "直接翻墙迎战追兵",
                "preview": "周默没有后退，他深吸一口气，猛地蹬上砖墙翻身而过..."
            },
            {
                "id": "B",
                "title": "智斗潜伏",
                "synopsis": "利用下水道暗中隐藏",
                "preview": "胡同尽头的铁质排水井盖微微松动，周默蹲下身一把拉开井盖..."
            }
        ]
    }, ensure_ascii=False)

    def mock_chat(*args, **kwargs):
        return (mock_resp, "stop")

    monkeypatch.setattr("app.chat", mock_chat)

    res = client.post("/api/generate-variants", json={
        "novel_name": "小样测试",
        "instruction": "摆脱追兵"
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert len(data["variants"]) == 2
    assert data["variants"][0]["title"] == "正面硬刚"
    assert data["variants"][1]["title"] == "智斗潜伏"

    # 测试无小说文件时基于原始正文文本生成走向小样
    res2 = client.post("/api/generate-variants", json={
        "source_title": "未建档小说",
        "source_text": "这是一个测试正文末尾片段，主角走到了悬崖边上。",
        "instruction": "如何度过难关"
    })
    assert res2.status_code == 200
    data2 = res2.get_json()
    assert data2["ok"] is True
    assert len(data2["variants"]) == 2
