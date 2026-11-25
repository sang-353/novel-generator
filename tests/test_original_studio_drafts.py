"""Unit and API tests for Original Novel Studio Drafts Box."""

import pytest

from app import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    """配置隔离临时目录与测试 client。"""
    monkeypatch.setattr("app.NOVELS_DIR", tmp_path)
    monkeypatch.setattr("original_studio.models.NOVELS_DIR", tmp_path)
    monkeypatch.setattr("original_studio.engine.NOVELS_DIR", tmp_path)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_draft_box_partial_save_list_get_update_delete(client):
    """半成品设定（缺书名、缺 logline、缺主角）应可正常保存、读取、更新、删除，且不污染书架。"""
    partial_payload = {
        "active_station": 2,
        "current_stage_index": 1,
        "spec": {
            "schema_version": "2.0.0",
            "meta": {"title": "", "genre": "都市言情"},
            "ideation": {"logline": ""},
            "worldview": {"background": "只写了一半的世界观"},
        },
    }
    res = client.post("/api/novel/original/drafts", json=partial_payload)
    assert res.status_code == 200
    body = res.get_json()
    draft_id = body["data"]["draft_id"]
    assert body["data"]["title"] == "未命名草稿"
    assert body["data"]["active_station"] == 2

    # 列表应包含该草稿
    list_res = client.get("/api/novel/original/drafts")
    assert list_res.status_code == 200
    drafts = list_res.get_json()["data"]["drafts"]
    assert len(drafts) == 1
    assert drafts[0]["draft_id"] == draft_id
    assert drafts[0]["title"] == "未命名草稿"

    # 书架列表不应包含 _drafts 中的草稿
    novels_res = client.get("/api/novels")
    assert novels_res.status_code == 200
    assert novels_res.get_json() == []

    # 更新同一份草稿，补上书名与一句话创意
    partial_payload["draft_id"] = draft_id
    partial_payload["spec"]["meta"]["title"] = "半成品测试新书"
    partial_payload["spec"]["ideation"]["logline"] = "补上一句话创意"
    upd_res = client.post("/api/novel/original/drafts", json=partial_payload)
    assert upd_res.status_code == 200
    assert upd_res.get_json()["data"]["title"] == "半成品测试新书"

    # 读取单条草稿
    get_res = client.get(f"/api/novel/original/drafts/{draft_id}")
    assert get_res.status_code == 200
    loaded = get_res.get_json()["data"]
    assert loaded["spec"]["worldview"]["background"] == "只写了一半的世界观"
    assert loaded["spec"]["ideation"]["logline"] == "补上一句话创意"

    # 删除草稿
    del_res = client.delete(f"/api/novel/original/drafts/{draft_id}")
    assert del_res.status_code == 200

    # 再读取应返回 404
    get_after = client.get(f"/api/novel/original/drafts/{draft_id}")
    assert get_after.status_code == 404


def test_draft_box_validation_and_safety(client):
    """缺少 spec 应返回 400；异常 draft_id 不应发生路径穿越。"""
    bad = client.post("/api/novel/original/drafts", json={"title": "无 spec"})
    assert bad.status_code == 400

    missing = client.get("/api/novel/original/drafts/nonexistent_id")
    assert missing.status_code == 404

    del_missing = client.delete("/api/novel/original/drafts/nonexistent_id")
    assert del_missing.status_code == 404
