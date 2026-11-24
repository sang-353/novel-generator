# -*- coding: utf-8 -*-
"""Comprehensive integration test suite covering ALL backend endpoints across:
1. Settings & Web Auth & Privacy
2. Novel Library & Studio Chapter Operations
3. Continuation & Analysis & Generation Jobs
4. Original Studio (Greenfield v2): Spec, Deduce, RefineField, Beats, StageRunner, Checkpoint
"""

import json
import time
from unittest.mock import patch
import pytest

import app as app_module
from app import app, write_novel, parse_novel
from original_studio.models import save_novel_spec, load_novel_spec, load_novel_runtime


@pytest.fixture
def client(tmp_path, monkeypatch):
    test_novels = tmp_path / "novels"
    test_novels.mkdir(parents=True, exist_ok=True)
    test_trash = test_novels / "_trash"
    test_trash.mkdir(parents=True, exist_ok=True)
    test_backups = test_trash / "chapters"
    test_backups.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("app.NOVELS_DIR", test_novels)
    monkeypatch.setattr("app.TRASH_DIR", test_trash)
    monkeypatch.setattr("app.CHAPTER_BACKUP_DIR", test_backups)
    monkeypatch.setattr("original_studio.models.NOVELS_DIR", test_novels)
    monkeypatch.setattr("original_studio.engine.NOVELS_DIR", test_novels)

    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _init_test_novel(novel_stem="test_book"):
    meta = {
        "title": "测试小说",
        "genre": "都市",
        "created": "2026-01-01T00:00:00",
    }
    chapters = [
        {"title": "第1章 初见", "content": "这是第一章的正文内容，足够长。", "volume": "正文"},
        {"title": "第2章 进展", "content": "这是第二章的正文内容。", "volume": "正文"},
    ]
    p = app_module.NOVELS_DIR / f"{novel_stem}.md"
    write_novel(p, meta, chapters)
    return novel_stem


def _sample_valid_spec():
    return {
        "schema_version": "2.0.0",
        "locked_fields": [],
        "meta": {
            "title": "测试原创书",
            "genre": "都市言情",
            "selected_trope": "合租契约",
            "target_total_words": 100000,
            "target_stages_count": 3,
            "target_words_per_chapter": 2000,
        },
        "ideation": {
            "logline": "调香师与画家的合租心动日常。",
            "hook": "气味免疫",
            "reader_expectation": "甜宠治愈",
            "theme": "治愈与陪伴",
            "tone": "温润轻快",
        },
        "worldview": {
            "background": "老洋房清吧二楼",
            "special_rules": "不越界探听隐私",
            "taboos": "不可假戏真做动真感情",
        },
        "protagonist": {
            "id": "char_male",
            "name": "江月白",
            "role": "调香师",
            "want": "拿下金奖",
            "need": "学会接纳",
            "flaw": "洁癖傲娇",
            "arc": "从防备到接纳",
        },
        "characters": [
            {
                "id": "char_female",
                "name": "苏晴好",
                "relation_type": "cp_love",
                "role_desc": "绘本插画师",
                "bond_or_conflict": "作息颠倒引发摩擦",
            }
        ],
        "ending": {
            "climax_vision": "颁奖前夕告白",
            "core_dilemma": "继承权还是爱人",
            "ultimate_cost": "放弃家族资助",
            "resolution_tone": "浪漫甜蜜",
        },
        "stages": [
            {
                "stage_index": 1,
                "title": "第 1 卷：屋檐下",
                "expected_chapters": 3,
                "anchors": {
                    "stage_goal": "建立同居契约",
                    "main_obstacle": "作息摩擦",
                    "climax_hook": "暴雨夜拯救猫咪",
                    "transition_springboard": "双方家长查房",
                },
            }
        ],
    }


# ============================================================================
# 1. 设置、安全门禁与隐私书架接口测试
# ============================================================================

def test_settings_endpoints(client):
    # GET /api/settings
    r = client.get("/api/settings")
    assert r.status_code == 200
    d = r.get_json()
    assert "providers" in d

    # POST /api/settings
    new_cfg = {
        "providers": [
            {"id": "p1", "name": "Provider 1", "base_url": "https://api.openai.com", "api_key": "sk-123", "model": "gpt-4o"}
        ],
        "active_provider": "p1",
    }
    r = client.post("/api/settings", json=new_cfg)
    assert r.status_code == 200
    assert r.get_json().get("ok") is True

    # POST /api/test (Provider connectivity test)
    with patch("app.chat", return_value=("pong", "stop")):
        r = client.post("/api/test", json={"provider_id": "p1"})
        assert r.status_code == 200
        assert r.get_json().get("ok") is True


def test_auth_and_privacy_lifecycle(client):
    # 1. Auth status
    r = client.get("/api/auth/status")
    assert r.status_code == 200
    assert r.get_json().get("enabled") is False

    # 2. Set password & verify
    r = client.post("/api/auth/set-password", json={"new_password": "NewSecretPassword123"})
    assert r.status_code == 200

    r = client.get("/api/auth/status")
    assert r.status_code == 200
    assert r.get_json().get("enabled") is True

    # 3. Login
    r = client.post("/api/auth/login", json={"password": "NewSecretPassword123"})
    assert r.status_code == 200
    token = r.get_json().get("token")
    assert token

    # 4. Disable password
    r = client.post(
        "/api/auth/set-password",
        json={"old_password": "NewSecretPassword123", "new_password": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200

    # 5. Privacy endpoints
    r = client.get("/api/privacy")
    assert r.status_code == 200

    r = client.post("/api/privacy/set", json={"new_password": "PrivateShelfPassword888"})
    assert r.status_code == 200

    r = client.post("/api/privacy/unlock", json={"password": "PrivateShelfPassword888"})
    assert r.status_code == 200

    r = client.post("/api/privacy/lock")
    assert r.status_code == 200


# ============================================================================
# 2. 小说书架与章节 CRUD / 批处理接口测试
# ============================================================================

def test_novel_library_and_chapter_endpoints(client):
    novel_stem = _init_test_novel("my_test_book")

    # 1. GET /api/novels
    r = client.get("/api/novels")
    assert r.status_code == 200
    novels = r.get_json()
    assert isinstance(novels, list)
    assert any(n["name"] == novel_stem for n in novels)

    # 2. GET /api/novels/<name> (TOC & metadata)
    r = client.get(f"/api/novels/{novel_stem}")
    assert r.status_code == 200
    data = r.get_json()
    assert len(data.get("chapters", [])) == 2
    assert data["meta"]["title"] == "测试小说"

    # Light TOC mode
    r_toc = client.get(f"/api/novels/{novel_stem}?toc=1")
    assert r_toc.status_code == 200
    assert len(r_toc.get_json().get("chapters", [])) == 2
    assert "words" in r_toc.get_json()["chapters"][0]

    # 3. GET single chapter (0-based)
    r = client.get(f"/api/novels/{novel_stem}/chapter/0")
    assert r.status_code == 200
    ch_data = r.get_json()
    assert "第1章" in ch_data.get("title", "")
    assert "第一章的正文内容" in ch_data.get("content", "")

    # 4. POST save chapter (0-based)
    r = client.post(
        f"/api/novels/{novel_stem}/chapter/0",
        json={"title": "第1章 初见修改版", "content": "这是修改后的正文内容。"},
    )
    assert r.status_code == 200

    # 5. GET chapter history snapshot
    r = client.get(f"/api/novels/{novel_stem}/chapters/0/history")
    assert r.status_code == 200
    hist = r.get_json().get("snapshots", [])
    assert len(hist) >= 1

    # 6. POST restore snapshot
    snap_id = hist[0]["id"]
    r = client.post(
        f"/api/novels/{novel_stem}/chapters/0/restore-snapshot",
        json={"snapshot_id": snap_id},
    )
    assert r.status_code == 200

    # 7. POST selection assist (划词局部修润)
    with patch("app.chat", return_value=("润色选区后的内容", "stop")):
        r = client.post(
            f"/api/novels/{novel_stem}/selection-assist",
            json={"selected_text": "初见", "instruction": "扩写细节", "chapter_idx": 0},
        )
        assert r.status_code == 200

    # 8. POST search-replace
    r = client.post(
        f"/api/novels/{novel_stem}/search-replace",
        json={"find": "这是", "replace": "此乃", "chapter_indices": [0]},
    )
    assert r.status_code == 200

    # 9. POST realign-numbers
    r = client.post(f"/api/novels/{novel_stem}/realign-numbers")
    assert r.status_code == 200

    # 10. POST reorder-chapters
    r = client.post(
        f"/api/novels/{novel_stem}/reorder-chapters",
        json={"order": [1, 0]},
    )
    assert r.status_code == 200

    # 11. GET & POST bible (设定集)
    r = client.get(f"/api/novels/{novel_stem}/bible")
    assert r.status_code == 200
    r = client.post(
        f"/api/novels/{novel_stem}/bible",
        json={"bible": {"characters": [{"name": "主角A"}]}},
    )
    assert r.status_code == 200

    # 12. POST preferences
    r = client.post(
        f"/api/novels/{novel_stem}/preferences",
        json={"preferred_style": "轻快"},
    )
    assert r.status_code == 200

    # 13. GET export
    r = client.get(f"/api/novels/{novel_stem}/export?fmt=txt")
    assert r.status_code == 200

    # 14. POST rename
    r = client.post(f"/api/novels/{novel_stem}/rename", json={"title": "renamed_book"})
    assert r.status_code == 200
    novel_stem = "renamed_book"

    # 15. DELETE to trash & restore
    r = client.delete(f"/api/novels/{novel_stem}")
    assert r.status_code == 200

    r = client.get("/api/trash")
    assert r.status_code == 200
    assert any(item["file"] == f"{novel_stem}.md" for item in r.get_json())

    r = client.post(f"/api/trash/{novel_stem}/restore")
    assert r.status_code == 200

    # 16. POST rewrite chapter (runs async job)
    with patch("app.chat", return_value=("重写后的段落内容", "stop")):
        r = client.post(
            f"/api/novels/{novel_stem}/chapters/rewrite",
            json={"index": 0, "prompt": "改成更幽默的语调"},
        )
        assert r.status_code == 200


def test_import_txt_endpoint(client):
    txt_content = """第1卷 少年游
第1章 惊变
这是第一章的正文。

第2章 启程
这是第二章的正文。
"""
    r = client.post(
        "/api/novels/import-txt",
        json={"title": "导入测试书", "text": txt_content},
    )
    assert r.status_code == 200
    d = r.get_json()
    assert d.get("ok") is True


# ============================================================================
# 3. 灵感推演、续写与大模型辅助纯函数接口测试
# ============================================================================

def test_continuation_and_ideation_endpoints(client):
    # 1. POST /api/suggest-tropes
    with patch("app.chat", return_value=(json.dumps([{"title": "灵感1", "summary": "描述1"}]), "stop")):
        r = client.post("/api/suggest-tropes", json={"genre": "玄幻"})
        assert r.status_code == 200
        tropes = r.get_json().get("tropes", [])
        assert len(tropes) >= 1

    # 2. POST /api/suggest-titles
    fake_titles_json = json.dumps({"titles": ["书名一", "书名二"]})
    with patch("app.chat", return_value=(fake_titles_json, "stop")):
        r = client.post("/api/suggest-titles", json={"genre": "都市", "storyline": "创业历险"})
        assert r.status_code == 200
        titles = r.get_json().get("titles", [])
        assert len(titles) >= 1

    # 3. POST /api/refine-field (Legacy general field refiner)
    with patch("app.chat", return_value=("润色后的故事背景", "stop")):
        r = client.post(
            "/api/refine-field",
            json={"field": "setting", "mode": "polish", "genre": "科幻", "setting": "旧背景"},
        )
        assert r.status_code == 200
        assert r.get_json().get("text") == "润色后的故事背景"

    # 4. POST /api/generate (Continuation task)
    novel_stem = _init_test_novel("continuation_book")
    with patch("app.chat", return_value=("续写出的第三章内容", "stop")):
        r = client.post(
            "/api/generate",
            json={"mode": "continuation", "novel_name": novel_stem, "chapters": 1},
        )
        assert r.status_code == 200
        job_id = r.get_json().get("job_id")
        assert job_id

        # GET /api/jobs/<job_id>
        r_job = client.get(f"/api/jobs/{job_id}")
        assert r_job.status_code == 200


# ============================================================================
# 4. 原创小说创作 Studio (v2.0) 核心接口全链路测试
# ============================================================================

def test_original_studio_all_endpoints(client):
    spec = _sample_valid_spec()
    novel_id = "studio_full_test_novel"

    # 1. PUT & GET /api/novel/original/spec
    r_put = client.put("/api/novel/original/spec", json={"novel_id": novel_id, "spec": spec})
    assert r_put.status_code == 200
    assert r_put.get_json().get("code") == 200

    r_get = client.get(f"/api/novel/original/spec?novel_id={novel_id}")
    assert r_get.status_code == 200
    assert r_get.get_json().get("data")["spec"]["meta"]["title"] == "测试原创书"

    # 2. POST /api/novel/original/deduce
    fake_step1 = json.dumps({
        "logline": "推演的故事创意",
        "hook": "爽点",
        "reader_expectation": "期待",
        "theme": "立意",
        "tone": "叙事基调",
    })
    fake_step2 = json.dumps({
        "background": "世界观舞台",
        "special_rules": "规则",
        "taboos": "禁忌",
        "protagonist": {"id": "p1", "name": "新主角", "want": "目标", "need": "救赎", "flaw": "缺陷", "arc": "成长"},
        "characters": [],
    })
    fake_step3 = json.dumps({
        "climax_vision": "终局画面",
        "core_dilemma": "两难困境",
        "ultimate_cost": "牺牲代价",
        "resolution_tone": "结局余韵",
    })
    fake_step4 = json.dumps({
        "stages": [
            {
                "stage_index": 1,
                "title": "第 1 卷：启航",
                "expected_chapters": 4,
                "anchors": {
                    "stage_goal": "达成初识",
                    "main_obstacle": "阻碍",
                    "climax_hook": "小高潮",
                    "transition_springboard": "转折点",
                },
            }
        ]
    })

    with patch("original_studio.engine.chat", side_effect=[
        (fake_step1, "stop"),
        (fake_step2, "stop"),
        (fake_step3, "stop"),
        (fake_step4, "stop"),
    ]):
        r_deduce = client.post("/api/novel/original/deduce", json={
            "novel_id": novel_id,
            "title": "推演新书",
            "genre": "都市言情",
            "selected_trope": "合租契约",
        })
        assert r_deduce.status_code == 200
        deduced_data = r_deduce.get_json().get("data")
        assert deduced_data["ideation"]["logline"] == "推演的故事创意"
        assert deduced_data["protagonist"]["name"] == "新主角"

    # 3. POST /api/novel/original/refine-field (Universal SpecField Refiner)
    with patch("original_studio.engine.chat", return_value=("润色后的一句话创意", "stop")):
        r_refine = client.post("/api/novel/original/refine-field", json={
            "novel_id": novel_id,
            "field_path": "ideation.logline",
            "mode": "polish",
            "current_value": "原本的一句话创意",
            "user_hint": "加入更多推拉暧昧感",
        })
        assert r_refine.status_code == 200
        candidates = r_refine.get_json()["data"]["candidates"]
        assert len(candidates) >= 1
        assert candidates[0] == "润色后的一句话创意"

    # 4. POST /api/novel/original/stage/beats (Generate & Save)
    fake_beats = json.dumps({
        "beats": [
            {"chapter_offset": 1, "title": "第1章 意外同居", "beat_type": "setup", "summary": "被迫合租"},
            {"chapter_offset": 2, "title": "第2章 订立契约", "beat_type": "climax", "summary": "签署合约"},
        ]
    })
    with patch("original_studio.engine.chat", return_value=(fake_beats, "stop")):
        r_beats_gen = client.post("/api/novel/original/stage/beats", json={
            "novel_id": novel_id,
            "stage_index": 1,
            "action": "generate",
        })
        assert r_beats_gen.status_code == 200
        beats = r_beats_gen.get_json()["data"]["beats"]
        assert len(beats) == 2

        # Save edited beats
        beats[0]["title"] = "第1章 暴风雨的重逢"
        r_beats_save = client.post("/api/novel/original/stage/beats", json={
            "novel_id": novel_id,
            "stage_index": 1,
            "action": "save",
            "beats": beats,
        })
        assert r_beats_save.status_code == 200

    # 5. POST /api/novel/original/stage/start & control (Pause, Resume, Cancel)
    # Mocking generation generator inside runner with synchronization event
    fake_ch_content = "第1章正文内容...\n这是生成的详细情节。"
    import threading
    step_event = threading.Event()

    def mock_chat_generator(*args, **kwargs):
        step_event.wait(timeout=1.0)
        return (fake_ch_content, "stop")

    with patch("original_studio.engine.chat", side_effect=mock_chat_generator):
        r_start = client.post("/api/novel/original/stage/start", json={
            "novel_id": novel_id,
            "stage_index": 1,
        })
        assert r_start.status_code == 202
        job_id = r_start.get_json()["data"]["job_id"]
        assert job_id

        # GET /api/novel/original/stage/status/<job_id>
        r_status = client.get(f"/api/novel/original/stage/status/{job_id}")
        assert r_status.status_code == 200

        # GET /api/novel/original/stage/stream/<job_id> (SSE handshake)
        r_stream = client.get(f"/api/novel/original/stage/stream/{job_id}")
        assert r_stream.status_code == 200
        assert "text/event-stream" in r_stream.content_type

        # POST /api/novel/original/stage/control (pause & resume & cancel)
        r_pause = client.post("/api/novel/original/stage/control", json={"job_id": job_id, "action": "pause"})
        assert r_pause.status_code == 200

        r_resume = client.post("/api/novel/original/stage/control", json={"job_id": job_id, "action": "resume"})
        assert r_resume.status_code == 200

        r_cancel = client.post("/api/novel/original/stage/control", json={"job_id": job_id, "action": "cancel"})
        assert r_cancel.status_code == 200
        step_event.set()

    # 6. POST /api/novel/original/stage/checkpoint (Evaluate & Writeback)
    fake_eval = json.dumps({
        "goal_achievement_pct": 98,
        "deviation_summary": "阶段高潮按规划达成",
        "character_growth_notes": "男女主信任度提升",
    })
    with patch("original_studio.engine.chat", return_value=(fake_eval, "stop")):
        r_eval = client.post("/api/novel/original/stage/checkpoint", json={
            "novel_id": novel_id,
            "stage_index": 1,
            "action": "evaluate",
        })
        assert r_eval.status_code == 200
        assert r_eval.get_json()["data"]["goal_achievement_pct"] == 98

        r_wb = client.post("/api/novel/original/stage/checkpoint", json={
            "novel_id": novel_id,
            "stage_index": 1,
            "action": "accept_and_writeback",
            "spec_modifications": {
                "stages": spec["stages"] + [{
                    "stage_index": 2,
                    "title": "第 2 卷：推拉试探",
                    "expected_chapters": 4,
                    "anchors": {
                        "stage_goal": "假扮情侣",
                        "main_obstacle": "情敌介入",
                        "climax_hook": "酒会亲吻",
                        "transition_springboard": "心意坦白",
                    },
                }]
            },
        })
        assert r_wb.status_code == 200
        assert r_wb.get_json()["data"]["next_stage_index"] == 2
