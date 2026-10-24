#!/usr/bin/env bash
# ============================================================================
# 小说生成器 —— Ubuntu 服务器初始化脚本
#
# 前提：项目文件已经传到 $APP_DIR
#       （Windows 上用 deploy\deploy.ps1 -WithData 传，或手动 scp/tar）
# 用法：sudo bash /opt/novel-generator/deploy/setup-server.sh
#
# 可重复执行。可用环境变量覆盖：APP_DIR / APP_USER / PORT
#   sudo APP_DIR=/srv/novel PORT=9000 bash deploy/setup-server.sh
# ============================================================================
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/novel-generator}"
APP_USER="${APP_USER:-novelgen}"
PORT="${PORT:-8000}"

info() { printf '\n\033[36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[33m[注意] %s\033[0m\n' "$*"; }
die()  { printf '\n\033[31m[错误] %s\033[0m\n' "$*" >&2; exit 1; }

[[ "${EUID}" -eq 0 ]] || die "需要 root：sudo bash $0"
[[ -f "${APP_DIR}/app.py" ]] || die "在 ${APP_DIR} 里找不到 app.py。请先把项目文件传上去，再运行本脚本。"

# --- 1. 系统包 --------------------------------------------------------------
info "1/7 安装系统依赖"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip rsync curl ca-certificates ufw cron

# --- 2. 运行用户 ------------------------------------------------------------
info "2/7 创建运行用户 ${APP_USER}（系统用户、不可登录）"
if id -u "${APP_USER}" >/dev/null 2>&1; then
  echo "    已存在，跳过"
else
  useradd --system --create-home --home-dir "/home/${APP_USER}" --shell /usr/sbin/nologin "${APP_USER}"
fi

# --- 3. 目录 / 属主 / 权限 --------------------------------------------------
info "3/7 修正目录与文件权限"
mkdir -p "${APP_DIR}/novels/_trash/chapters" "${APP_DIR}/analysis_cache"

# 关键一步：删掉 Windows 带过来的 pylibs/。
# 里面是 *.pyd（Windows 二进制），在 Linux 上既加载不了，
# 又会因为 app.py 第 26-28 行把它插到 sys.path 最前面而顶掉 venv 里的正常包。
if [[ -d "${APP_DIR}/pylibs" ]]; then
  rm -rf "${APP_DIR}/pylibs"
  echo "    已删除 pylibs/（Windows 专用，Linux 改用 venv）"
fi

chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"
chmod 750 "${APP_DIR}"
# Windows 的 tar 会把目录/文件解成 777，去掉多余的可写位（config.json 下面单独设 600）
chmod -R go-w "${APP_DIR}" 2>/dev/null || true

# config.json 里是明文 API Key + 隐私密码哈希：只有属主可读写。
# 文件必须存在：systemd 单元的 ReadWritePaths 指向它。
if [[ ! -f "${APP_DIR}/config.json" ]]; then
  install -o "${APP_USER}" -g "${APP_USER}" -m 600 /dev/null "${APP_DIR}/config.json"
  echo "    新建空 config.json（启动后到网页「设置」里填模型）"
else
  chown "${APP_USER}:${APP_USER}" "${APP_DIR}/config.json"
  chmod 600 "${APP_DIR}/config.json"
  echo "    config.json 权限收紧为 600"
fi

# --- 4. venv ----------------------------------------------------------------
info "4/7 创建 venv 并安装依赖"
if [[ ! -x "${APP_DIR}/.venv/bin/python" ]]; then
  sudo -u "${APP_USER}" python3 -m venv "${APP_DIR}/.venv"
fi
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/python" -m pip install --quiet --upgrade pip
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/pip" install --quiet -r "${APP_DIR}/deploy/requirements-prod.txt"
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/python" - <<'PY'
import flask, requests
print(f"    flask {flask.__version__} / requests {requests.__version__}")
try:
    import gunicorn
    print(f"    gunicorn {gunicorn.__version__}")
except ImportError:
    raise SystemExit("gunicorn 没装上 —— 见 deploy/README-DEPLOY.md 的「gunicorn 装不上」一节")
PY

# --- 5. 自检 ----------------------------------------------------------------
info "5/7 语法自检 + 单元测试"
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/python" -m py_compile "${APP_DIR}/app.py"
echo "    app.py 语法 OK"
if [[ -f "${APP_DIR}/tests/test_app.py" ]]; then
  sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/pip" install --quiet pytest
  if sudo -u "${APP_USER}" bash -c "cd '${APP_DIR}' && .venv/bin/python -m pytest tests/ -q"; then
    echo "    单元测试全部通过"
  else
    warn "单元测试有失败项（见上面输出）。不阻塞部署，但先确认不是环境问题"
  fi
fi

# --- 6. systemd -------------------------------------------------------------
info "6/7 安装并启动 systemd 服务"
sed -e "s#/opt/novel-generator#${APP_DIR}#g" \
    -e "s/^User=novelgen/User=${APP_USER}/" \
    -e "s/^Group=novelgen/Group=${APP_USER}/" \
    -e "s#0\.0\.0\.0:8000#0.0.0.0:${PORT}#" \
    "${APP_DIR}/deploy/novel-generator.service" > /etc/systemd/system/novel-generator.service
systemctl daemon-reload
systemctl enable novel-generator >/dev/null 2>&1 || true
systemctl restart novel-generator
sleep 3
if systemctl is-active --quiet novel-generator; then
  echo "    服务已启动，且已设为开机自启"
else
  journalctl -u novel-generator -n 60 --no-pager || true
  die "服务没起来。见 README-DEPLOY.md「排查」一节：先把加固项注释掉再试"
fi

# --- 7. 本机自检 ------------------------------------------------------------
info "7/7 本机接口自检"
LOCAL_URL="http://127.0.0.1:${PORT}/"
code="$(curl -s -o /dev/null -w '%{http_code}' "${LOCAL_URL}" || true)"
echo "    GET ${LOCAL_URL}  ->  HTTP ${code}"
[[ "${code}" == "200" ]] || warn "没返回 200：journalctl -u novel-generator -n 60 --no-pager"

# --- 防火墙（主机层）--------------------------------------------------------
info "配置 ufw（主机层防火墙）"
# 防锁死：先安排一次「3 分钟后自动关闭 ufw」，确认 SSH 规则真的生效后再取消这个定时器。
# 远程开防火墙最怕的就是规则没生效，把自己关在门外（那就只能去云控制台 VNC 救急了）。
systemd-run --on-active=3min --unit=ufw-emergency-off ufw disable >/dev/null 2>&1 || true
ufw allow 22/tcp >/dev/null
# 只在「这个端口还没有任何规则」时才加「所有来源」规则。
# 否则你把它收紧成只允许自己的 IP 之后，下一次重新部署又会把它对全网打开。
if ufw status | grep -q "${PORT}/tcp"; then
  echo "    ${PORT}/tcp 已有规则，保持现状（不会重新对全网放开）"
else
  ufw allow "${PORT}/tcp" >/dev/null
  echo "    已放行 ${PORT}/tcp（所有来源）"
fi
ufw --force enable >/dev/null
ufw status verbose | sed 's/^/    /'
if ufw status | grep -q '22/tcp'; then
  systemctl stop ufw-emergency-off.timer >/dev/null 2>&1 || true
  echo "    SSH(22) 规则已确认生效，自动回退已取消"
else
  ufw disable
  warn "22/tcp 规则异常，已直接关闭 ufw —— 请手动检查后再启用"
fi
warn "ufw 对【所有来源】放开了 ${PORT}。真正的白名单请在云控制台的「安全组」里按你的出口 IP 限制。"
warn "想在主机层也限制：ufw delete allow ${PORT}/tcp 之后执行"
warn "  ufw allow from <你的固定IP> to any port ${PORT} proto tcp"

# --- 备份 -------------------------------------------------------------------
info "安装每日备份（03:15，保留 30 天）"
chmod +x "${APP_DIR}/deploy/backup.sh"
cat > /etc/cron.d/novel-backup <<EOF
# 小说生成器：备份 novels/ 与 config.json（备份文件仅 root 可读）
15 3 * * * root APP_DIR=${APP_DIR} ${APP_DIR}/deploy/backup.sh >> /var/log/novel-backup.log 2>&1
EOF
chmod 644 /etc/cron.d/novel-backup
systemctl enable --now cron >/dev/null 2>&1 || true

# --- 收尾 -------------------------------------------------------------------
PUBLIC_IP="$(curl -s --max-time 5 https://ifconfig.me || true)"
cat <<EOF

$(printf '\033[32m')部署完成$(printf '\033[0m')

  访问地址   http://${PUBLIC_IP:-<服务器公网IP>}:${PORT}/
  服务管理   systemctl status|restart|stop novel-generator
  看日志     journalctl -u novel-generator -f
  数据目录   ${APP_DIR}/novels/          （小说 Markdown，含 _trash 回收站）
  配置       ${APP_DIR}/config.json      （权限 600，明文 API Key）
  备份       /var/backups/novel-generator/

  还没做的事：
    1) 在云控制台「安全组」里只放行你自己的出口 IP 访问 ${PORT} 端口
    2) 打开网页 →「设置」确认模型和 Key 正常（config.json 已迁移的话直接点「测试」）
EOF
