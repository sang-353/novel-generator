# 部署到 Ubuntu 26.04（公网 IP 直连 + 云安全组白名单）

> 面向的方案：**公网 IP 直连 8000 端口，用云控制台的「安全组」把自己的出口 IP 加白**，数据整机迁移。
> 如果你后来想加密流量，看第 5 节的 nginx 方案（`deploy/nginx-novel-generator.conf.example`）。

---

## 0. 一句话结论

代码本身很好部署（纯 Python、两个依赖、无构建步骤、无数据库）。**真正要做的事只有三类：**

1. **跑起来**：传到服务器 → 建 venv 装依赖 → systemd 托管 → 开机自启。`deploy/` 里三个文件全干完。
2. **数据搬过去**：`novels/`（含那本 19MB 的续写）+ `config.json`（明文 API Key + 隐私密码哈希）。
3. **别裸奔在公网上**：项目**没有账号体系**，安全组白名单是唯一一道门；再加备份、权限收紧、SSH 加固。

用脚本的话，服务器上是这两步：

```powershell
# 在你自己的 Windows 机器上（项目根目录）
pwsh -File deploy\deploy.ps1 -Server <服务器公网IP> -WithData
```

> ⚠️ 我无法在这里连接你的服务器实测这两个脚本（本机沙箱不允许执行 bash / 建 SSH 连接）。
> PowerShell 脚本过了语法解析，bash 脚本是逐行审过的。**第一次跑请盯着输出**，
> 哪一步报错就按第 7 节的手动命令逐步来。

---

## 1. 服务器准备

### 1.1 选规格

| 项目 | 建议 | 原因 |
| --- | --- | --- |
| 内存 | **1 GB 起，2 GB 舒服** | 导出 / 分析会把整本小说读进内存解析，19MB 的书单次请求峰值约 40–60 MB，8 个线程并发时更明显 |
| CPU | 1–2 核 | 没有本地推理，全部算力在大模型 API 那边 |
| 磁盘 | 20 GB | 代码 50MB，小说和章节快照会持续长 |
| 系统 | Ubuntu 26.04 LTS x86_64 | 纯 Python 依赖，没有平台相关代码 |

内存只有 512 MB 的话，把 `deploy/gunicorn.conf.py` 里的 `threads` 降到 4。

### 1.2 云控制台安全组（**最关键的一步**）

| 方向 | 协议 | 端口 | 来源 |
| --- | --- | --- | --- |
| 入站 | TCP | 22 | 你的出口 IP（别开 0.0.0.0/0） |
| 入站 | TCP | **8000** | **只填你的出口 IP** |
| 入站 | 其他 | — | 全部删除（尤其是云厂商默认的 80/443/3306 全开规则） |

出口 IP 用 <https://ifconfig.me> 查。家宽 IP 会变，变了要回控制台改——**这是这套方案唯一的运维负担**，
嫌烦就换成 Tailscale（见第 5 节末尾）。

### 1.3 系统与 SSH 加固

```bash
sudo apt update && sudo apt upgrade -y
lsb_release -a          # 确认是 26.04
python3 -V              # 记下版本，后面 venv 用它
```

SSH 改成只用密钥（**先确认密钥能登录，再关密码登录，别把自己锁在门外**）：

```bash
# 本机：把公钥推上去（Windows 在 PowerShell 里跑）
type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh root@<IP> "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"

# 服务器：改配置
sudo sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
sudo systemctl restart ssh
```

可选但推荐（公网 22 端口天天被扫）：

```bash
sudo apt install -y fail2ban && sudo systemctl enable --now fail2ban
```

---

## 2. 上传代码并初始化

### 方式 A：用脚本（推荐）

```powershell
cd E:\code\Agents\novel-generator

# 首次部署：代码 + novels/ + config.json 一起传
pwsh -File deploy\deploy.ps1 -Server 1.2.3.4 -WithData

# 以后每次改完代码，只更新代码（默认不碰服务器上的小说数据）
pwsh -File deploy\deploy.ps1 -Server 1.2.3.4
```

脚本做的事：本机打包 → `scp` 到 `/tmp` → 解开到 `/opt/novel-generator` → 执行服务器上的
`deploy/setup-server.sh`（装着环境、起 systemd、配 ufw 和每日备份）→ 自检 `HTTP 200`。

参数：`-User`（默认 root）`-SshPort`（默认 22）`-AppDir`（默认 `/opt/novel-generator`）`-AppPort`（默认 8000）`-UploadOnly`。

### 方式 B：手动（脚本不对时照这个来）

```bash
# 服务器上
sudo mkdir -p /opt/novel-generator
```

```powershell
# Windows 上：打包（自动排除 pylibs 等 Windows 专用文件）
cd E:\code\Agents\novel-generator
tar -czf $env:TEMP\novel.tgz --exclude=pylibs --exclude=wheels --exclude=.tmp `
    --exclude=__pycache__ --exclude=.pytest_cache --exclude=.idea `
    app.py requirements.txt README.md static tests deploy novels config.json
scp $env:TEMP\novel.tgz root@1.2.3.4:/tmp/
```

```bash
# 服务器上
sudo tar -xzf /tmp/novel.tgz -C /opt/novel-generator
sudo bash /opt/novel-generator/deploy/setup-server.sh
```

### 部署后的目录

```
/opt/novel-generator/
├── app.py                   后端（Flask）
├── static/index.html        前端单页
├── novels/                  ← 你的小说数据（唯一真相在服务器上）
│   ├── *.md
│   └── _trash/              回收站 + 章节快照
├── analysis_cache/          通读分析缓存
├── config.json              600 权限：明文 API Key + 隐私密码哈希
├── deploy/                  systemd 单元、gunicorn 配置、部署与备份脚本
└── .venv/                   虚拟环境
```

---

## 3. 五个必须知道的坑（都跟这个项目的实现有关）

### 3.1 必须单进程，永远不要加 worker

`app.py` 把生成任务进度（`JOBS`）、隐私解锁令牌（`PRIVACY_TOKENS`）、同书生成锁（`ACTIVE_BOOKS`）
全放在**进程内存**里。多 worker 时，轮询进度的请求会随机落到别的进程，表现是
「进度条卡住不动」「密码输对了却说没解锁」「同一本书并发写坏」。
`deploy/gunicorn.conf.py` 里已经锁死 `workers = 1`，**别改**。要提并发就加 `threads`。

### 3.2 单个请求最长会阻塞 300 秒

`chat()` 的默认超时是 `300` 秒（`app.py:205`），而 `/api/outline`、`/api/analyze-style`
是**同步**接口，会一直占着这个请求。gunicorn 默认超时 30 秒会把 worker 直接杀掉，
所以配置里是 `timeout = 900`。这也是为什么用 `gthread` 而不是单线程 sync worker——
否则一个人点「生成大纲」，页面其他操作全卡死。

### 3.3 `pylibs/` 绝对不能传上去

本机 `pylibs/` 是给 Windows 沙箱环境用的（22MB，里面有 `*.pyd`：`markupsafe\_speedups.cp314-win_amd64.pyd`、
`charset_normalizer\*.cp314-win_amd64.pyd`）。`app.py` 第 26–28 行会把它插到 `sys.path` **最前面**，
到了 Linux 上这些二进制加载不了，还会**顶掉 venv 里的正常包**。
`deploy.ps1` 默认不打包它，`setup-server.sh` 发现它存在会直接 `rm -rf`。

### 3.4 `pylibs/` 里的 pip 安装方式不要照搬

`安装并启动.bat` / `tools/install.ps1` 是绕 Windows 沙箱权限的产物（`pip install --target pylibs`）。
Linux 上正常用 venv：`python3 -m venv .venv`。根目录那几个 `.bat` 和 `tools\*.ps1` 在服务器上没用。

### 3.5 数据库？没有

不用装 MySQL / PostgreSQL / Redis。数据就是 `novels/` 里的 Markdown 和 `config.json`。
迁移 = 拷这两个。

---

## 4. 数据迁移与备份

### 4.1 首次迁移

- `novels/`：`未命名小说.md`(37KB)、`只想每天被姐姐惩罚·续写.md`(19MB)、`_trash/`（回收站与章节快照）
- `config.json`：2 个 provider 的**明文 API Key**、`active_provider`、隐私密码的 salt/hash/iterations

`deploy.ps1 -WithData` 会自动带上这两个。迁移后确认：

```bash
sudo ls -l /opt/novel-generator/novels/          # 看到那两个 .md
sudo stat -c '%a %U:%G %n' /opt/novel-generator/config.json   # 期望 600 novelgen:novelgen
```

隐私密码跟着 `config.json` 一起过来，**不需要重设**（哈希里带 salt）。

### 4.2 以后不要再从本机推数据

迁移完成后 **服务器上的 `novels/` 就是唯一真相**。`deploy.ps1` 默认不推 `novels/` 和 `config.json`，
就是为了防止把服务器上新写的小说覆盖掉。想拿回本机就反向 scp。

### 4.3 备份

`setup-server.sh` 会装好每天 03:15 的备份（`/etc/cron.d/novel-backup`），
打包到 `/var/backups/novel-generator/novel-<时间>.tar.gz`，保留 30 天，权限 600（含明文 Key）。

```bash
sudo bash /opt/novel-generator/deploy/backup.sh    # 手动立刻备一份
sudo ls -lh /var/backups/novel-generator/
```

**本地备份 ≠ 备份**。强烈建议再加一条异地：服务器上生成后，从本机定时 `scp` 拉回来，或者开云厂商的对象存储。

### 4.4 恢复

```bash
sudo systemctl stop novel-generator
sudo tar -xzf /var/backups/novel-generator/novel-2026-01-01-0315.tar.gz -C /opt/novel-generator
sudo chown -R novelgen:novelgen /opt/novel-generator/novels /opt/novel-generator/config.json
sudo chmod 600 /opt/novel-generator/config.json
sudo systemctl start novel-generator
```

---

## 5. 公网安全（选的是直连方案，这段务必看完）

必须摆明一个事实：**这个项目没有账号体系**（只有「隐私书架」需要密码，而且 README 自己写了
「书籍正文仍以明文存放在 `novels/`，只在界面与接口层按密码隐藏」）。所以：

**能连到 8000 端口的人 = 能读你所有小说、能用你的 API Key 花钱、能删你的书。**

云安全组白名单能挡住这个——只要满足两个前提：**8000 端口只对固定 IP 放行**，**SSH 也不对全网开放**。

### 5.1 直连方案的三个残留风险

| 风险 | 说明 | 缓解 |
| --- | --- | --- |
| **流量明文** | 你在网页「设置」里保存 API Key 时，Key 以明文 JSON 过公网；隐私密码也一样 | 加 nginx + TLS（下面 5.2），或者用 SSH 隧道 |
| 白名单形同虚设 | 安全组如果有人手滑写了 `0.0.0.0/0` | 定期去控制台复核规则 |
| 家宽 IP 变化 | 换 IP 后你自己也访问不了 | 换 Tailscale，或给服务器配动态 DNS + 脚本改安全组 |

### 5.2 加一层 nginx + HTTPS（推荐，可选项）

项目不带 TLS，但加一层反代很便宜。`deploy/nginx-novel-generator.conf.example` 里已经写好，
包含 Basic Auth、`client_max_body_size 100m`（那本 19MB 的书是整段 JSON 上传的，
nginx 默认 1MB 会直接 413）、以及 900 秒的 `proxy_read_timeout`。

```bash
sudo apt install -y nginx apache2-utils
sudo htpasswd -c /etc/nginx/.htpasswd yourname          # 反代鉴权，补上项目缺失的登录
sudo cp /opt/novel-generator/deploy/nginx-novel-generator.conf.example \
        /etc/nginx/sites-available/novel-generator
sudo ln -s /etc/nginx/sites-available/novel-generator /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

启用 nginx 后**务必同时改两处**，否则 8000 还是裸的：

1. `deploy/novel-generator.service` 里 `NOVEL_BIND=127.0.0.1:8000`（只监听本机），`systemctl daemon-reload && systemctl restart novel-generator`
2. 安全组里**删掉 8000 的入站规则**，只留 443

证书：有域名就 `sudo apt install certbot python3-certbot-nginx && sudo certbot --nginx -d your.domain`。
没有域名可以先用自签证书（浏览器会警告）或者 `<你的IP>.nip.io` 这类临时域名试试 certbot 的 HTTP-01 签发。

### 5.3 更省事的替代：不暴露公网

如果你只是想在外面写小说，**Tailscale / WireGuard / SSH 隧道**比白名单省心得多，
而且不用改任何配置：

```bash
# 服务器装 Tailscale，本机也装，登录同一账号后直接访问它的 Tailscale IP
ssh -L 8000:127.0.0.1:8000 root@<公网IP>     # 或者纯 SSH 隧道
# 然后浏览器开 http://127.0.0.1:8000
```

---

## 6. 常用运维命令

```bash
sudo systemctl status novel-generator        # 状态
sudo systemctl restart novel-generator       # 重启（改代码后）
sudo systemctl stop novel-generator          # 停止
sudo journalctl -u novel-generator -f        # 实时日志
sudo journalctl -u novel-generator -n 100 --no-pager    # 最近 100 行
sudo ss -tlnp | grep 8000                    # 确认监听状态
curl -I http://127.0.0.1:8000/               # 本机自检
sudo ufw status verbose                      # 主机防火墙
```

改代码后：`pwsh -File deploy\deploy.ps1 -Server <IP>`，脚本里已经带了 `systemctl restart`。

**重启会清空内存里的生成任务**（`JOBS`）。正在生成的书会被标记为「生成中断」，
到阅读器点「从断点继续」即可——这是项目自带的设计，不是故障。

---

## 7. 排查

| 现象 | 原因与处理 |
| --- | --- |
| 服务起不来，日志有 `Failed to set up mount namespacing` | `config.json` 等 `ReadWritePaths` 指向的路径不存在。`sudo touch /opt/novel-generator/config.json`，或确认单元里路径前缀 `-` 没被删 |
| 服务起不来，日志有 `status=226/NAMESPACE` 或权限错 | 加固项太严。把 `deploy/novel-generator.service` 里 `NoNewPrivileges=true` 到 `SystemCallErrorNumber=EPERM` 整段注释掉，`daemon-reload` 后重启，再逐行加回来定位 |
| 日志有 `ImportError: cannot import name 'flask'` | venv 没装好，或 `pylibs/` 还在顶包。`sudo rm -rf /opt/novel-generator/pylibs`，再跑一次 `setup-server.sh` |
| `gunicorn: command not found` | venv 里没装上。见下面「gunicorn 装不上」 |
| 页面能开，点生成报 500，日志是连接超时 | 服务器出网被限。`curl -sS https://api.deepseek.com` 试试；云厂商安全组出站默认全通，但有些机器配了 NAT 限制 |
| 私密书架「密码正确却提示没解锁」 | 有多进程在跑。`ps aux \| grep gunicorn`，确认只有 1 个 worker |
| 上传大文件报 413 | 你加了 nginx 但没配 `client_max_body_size`（example 里有） |
| 换 IP 后访问不了 | 安全组白名单失效，去控制台改；或改用 Tailscale |
| 「进度条不动 / 任务卡住」 | 先看 `journalctl -u novel-generator -f` 有没有异常；再确认只有 1 个 worker。重启会丢任务状态，但已生成章节保留在文件里 |

**gunicorn 装不上**（Ubuntu 26.04 的 Python 比较新，某个版本可能还没有预编译/适配）：
最省事的退路是**不用 gunicorn**，直接用项目原本的启动方式让 systemd 托管。
把 `deploy/novel-generator.service` 的 `ExecStart` 换成：

```ini
Environment=NOVEL_HOST=0.0.0.0
Environment=NOVEL_PORT=8000
ExecStart=/opt/novel-generator/.venv/bin/python /opt/novel-generator/app.py
```

注意：`NOVEL_HOST` / `NOVEL_PORT` 这两个环境变量**只在 `python app.py` 这条路径下生效**
（`app.py:2010` 的 `if __name__ == "__main__"` 里）。走 gunicorn 时它们被忽略，
监听地址由 `gunicorn.conf.py` 的 `bind` 决定——**这是很容易踩的一个坑**。
Flask 自带的服务器是单进程多线程，对这个单人工具够用，只是不如 gunicorn 稳。

---

## 8. 部署后自检清单

按顺序过一遍，全绿就算部署完成：

- [ ] `systemctl is-active novel-generator` 输出 `active`
- [ ] `systemctl is-enabled novel-generator` 输出 `enabled`（开机自启）
- [ ] `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/` 输出 `200`
- [ ] `sudo reboot` 后服务自己起来了，`journalctl -u novel-generator` 没有报错
- [ ] 从你自己的设备打开 `http://<公网IP>:8000/` 能出页面
- [ ] 从**别的网络**（手机 4G，不用 WiFi）访问**打不开** —— 证明白名单生效
- [ ] 「设置」页能看到迁移过来的 2 个模型（Key 显示掩码），点「测试」通过
- [ ] 「我的书架」能看到那两本书，打开 19MB 那本能正常翻章
- [ ] 试一次「续写」1 章，进度条会走、能生成成功
- [ ] 隐私书架：输入原密码能解锁（验证 `config.json` 迁移完整）
- [ ] `sudo ls -l /var/backups/novel-generator/` 有今天的备份包
- [ ] `sudo stat -c '%a %n' /opt/novel-generator/config.json` 是 `600`
- [ ] `ps aux | grep -c '[g]unicorn'` 里 worker 只有 1 个

---

## 9. deploy/ 目录里有什么

| 文件 | 作用 |
| --- | --- |
| `README-DEPLOY.md` | 本文档 |
| `deploy.ps1` | Windows 上一键：打包 → 上传 → 服务器初始化 → 重启 → 自检 |
| `setup-server.sh` | 服务器上以 root 执行：装系统包、建 `novelgen` 用户、venv、systemd、ufw、cron 备份、跑测试 |
| `novel-generator.service` | systemd 单元（含加固与 `ReadWritePaths`） |
| `gunicorn.conf.py` | 单进程 + 8 线程 + 900s 超时，注释里写了每个值的理由 |
| `requirements-prod.txt` | flask / requests / gunicorn |
| `backup.sh` | 备份 `novels/` 与 `config.json`，保留 30 天 |
| `nginx-novel-generator.conf.example` | 可选的 nginx + Basic Auth + TLS 反代配置 |

---

## 附：本次部署实测记录（2026-10-08）

| 项目 | 实际值 |
| --- | --- |
| 服务器 | <SERVER_IP>（阿里云 ECS，主机名 `<INSTANCE_ID>`） |
| 系统 | Ubuntu 26.04.1 LTS x86_64，Python 3.14.4 |
| 规格 | 2 vCPU / 1.7 GB 内存 / 40 GB 磁盘（另有 2 GB swap） |
| 运行用户 | `novelgen`（系统用户，`/usr/sbin/nologin`） |
| 应用目录 | `/opt/novel-generator`（750），数据在 `novels/`（755） |
| 依赖版本 | Flask 3.1.3 / requests 2.34.2 / **gunicorn 26.2.0** / pytest 9.1.1 |
| 监听 | `0.0.0.0:8000`，1 master + 1 worker（gthread，8 线程），内存峰值 44 MB |
| 主机防火墙 | ufw active：`22/tcp` 所有来源；`8000/tcp` 仅 `<CLIENT_IP>` |
| 备份 | cron 每天 03:15 → `/var/backups/novel-generator/`（首份 7.3 MB，权限 600） |

已实测通过的项：迁移文件 SHA256 与本地**逐字节一致**（含 19 MB 那本）、29 个单元测试全过、
`HTTP 200`、隐私书架未解锁返回 `403`、**真实调用 DeepSeek 返回「正常」**、
通过 API 删书入回收站再恢复成功（证明 `ProtectSystem=strict` 下写入路径正常）、
备份脚本产出 7.3 MB 包、`systemctl reboot` 后 45 秒服务自动恢复且数据未变、
本次启动日志 ERROR 数 = 0。

### 实测踩到的两个坑（脚本已修）

1. **Windows 的 tar 会把目录/文件解成 777**：`novels/` 变成 `drwxrwxrwx`、小说文件 `-rw-rw-rw-`。
   `setup-server.sh` 现在会 `chmod -R go-w`，`config.json` 仍单独设 600。
2. **gunicorn 26 的「控制套接字」**：默认在 `$XDG_RUNTIME_DIR`（取不到就 `$HOME`）建一个给
   `gunicornc` 用的 socket；单元里开了 `ProtectHome=true`，于是每次启动都刷
   `[ERROR] Control server error: [Errno 13] Permission denied: '/home/novelgen'`。
   单 worker 场景用不到运行时管理，已在 `gunicorn.conf.py` 里 `control_socket_disable = True` 关闭。

### 这个实例还没做完的一件事

**阿里云安全组**。`ufw` 已经把 8000 收紧到你的 IP，但云安全组是另一层，**从服务器内部看不到它的规则**，
必须你在控制台确认：入方向放行「自定义 TCP / 8000」、授权对象 `58.19.2.247/32`，
并删掉任何 `0.0.0.0/0` 的 8000 规则。以后换 IP 要两处一起改（安全组 + `ufw`）。
