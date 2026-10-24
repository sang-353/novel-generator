# -*- coding: utf-8 -*-
"""gunicorn 配置 —— 小说生成器在 Linux 服务器上的运行参数。

这里的每个值都跟 app.py 的实现绑死，改之前先看理由：

* workers = 1
  app.py 把「生成任务进度 JOBS」「隐私书架解锁令牌 PRIVACY_TOKENS」
  「同一本书的生成锁 ACTIVE_BOOKS」全部存在 **进程内存** 里。
  多 worker 时，轮询进度/取消任务/解锁状态会随机落到另一个进程而查不到，
  表现为「进度条卡住不动」「密码输对了却说没解锁」。所以永远不要加 worker。

* worker_class = "gthread" + threads
  单进程下必须靠线程并发，否则一个「通读全书」请求会把整个服务冻住。
  （app.py 里的后台生成任务本身也是 threading.Thread。）

* timeout = 900
  app.py 里 chat() 的默认请求超时是 300s，同步接口 /api/outline、/api/analyze-style
  一次请求最长会阻塞 300s 以上；gunicorn 默认 30s 会把 worker 直接杀掉。

* max_requests = 0
  不做周期性重启 —— 重启会清空内存里的任务状态，正在生成的书会被标记为「生成中断」。
"""
import os

# 项目根目录：由 systemd 的 Environment=NOVEL_APP_DIR= 传入
APP_DIR = os.environ.get("NOVEL_APP_DIR", "/opt/novel-generator")
chdir = APP_DIR

# 监听地址。公网直连：0.0.0.0:8000；若前面加了 nginx 反代：127.0.0.1:8000
bind = os.environ.get("NOVEL_BIND", "0.0.0.0:8000")

# ---- 并发：必须单进程 ----
workers = 1
worker_class = "gthread"
# 内存紧张的小机器（512MB）建议降到 4：
# 每次导出/解析会整本读进内存，那本 19MB 的书单次请求峰值约 40-60MB。
threads = int(os.environ.get("NOVEL_THREADS", "8"))

# ---- 超时 ----
timeout = 900
graceful_timeout = 60
keepalive = 5

# 不自动重启 worker
max_requests = 0

# 日志进 stdout/stderr，由 systemd 收进 journald：journalctl -u novel-generator -f
accesslog = "-"
errorlog = "-"
loglevel = "info"

proc_name = "novel-generator"

# gunicorn 26 默认会开一个「控制套接字」（给 gunicornc 做运行时管理），
# 路径优先取 $XDG_RUNTIME_DIR，取不到就落到 $HOME 下。systemd 单元里开了 ProtectHome=true，
# $HOME 不可访问，于是每次启动都刷一条：
#   [ERROR] Control server error: [Errno 13] Permission denied: '/home/novelgen'
# 这个应用被硬性限制成单 worker（见文件开头），运行时扩缩容没有意义，重启交给 systemd，
# 所以直接关掉。真要启用 gunicornc，删掉下面这行，并在 novel-generator.service 里加：
#   RuntimeDirectory=novel-generator
#   Environment=XDG_RUNTIME_DIR=/run/novel-generator
#   ReadWritePaths=-/run/novel-generator
control_socket_disable = True
