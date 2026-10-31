import pytest
import json
import re
from pathlib import Path
import app as app_module
from app import app, parse_novel, write_novel

@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c

def test_volume_parsing_and_writing(tmp_path):
    p = tmp_path / "test_vol.md"
    meta = {"title": "分卷测试", "type": "original"}
    chapters = [
        {"title": "第一章 始动", "content": "这是第一卷的第一章正文。", "volume": "第一卷 崛起"},
        {"title": "第二章 进阶", "content": "这是第一卷的第二章正文。", "volume": "第一卷 崛起"},
        {"title": "第三章 破境", "content": "这是第二卷的第三章正文。", "volume": "第二卷 争锋"},
    ]
    write_novel(p, meta, chapters)
    
    parsed_meta, parsed_chapters, words = parse_novel(p, repair=False)
    assert len(parsed_chapters) == 3
    assert parsed_chapters[0]["volume"] == "第一卷 崛起"
    assert parsed_chapters[1]["volume"] == "第一卷 崛起"
    assert parsed_chapters[2]["volume"] == "第二卷 争锋"
    assert words > 0

def test_reorder_chapters_and_volumes(client):
    book_name = "test_reorder_book"
    p = app_module.NOVELS_DIR / f"{book_name}.md"
    meta = {"title": "重排序测试", "type": "original"}
    chapters = [
        {"title": "第1章", "content": "内容一", "volume": "第一卷"},
        {"title": "第2章", "content": "内容二", "volume": "第一卷"},
        {"title": "第3章", "content": "内容三", "volume": "第一卷"},
    ]
    write_novel(p, meta, chapters)

    try:
        # Reorder chapters to [2, 0, 1] with new volumes
        res = client.post(f"/api/novels/{book_name}/reorder-chapters", json={
            "order": [
                {"index": 2, "volume": "第二卷", "title": "第3章 (提前)"},
                {"index": 0, "volume": "第一卷"},
                {"index": 1, "volume": "第一卷"}
            ]
        })
        assert res.status_code == 200
        data = res.get_json()
        assert data["ok"] is True
        assert data["count"] == 3

        # Verify on disk
        _, updated_chapters, _ = parse_novel(p, repair=False)
        assert updated_chapters[0]["title"] == "第3章 (提前)"
        assert updated_chapters[0]["content"] == "内容三"
        assert updated_chapters[0]["volume"] == "第二卷"
        assert updated_chapters[1]["title"] == "第1章"
        assert updated_chapters[2]["title"] == "第2章"
    finally:
        if p.exists():
            p.unlink()

def test_chapter_history_and_restore(client):
    book_name = "test_history_book"
    p = app_module.NOVELS_DIR / f"{book_name}.md"
    meta = {"title": "历史快照测试", "type": "original"}
    chapters = [
        {"title": "第1章 初稿", "content": "这是最初版本的内容，十分质朴。"}
    ]
    write_novel(p, meta, chapters)

    try:
        # Edit chapter to trigger backup
        res_edit = client.post(f"/api/novels/{book_name}/chapters/0", json={
            "title": "第1章 修改版",
            "content": "这是修改后的第二版内容，添加了许多新细节。"
        })
        assert res_edit.status_code == 200

        # Query history
        res_hist = client.get(f"/api/novels/{book_name}/chapters/0/history")
        assert res_hist.status_code == 200
        hist_data = res_hist.get_json()
        assert hist_data["ok"] is True
        assert len(hist_data["snapshots"]) >= 1
        snapshot = hist_data["snapshots"][0]
        assert "最初版本" in snapshot["content"]

        # Restore snapshot
        res_restore = client.post(f"/api/novels/{book_name}/chapters/0/restore-snapshot", json={
            "snapshot_id": snapshot["id"]
        })
        assert res_restore.status_code == 200
        restore_data = res_restore.get_json()
        assert "最初版本" in restore_data["content"]

        # Verify on disk
        _, cur_chapters, _ = parse_novel(p, repair=False)
        assert "最初版本" in cur_chapters[0]["content"]
    finally:
        if p.exists():
            p.unlink()

def test_import_txt_novel(client):
    raw_txt = """
    这是小说导入的前言说明。

    第一章 灵气复苏
    林风站在天台之上，看着血月悬空。世界变了。

    第二章 签到系统激活
    叮，恭喜宿主激活超神签到系统。
    获得神级新手大礼包一份。

    第三章 初试锋芒
    夜色如墨，黑影袭来。林风抬手一拳，拳风呼啸。
    """
    res = client.post("/api/novels/import-txt", json={
        "title": "导入测试书目",
        "genre": "玄幻修真",
        "text": raw_txt
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    book_name = data["name"]
    assert data["chapters_count"] >= 3
    assert data["total_words"] > 0

    p = app_module.NOVELS_DIR / f"{book_name}.md"
    bible_p = app_module.NOVELS_DIR / f"{book_name}.bible.json"
    try:
        assert p.exists()
        assert bible_p.exists()
        _, chs, _ = parse_novel(p, repair=False)
        assert len(chs) >= 3
        assert "第一章" in chs[0]["title"] or "序章" in chs[0]["title"]
    finally:
        if p.exists():
            p.unlink()
        if bible_p.exists():
            bible_p.unlink()

def test_search_and_replace(client):
    book_name = "test_sr_book"
    p = app_module.NOVELS_DIR / f"{book_name}.md"
    meta = {"title": "全局替换测试", "type": "original"}
    chapters = [
        {"title": "第1章", "content": "张三看了李四一眼，张三笑了。"},
        {"title": "第2章", "content": "李四对张三说：此去凶险。"},
    ]
    write_novel(p, meta, chapters)

    try:
        # 1. Preview only
        res_prev = client.post(f"/api/novels/{book_name}/search-replace", json={
            "find": "张三",
            "replace": "叶凡",
            "preview_only": True
        })
        assert res_prev.status_code == 200
        prev_data = res_prev.get_json()
        assert prev_data["preview_only"] is True
        assert prev_data["total_matches"] == 3
        assert prev_data["modified_chapters"] == 2

        # Verify not yet modified on disk
        _, chs_before, _ = parse_novel(p, repair=False)
        assert "张三" in chs_before[0]["content"]

        # 2. Execute replacement
        res_exec = client.post(f"/api/novels/{book_name}/search-replace", json={
            "find": "张三",
            "replace": "叶凡",
            "preview_only": False
        })
        assert res_exec.status_code == 200
        exec_data = res_exec.get_json()
        assert exec_data["preview_only"] is False
        assert exec_data["total_matches"] == 3

        # Verify modified on disk
        _, chs_after, _ = parse_novel(p, repair=False)
        assert "叶凡" in chs_after[0]["content"]
        assert "张三" not in chs_after[0]["content"]
    finally:
        if p.exists():
            p.unlink()

def test_prompt_settings_and_novel_preferences(client):
    # Test prompt settings
    res = client.get("/api/settings/prompts")
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert "zhihu" in data["templates"]
    assert "qidian" in data["templates"]
    assert "jjwx" in data["templates"]
    assert "fanqie" in data["templates"]

    # Save prompt settings
    res_save = client.post("/api/settings/prompts", json={
        "active": "zhihu",
        "custom_template": {
            "id": "my_custom",
            "name": "我的定制流",
            "instruction": "注重人物对白幽默反讽。"
        }
    })
    assert res_save.status_code == 200
    save_data = res_save.get_json()
    assert save_data["active"] == "zhihu"
    assert "my_custom" in save_data["templates"]

    # Reset active to default
    client.post("/api/settings/prompts", json={"active": "default"})

    # Test novel preferences
    book_name = "test_pref_book"
    p = app_module.NOVELS_DIR / f"{book_name}.md"
    meta = {"title": "偏好测试", "type": "original"}
    write_novel(p, meta, [{"title": "第1章", "content": "正文"}])
    try:
        res_pref = client.post(f"/api/novels/{book_name}/preferences", json={
            "preferred_style_template": "qidian",
            "preferred_perspective": "第三人称",
            "preferred_words": 2000
        })
        assert res_pref.status_code == 200
        pref_data = res_pref.get_json()
        assert pref_data["meta"]["preferred_style_template"] == "qidian"

        # Verify on disk
        meta_disk, _, _ = parse_novel(p, repair=False)
        assert meta_disk["preferred_style_template"] == "qidian"
    finally:
        if p.exists():
            p.unlink()


def test_realign_chapter_numbers_api(client):
    """测试一键章节序号重排与对齐 API：消除跳号与重复号，保持副标题与正文首行同步。"""
    book_name = "test_realign_book"
    p = app_module.NOVELS_DIR / f"{book_name}.md"
    meta = {"title": "序号对齐测试书", "type": "original"}
    initial_chapters = [
        {"title": "第1章 暴雨夜", "content": "第1章 暴雨夜\n第一章正文。"},
        {"title": "第2章 码头暗账", "content": "第2章 码头暗账\n第二章正文。"},
        {"title": "第7章 废纸袋", "content": "第7章 废纸袋\n第三章正文（原跳号到7）。"},
        {"title": "第7章 废纸袋", "content": "第7章 废纸袋\n第四章正文（原重复第7章）。"},
        {"title": "第10章 领带与刀锋", "content": "第10章 领带与刀锋\n第五章正文。"},
    ]
    write_novel(p, meta, initial_chapters)
    try:
        res = client.post(f"/api/novels/{book_name}/realign-numbers")
        assert res.status_code == 200
        data = res.get_json()
        assert data["ok"] is True
        assert data["changed_count"] >= 3

        meta_disk, chapters_disk, _ = parse_novel(p, repair=False)
        expected_titles = [
            "第1章 暴雨夜",
            "第2章 码头暗账",
            "第3章 废纸袋",
            "第4章 废纸袋",
            "第5章 领带与刀锋",
        ]
        actual_titles = [c["title"] for c in chapters_disk]
        assert actual_titles == expected_titles, f"重排后标题不匹配: {actual_titles}"

        # 断言正文首行也同步平移重命名
        assert chapters_disk[2]["content"].startswith("第3章 废纸袋")
        assert chapters_disk[3]["content"].startswith("第4章 废纸袋")
        assert chapters_disk[4]["content"].startswith("第5章 领带与刀锋")
    finally:
        if p.exists():
            p.unlink()


def test_batch_delete_chapters_api(client):
    """测试章节批量删除 API：支持多选删除、原作保护与自动重排序号。"""
    book_name = "test_batch_del_book"
    p = app_module.NOVELS_DIR / f"{book_name}.md"
    meta = {"title": "批量删除测试书", "type": "original", "original_count": 1}
    initial_chapters = [
        {"title": "原作", "content": "原作正文。"},
        {"title": "第1章 发展", "content": "第1章 发展\n内容1。"},
        {"title": "第2章 废章A", "content": "第2章 废章A\n内容2。"},
        {"title": "第3章 推进", "content": "第3章 推进\n内容3。"},
        {"title": "第4章 废章B", "content": "第4章 废章B\n内容4。"},
        {"title": "第5章 决战", "content": "第5章 决战\n内容5。"},
    ]
    write_novel(p, meta, initial_chapters)
    try:
        # 1. 尝试删除原作章节（下标 0），应被拒绝 400
        res_deny = client.post(f"/api/novels/{book_name}/chapters/batch-delete", json={
            "indices": [0, 2],
            "auto_realign": True
        })
        assert res_deny.status_code == 400
        assert "原作章节不可删除" in res_deny.get_json()["error"]

        # 2. 正确批量删除第 2 章废章A（下标 2）与第 4 章废章B（下标 4）
        res_ok = client.post(f"/api/novels/{book_name}/chapters/batch-delete", json={
            "indices": [2, 4],
            "auto_realign": True
        })
        assert res_ok.status_code == 200
        data = res_ok.get_json()
        assert data["ok"] is True
        assert data["deleted_count"] == 2
        assert data["remaining_count"] == 4

        # 3. 校验磁盘落盘情况
        meta_disk, chapters_disk, _ = parse_novel(p, repair=False)
        assert len(chapters_disk) == 4
        # 原作保留在 0
        assert chapters_disk[0]["title"] == "原作"
        # 剩余章节序号自动平移对齐为第 1 章、第 2 章、第 3 章
        expected_titles = ["原作", "第1章 发展", "第2章 推进", "第3章 决战"]
        actual_titles = [c["title"] for c in chapters_disk]
        assert actual_titles == expected_titles, f"批量删除后重排不符: {actual_titles}"
    finally:
        if p.exists():
            p.unlink()


