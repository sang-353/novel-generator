"""
tests/e2e/fake_llm_server.py - 本地独立假 LLM 服务
兼容 OpenAI /chat/completions 接口，支持普通模式与 SSE 流式输出，
可通过控制接口动态注入正常与异常响应。
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import urlparse


class FakeLLMState:
    """全局控制状态，用于指导假 LLM 返回正常或特定的异常数据。"""
    mode = "normal"  # normal, missing_fields, field_drift, top_level_array, malformed_json, empty
    custom_response = None
    call_history = []
    lock = threading.Lock()

    @classmethod
    def reset(cls):
        with cls.lock:
            cls.mode = "normal"
            cls.custom_response = None
            cls.call_history.clear()

    @classmethod
    def set_mode(cls, mode, custom_response=None):
        with cls.lock:
            cls.mode = mode
            cls.custom_response = custom_response


class FakeLLMHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # 静默日志，避免刷屏
        pass

    def _send_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def do_OPTIONS(self):
        self.send_response(200)
        self._send_cors()
        self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path.endswith("/chat/completions"):
            self.handle_chat_completions()
        elif parsed.path == "/mock/set_mode":
            self.handle_set_mode()
        elif parsed.path == "/mock/reset":
            FakeLLMState.reset()
            self.send_response(200)
            self._send_cors()
            self.end_headers()
            self.wfile.write(b'{"ok": true}')
        else:
            self.send_response(404)
            self.end_headers()

    def handle_set_mode(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        data = json.loads(body.decode("utf-8")) if body else {}
        FakeLLMState.set_mode(data.get("mode", "normal"), data.get("custom_response"))
        self.send_response(200)
        self._send_cors()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def handle_chat_completions(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        payload = json.loads(body.decode("utf-8")) if body else {}

        with FakeLLMState.lock:
            FakeLLMState.call_history.append(payload)
            mode = FakeLLMState.mode
            custom_response = FakeLLMState.custom_response

        messages = payload.get("messages", [])
        is_stream = bool(payload.get("stream", False))

        content = self._generate_response_content(messages, mode, custom_response)

        if is_stream:
            self.send_response(200)
            self._send_cors()
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()

            # 将 content 拆成若干 chunks 模拟流式推送
            chunk_size = max(5, len(content) // 4)
            for i in range(0, len(content), chunk_size):
                chunk = content[i : i + chunk_size]
                sse_data = {
                    "id": "chatcmpl-mock",
                    "object": "chat.completion.chunk",
                    "choices": [{"delta": {"content": chunk}, "index": 0}],
                }
                self.wfile.write(f"data: {json.dumps(sse_data, ensure_ascii=False)}\n\n".encode("utf-8"))
                self.wfile.flush()
                time.sleep(0.01)

            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            self.close_connection = True
        else:
            self.send_response(200)
            self._send_cors()
            self.send_header("Content-Type", "application/json")
            self.send_header("Connection", "close")
            self.end_headers()
            resp = {
                "id": "chatcmpl-mock",
                "object": "chat.completion",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                        "index": 0,
                    }
                ],
            }
            self.wfile.write(json.dumps(resp, ensure_ascii=False).encode("utf-8"))
            self.close_connection = True

    def _generate_response_content(self, messages, mode, custom_response):
        if custom_response:
            return custom_response

        # 检查是否为异常模拟模式
        if mode == "malformed_json":
            return "This is a malformed non-JSON response from LLM ```bad format"
        elif mode == "empty":
            return ""
        elif mode == "top_level_array":
            return '[{"title": "顶层数组书", "label": "测试标签", "genre": "都市", "icon": "💡"}]'
        elif mode == "field_drift":
            return '{"templates": [{"book_name": "字段漂移小说", "tag": "新标签", "category": "科幻"}]}'
        elif mode == "missing_fields":
            return '{"tropes": [{"unknown_key": "缺少核心字段"}]}'

        # 正常模式：根据提示词特征智能返回结构
        full_prompt = " ".join([m.get("content", "") for m in messages])

        if "世界观与角色设定集" in full_prompt or "generate-bible" in full_prompt:
            return json.dumps({
                "suggested_title": "星渊法则",
                "candidate_titles": ["星渊法则", "深空遗落", "机械神谕", "归零纪元"],
                "setting": "未来赛博与太空文明碰撞的时代，人类在太阳系边缘发现了远古遗迹。",
                "characters": [
                    {"name": "林越", "role": "拾荒者/破译官", "desc": "机警沉稳，擅长机械改造", "goal": "探寻父亲失踪真相"},
                    {"name": "零", "role": "仿生人向导", "desc": "外表冷漠，逻辑核心藏有秘密", "goal": "寻找自我意识起源"}
                ],
                "conflict": "旧人类势力与超级智脑的最终对决",
                "tone": "冷硬科幻，克制细腻，硬派悬疑"
            }, ensure_ascii=False)

        elif "章节大纲" in full_prompt or "outline" in full_prompt:
            return json.dumps({
                "logline": "一个拾荒者在边缘星系挖出史前遗迹，卷入星际阴谋的故事。",
                "chapters": [
                    {"title": "第1章 废墟拾荒", "points": "林越在废弃矿井遭遇磁暴，意外挖出一枚发光的古老金属核。"},
                    {"title": "第2章 隐秘追杀", "points": "赏金猎人追踪而至，林越被迫启动金属核，唤醒了沉睡的仿生人零。"},
                    {"title": "第3章 破晓逃亡", "points": "两人搭乘货船逃离空间站，智脑监控网全面收紧。"}
                ]
            }, ensure_ascii=False)

        elif "灵感开局" in full_prompt or "策划" in full_prompt or "suggest-tropes" in full_prompt:
            return json.dumps({
                "tropes": [
                    {
                        "icon": "⚡",
                        "label": "科幻悬疑·废土开局",
                        "title": "深空守望者",
                        "genre": "科幻未来",
                        "setting": "人类迁徙至地表地下城的第两百年。",
                        "characters": "主角楚风：巡逻警员，拥有感知机械共鸣的异能。",
                        "storyline": "巡逻时发现城市主供能塔被暗中植入了神秘代码，调查牵扯出建城元老的阴谋。",
                        "style": "硬朗快节奏，悬念拉满",
                        "perspective": "第三人称",
                        "chapters": 10,
                        "per_words": 2500
                    },
                    {
                        "icon": "💍",
                        "label": "都市轻熟·契约破局",
                        "title": "错位温度",
                        "genre": "都市言情",
                        "setting": "繁华都市商界与设计圈。",
                        "characters": "主角苏晚：新锐室内建筑师；男主顾明舟：投资人。",
                        "storyline": "因家族联姻协议同住屋檐下，在职场合作与生活碰撞中渐生情愫。",
                        "style": "细腻克制，拉扯感强",
                        "perspective": "第三人称",
                        "chapters": 10,
                        "per_words": 2500
                    }
                ]
            }, ensure_ascii=False)

        elif "剧情小样" in full_prompt or "variants" in full_prompt:
            return json.dumps({
                "variants": [
                    {
                        "id": "A",
                        "title": "顺承推进·潜行调查",
                        "synopsis": "跟随线索深入密室展开搜查",
                        "preview": "林越屏住呼吸，手指轻轻滑过金属闸门上的冷凝水珠。防盗面板上的红色警报灯闪烁不定，他取出一根纤细的接线针，悄然刺入了备用供电回路。"
                    },
                    {
                        "id": "B",
                        "title": "突发意外·警报骤响",
                        "synopsis": "突遭暗处巡逻队堵截打破潜行",
                        "preview": "空气中猛然响起尖锐的蜂鸣声！走廊尽头的重力隔离门瞬间锁死，两名手持脉冲震荡器的守卫从转角大踏步走出，刺目的探照灯直接打在林越脸上。"
                    }
                ]
            }, ensure_ascii=False)

        elif "拟定" in full_prompt and "书名" in full_prompt:
            return json.dumps({
                "titles": ["星渊法则", "深空遗落", "机械神谕", "归零纪元", "破晓序列", "深空彼岸"]
            }, ensure_ascii=False)

        elif "改写" in full_prompt or "精修" in full_prompt or "selection-assist" in full_prompt:
            return "【AI 润色优化正文】林越凝神细听，阴冷潮湿的风顺着金属甬道深处灌入，空气中弥漫着刺鼻的臭氧与机油焦味。他握紧手中的扳手，指节因用力而微微泛白。"

        # 默认正文生成输出
        return (
            "晨光撕破了晨雾，整座太空基地的轮廓在金红色的霞光中逐渐清晰。\n\n"
            "林越站在舷窗前，凝视着脚下缓缓旋转的蔚蓝星球。这颗曾孕育了人类文明的故土，如今只剩下沉默与荒芜。\n\n"
            "通讯终端发出滴滴轻响，一条最高优先级的加密讯息自动展开在视网膜投影上——「代号：深潜者已苏醒，请立即前往甲板集结」。"
        )


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class FakeLLMServer:
    def __init__(self, port=0):
        self.server = ThreadedHTTPServer(("127.0.0.1", port), FakeLLMHandler)
        self.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        try:
            t = threading.Thread(target=self.server.shutdown, daemon=True)
            t.start()
            t.join(timeout=2.0)
            self.server.server_close()
        except Exception:
            pass
