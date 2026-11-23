"""Unit and integration tests for Original Novel Studio backend modules (Greenfield v2.0)."""

import json
from unittest.mock import patch

import pytest

from app import app
from original_studio.engine import (
    apply_checkpoint_writeback,
    deduce_creative_pipeline,
    evaluate_stage_checkpoint,
    generate_stage_beats,
    refine_spec_field,
)
from original_studio.models import (
    apply_locked_fields,
    default_runtime,
    get_markdown_path,
    get_runtime_path,
    get_spec_path,
    init_novel_three_layers,
    load_novel_runtime,
    load_novel_spec,
    save_novel_runtime,
    save_novel_spec,
    validate_runtime,
    validate_spec,
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    """配置隔离临时目录与测试 client。"""
    monkeypatch.setattr("app.NOVELS_DIR", tmp_path)
    monkeypatch.setattr("original_studio.models.NOVELS_DIR", tmp_path)
    monkeypatch.setattr("original_studio.engine.NOVELS_DIR", tmp_path)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _sample_valid_spec():
    return {
        "schema_version": "2.0.0",
        "locked_fields": ["protagonist.name"],
        "meta": {
            "title": "微醺心跳定律",
            "genre": "都市言情·甜宠",
            "selected_trope": "合租屋里的猫咪与合约情侣",
            "target_total_words": 150000,
            "target_stages_count": 4,
            "target_words_per_chapter": 2500,
        },
        "ideation": {
            "logline": "傲娇调酒师与失眠插画师的合租日常，契约恋爱假戏真做。",
            "hook": "猫咪误吞定情信物引发的同居契约",
            "reader_expectation": "高甜无虐、极致推拉、暧昧爆表",
            "theme": "在不确定的都市中，找到彼此治愈的安全感",
            "tone": "第三人称限制视角，轻快温馨细腻",
        },
        "worldview": {
            "background": "现代海滨城市，充满烟火气的梧桐老街与精酿清吧",
            "special_rules": "合租守则十二条：禁止在走廊越界、公区轮流喂猫",
            "taboos": "严禁对合约恋爱动真感情",
        },
        "protagonist": {
            "id": "char_protagonist",
            "name": "林眠",
            "role": "自由插画师",
            "want": "拥有一间带天窗的独立画室并按期办展",
            "need": "克服童年被遗弃阴影，学会信任他人",
            "flaw": "遇事习惯缩进壳里，极度害怕麻烦别人",
            "arc": "从敏感防备到勇敢向男主敞开心扉",
        },
        "characters": [
            {
                "id": "char_male_lead",
                "name": "陆沉舟",
                "relation_type": "cp_love",
                "role_desc": "深藏不露的清吧调酒老板",
                "bond_or_conflict": "表面冷硬毒舌，实则默默守护女主",
            }
        ],
        "ending": {
            "climax_vision": "初雪之夜的露天艺术展，男主以定制特调公开告白",
            "core_dilemma": "女主面临出国深造与留在身边的双向抉择",
            "ultimate_cost": "男主放下家族酒庄执念，共同开启独立工作室",
            "resolution_tone": "极尽浪漫温馨与微醺释然",
        },
        "stages": [
            {
                "stage_index": 1,
                "title": "第 1 卷：屋檐下的冰块与野猫",
                "expected_chapters": 6,
                "anchors": {
                    "stage_goal": "建立合租默契，签署同居契约",
                    "main_obstacle": "作息完全颠倒引发的生活习惯碰撞",
                    "climax_hook": "暴雨夜猫咪生病，两人在急诊室第一次坦诚身世",
                    "transition_springboard": "假扮男女朋友应付双方家长的考验",
                },
            }
        ],
    }


def test_spec_model_validation_and_storage(client):
    """测试 CreativeSpec 模型校验、三层文件落盘与锁定字段保护。"""
    spec = _sample_valid_spec()
    validated = validate_spec(spec)
    assert validated["meta"]["title"] == "微醺心跳定律"
    assert validated["protagonist"]["name"] == "林眠"

    # 必填缺失校验
    bad_spec = spec.copy()
    bad_spec["meta"] = {}
    with pytest.raises(ValueError):
        validate_spec(bad_spec)

    # 存储与读取
    novel_id = "sweet_love_001"
    save_novel_spec(novel_id, validated)
    loaded = load_novel_spec(novel_id)
    assert loaded is not None
    assert loaded["meta"]["title"] == "微醺心跳定律"

    # 锁定字段保护测试
    new_spec = _sample_valid_spec()
    new_spec["protagonist"]["name"] = "覆盖名字"
    preserved = apply_locked_fields(loaded, new_spec, locked_fields=["protagonist.name"])
    assert preserved["protagonist"]["name"] == "林眠", "已锁定的主角姓名不应被新推演覆盖"


def test_runtime_model_and_three_layers_init(client):
    """测试 Runtime 状态机校验与三层存储初始化。"""
    spec = _sample_valid_spec()
    runtime = default_runtime()
    assert runtime["status"] == "idle"

    # 校验合法性
    v_rt = validate_runtime(runtime)
    assert v_rt["status"] == "idle"

    # 初始化三层落盘
    novel_id = "test_three_layers"
    spec_p, runtime_p, md_p = init_novel_three_layers(novel_id, spec["meta"]["title"], spec, runtime)
    assert spec_p.exists()
    assert runtime_p.exists()
    assert md_p.exists()

    # 读取验证
    loaded_spec = load_novel_spec(novel_id)
    loaded_rt = load_novel_runtime(novel_id)
    assert loaded_spec["meta"]["title"] == "微醺心跳定律"
    assert loaded_rt["status"] == "idle"


def test_api_spec_crud(client):
    """测试 GET/PUT /api/novel/original/spec 接口。"""
    spec = _sample_valid_spec()
    novel_id = "api_spec_novel"

    # 1. 初始未保存时查询应返回 404
    r_get = client.get(f"/api/novel/original/spec?novel_id={novel_id}")
    assert r_get.status_code == 404

    # 2. 保存合规 spec
    r_put = client.put("/api/novel/original/spec", json={"novel_id": novel_id, "spec": spec})
    assert r_put.status_code == 200
    assert r_put.get_json()["code"] == 200

    # 3. 再次查询
    r_get2 = client.get(f"/api/novel/original/spec?novel_id={novel_id}")
    assert r_get2.status_code == 200
    assert r_get2.get_json()["data"]["spec"]["meta"]["title"] == "微醺心跳定律"

    # 4. 提交畸形 spec 校验应返回 400
    r_bad = client.put("/api/novel/original/spec", json={"novel_id": novel_id, "spec": {"meta": {}}})
    assert r_bad.status_code == 400


def test_api_refine_field_zero_disk_mutation(client, tmp_path):
    """测试 POST /api/novel/original/refine-field 字段级润色重写，并断言其具备 0 磁盘写盘副作用。"""
    files_before = set(tmp_path.glob("*"))

    mock_resp = "极度缺乏安全感引发的偏执防御；童年因信任孤儿院同伴导致义肢被剥夺。"
    with patch("original_studio.engine.chat", return_value=(mock_resp, "stop")):
        # 1. 重写模式
        payload_rewrite = {
            "novel_id": "none_exist_book",
            "field_path": "protagonist.flaw",
            "mode": "rewrite",
            "current_value": "过于自负",
            "user_hint": "加入孤儿院创伤",
            "spec_context": {"meta": {"title": "赛博道祖", "genre": "科幻修真"}},
        }
        res = client.post("/api/novel/original/refine-field", json=payload_rewrite)
        assert res.status_code == 200
        d = res.get_json()["data"]
        assert d["field_path"] == "protagonist.flaw"
        assert len(d["candidates"]) == 1
        assert "孤儿院" in d["candidates"][0]

        # 2. 润色模式（空内容应返回 400）
        res_empty = client.post("/api/novel/original/refine-field", json={
            "field_path": "protagonist.flaw",
            "mode": "polish",
            "current_value": "",
        })
        assert res_empty.status_code == 400

    # 铁律断言：执行字段级精修前后，磁盘文件数量与内容严禁发生任何变化
    files_after = set(tmp_path.glob("*"))
    assert files_before == files_after, "refine-field 必须为纯内存计算，严禁产生磁盘写盘副作用"


def test_api_deduce_endpoint(client):
    """测试 POST /api/novel/original/deduce 链式推演接口。"""
    fake_ideation = json.dumps({"logline": "一句话推演梗概", "hook": "爽点", "theme": "立意"})
    fake_world = json.dumps({"worldview": {"background": "背景"}, "protagonist": {"name": "推演主角", "want": "成仙"}})
    fake_ending = json.dumps({"climax_vision": "决胜高潮", "core_dilemma": "选择"})
    fake_stages = json.dumps({"stages": [{"stage_index": 1, "title": "第一卷", "anchors": {"stage_goal": "走出新手村"}}]})

    chat_responses = [
        (fake_ideation, "stop"),
        (fake_world, "stop"),
        (fake_ending, "stop"),
        (fake_stages, "stop"),
    ]

    with patch("original_studio.engine.chat", side_effect=chat_responses):
        res = client.post("/api/novel/original/deduce", json={
            "title": "赛博剑仙",
            "genre": "科幻修仙",
            "user_pitch": "现代九龙城寨里的剑修",
        })
        assert res.status_code == 200
        spec = res.get_json()["data"]
        assert spec["meta"]["title"] == "赛博剑仙"
        assert spec["protagonist"]["name"] == "推演主角"
        assert len(spec["stages"]) == 1


def test_api_stage_beats_lifecycle(client):
    """测试 POST /api/novel/original/stage/beats 节拍表推导与保存。"""
    spec = _sample_valid_spec()
    novel_id = "beats_test_novel"
    save_novel_spec(novel_id, spec)

    fake_beats_json = json.dumps({
        "beats": [
            {"chapter_offset": 1, "title": "第1章 不速之客", "beat_type": "setup", "summary": "相遇"},
            {"chapter_offset": 2, "title": "第2章 合约达成", "beat_type": "climax", "summary": "立约"},
        ]
    })

    with patch("original_studio.engine.chat", return_value=(fake_beats_json, "stop")):
        # 1. 生成节拍表
        r_gen = client.post("/api/novel/original/stage/beats", json={
            "novel_id": novel_id,
            "stage_index": 1,
            "action": "generate",
        })
        assert r_gen.status_code == 200
        beats = r_gen.get_json()["data"]["beats"]
        assert len(beats) == 2
        assert beats[0]["title"] == "第1章 不速之客"

        # 2. 作者手动编辑后保存
        beats[0]["title"] = "第1章 盛夏的骤雨"
        r_save = client.post("/api/novel/original/stage/beats", json={
            "novel_id": novel_id,
            "stage_index": 1,
            "action": "save",
            "beats": beats,
        })
        assert r_save.status_code == 200
        rt = load_novel_runtime(novel_id)
        assert rt["current_stage_beats"][0]["title"] == "第1章 盛夏的骤雨"


def test_api_stage_checkpoint_evaluate_and_writeback(client):
    """测试 POST /api/novel/original/stage/checkpoint 阶段偏差复盘与大纲回写。"""
    spec = _sample_valid_spec()
    novel_id = "checkpoint_novel"
    save_novel_spec(novel_id, spec)

    fake_report = json.dumps({
        "goal_achievement_pct": 95,
        "deviation_summary": "达成阶段高潮，男女主感情提前升温",
        "character_growth_notes": "女主更加信任男主",
    })

    with patch("original_studio.engine.chat", return_value=(fake_report, "stop")):
        # 1. 评估复盘
        r_eval = client.post("/api/novel/original/stage/checkpoint", json={
            "novel_id": novel_id,
            "stage_index": 1,
            "action": "evaluate",
        })
        assert r_eval.status_code == 200
        d = r_eval.get_json()["data"]
        assert d["goal_achievement_pct"] == 95

        # 2. 确认采纳回写
        new_stages = spec["stages"] + [{
            "stage_index": 2,
            "title": "第 2 卷：试探与蜜意",
            "expected_chapters": 6,
            "anchors": {
                "stage_goal": "假扮情侣进入社交圈",
                "main_obstacle": "情敌出现",
                "climax_hook": "酒会亲吻",
                "transition_springboard": "合约秘密险些曝光",
            },
        }]
        r_writeback = client.post("/api/novel/original/stage/checkpoint", json={
            "novel_id": novel_id,
            "stage_index": 1,
            "action": "accept_and_writeback",
            "spec_modifications": {"stages": new_stages},
        })
        assert r_writeback.status_code == 200
        updated_spec = load_novel_spec(novel_id)
        assert len(updated_spec["stages"]) == 2
        rt = load_novel_runtime(novel_id)
        assert rt["current_stage_index"] == 2
        assert rt["status"] == "idle"
