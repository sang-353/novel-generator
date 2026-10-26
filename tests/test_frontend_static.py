# -*- coding: utf-8 -*-
"""前端静态检查测试（用 pytest 实现，不引入外部依赖）

1. 解析 static/index.html 收集所有元素 id。
2. 扫描 static/js/*.js 中所有通过 $('id')、getElementById('id')、on('id', ...) 引用的 id。
3. 断言：JS 中引用的每个 id 在 HTML 中都存在（允许白名单，注明原因）。
4. 断言：不存在裸写的 $('xxx').onclick/onchange/oninput = ... 或 $('xxx').addEventListener(...)，必须使用安全绑定函数 on() 或有 null 守护。
5. 检查 HTML 中是否存在重复 id。
6. 对每个 js 文件执行 node --check（如果本机有 node，否则跳过并提示）。
"""

import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
HTML_PATH = ROOT_DIR / "static" / "index.html"
JS_DIR = ROOT_DIR / "static" / "js"

# 动态生成的 DOM 元素白名单（每项注明生成位置与原因）
DYNAMIC_ID_WHITELIST = {
    # 动态创建的章节编辑组件，在 reader.js:enterChapterEdit() 中进入编辑模式时渲染
    "rd_edit_body_inp": "在 reader.js:enterChapterEdit() 动态进入编辑模式时渲染的正文编辑 textarea",
    "rd_edit_title_inp": "在 reader.js:enterChapterEdit() 动态进入编辑模式时渲染的标题 input",
    "rd_edit_words_live": "在 reader.js:enterChapterEdit() 动态进入编辑模式时渲染的实时字数计数 span",
    "rd_edit_save_btn": "在 reader.js:enterChapterEdit() 动态进入编辑模式时渲染的保存修改 button",
    "rd_edit_cancel_btn": "在 reader.js:enterChapterEdit() 动态进入编辑模式时渲染的取消编辑 button",
    # 动态创建的章节底部导航按钮，在 reader.js:renderChapter() 中正文末尾渲染
    "rd_prev_bottom": "在 reader.js:renderChapter() 中动态注入章节末尾的「上一章」按钮",
    "rd_next_bottom": "在 reader.js:renderChapter() 中动态注入章节末尾的「下一章」按钮",
    # 历史兼容别名
    "rd_edit_input": "历史遗留兼容别名，在 reader.js 中作为 rd_edit_body_inp 的降级判断",
    "rd_bible_btn": "历史兼容别名，在 reader.js:1143 兼容旧桌面栏设定集入口（移动端为 rd_bible_btn_m）",
}


class HTMLIDParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.duplicates = []

    def handle_starttag(self, tag, attrs):
        for attr, val in attrs:
            if attr.lower() == "id" and val:
                v = val.strip()
                if v in self.ids:
                    self.duplicates.append((v, tag))
                self.ids.add(v)


def get_html_ids():
    assert HTML_PATH.exists(), f"找不到 {HTML_PATH}"
    parser = HTMLIDParser()
    content = HTML_PATH.read_text(encoding="utf-8")
    parser.feed(content)
    return parser.ids, parser.duplicates


def test_html_no_duplicate_ids():
    """检查 HTML 中是否存在重复 id"""
    ids, duplicates = get_html_ids()
    assert len(duplicates) == 0, f"HTML 中存在重复 ID: {duplicates}"
    assert len(ids) > 0, "未能解析到任何 HTML ID"


def test_js_referenced_ids_exist_in_html():
    """扫描 static/js/*.js 中引用的 id，断言在 HTML 或动态白名单中存在"""
    html_ids, _ = get_html_ids()
    js_files = sorted(JS_DIR.glob("*.js"))
    assert len(js_files) > 0, "未能找到 static/js/*.js 文件"

    id_patterns = [
        re.compile(r"\$\(\s*['\"]([a-zA-Z0-9_\-]+)['\"]\s*\)"),
        re.compile(r"document\.getElementById\(\s*['\"]([a-zA-Z0-9_\-]+)['\"]\s*\)"),
        re.compile(r"on\(\s*['\"]([a-zA-Z0-9_\-]+)['\"]"),
    ]

    missing_ids = {}
    for js_file in js_files:
        code = js_file.read_text(encoding="utf-8")
        lines = code.splitlines()
        for line_idx, line in enumerate(lines, 1):
            # 排除注释行
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("*"):
                continue

            for pat in id_patterns:
                for match in pat.finditer(line):
                    ref_id = match.group(1)
                    if ref_id not in html_ids and ref_id not in DYNAMIC_ID_WHITELIST:
                        missing_ids.setdefault(ref_id, []).append(f"{js_file.name}:{line_idx}")

    assert len(missing_ids) == 0, f"发现 JS 引用的 ID 在 HTML 中不存在且未在白名单中: {missing_ids}"


def test_no_naked_event_bindings():
    """断言不存在裸写的 $('xxx').onclick/onchange/oninput = ... 或 $('xxx').addEventListener(...)

    必须使用安全绑定函数 on() 或有显式判空防护（例如 if ($(id)) ... 或 const el = $(id); if (el) ...）
    """
    js_files = sorted(JS_DIR.glob("*.js"))
    naked_bindings = []

    # 匹配 $('xxx').onclick = ... 或 $('xxx').addEventListener(...)
    # 注意避免匹配已带 if 前缀的单行判断，如 if ($('xxx')) $('xxx').onclick = ...
    naked_dollar_pattern = re.compile(
        r"(\$\(\s*['\"][^'\"]+['\"]\s*\)\.(?:on[a-z]+|addEventListener)\s*(?:=|\())"
    )

    for js_file in js_files:
        code = js_file.read_text(encoding="utf-8")
        lines = code.splitlines()
        for line_idx, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("*"):
                continue

            # 如果该行包含裸写
            match = naked_dollar_pattern.search(line)
            if match:
                # 检查该行自身是否有 if 守卫
                if "if (" in line or "if(" in line:
                    continue
                # 记录裸写位置
                naked_bindings.append(f"{js_file.name}:{line_idx} -> {stripped}")

    assert len(naked_bindings) == 0, f"发现裸写事件绑定（易因元素缺失导致全站 JS 崩溃），请改用 on() 或加 null 防护:\n" + "\n".join(naked_bindings)


def test_node_check_js_syntax():
    """对每个 js 文件执行 node --check（如果本机有 node，否则跳过并提示）"""
    node_exe = shutil.which("node")
    if not node_exe:
        pytest.skip("未在系统 PATH 中找到 node 可执行文件，跳过语法静态检查")

    js_files = sorted(JS_DIR.glob("*.js"))
    for js_file in js_files:
        res = subprocess.run([node_exe, "--check", str(js_file)], capture_output=True, text=True)
        assert res.returncode == 0, f"{js_file.name} 存在 JS 语法错误:\n{res.stderr}"
