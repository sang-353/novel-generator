<#
.SYNOPSIS
    把小说生成器从 Windows 推到 Ubuntu 服务器，并在服务器上完成初始化 / 更新、重启服务。

.DESCRIPTION
    在本机先打包（只带运行需要的文件，自动剔除 pylibs\ 等 Windows 专用产物），
    再用 scp 传到服务器 /tmp 解开，最后调用服务器上的 deploy/setup-server.sh。

    默认【不推数据】：服务器上的 novels\ 与 config.json 是运行期间的唯一真相，
    每次部署都覆盖会把服务器上新写的小说冲掉。首次迁移请显式加 -WithData。

.EXAMPLE
    # 首次部署（连本机的小说正文和配置一起迁过去）
    pwsh -File deploy\deploy.ps1 -Server 1.2.3.4 -WithData

.EXAMPLE
    # 以后只更新代码
    pwsh -File deploy\deploy.ps1 -Server 1.2.3.4

.EXAMPLE
    # 传文件但不装环境、不重启（只想看一眼）
    pwsh -File deploy\deploy.ps1 -Server 1.2.3.4 -UploadOnly
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Server,
    [string]$User = "root",
    [int]$SshPort = 22,
    [string]$AppDir = "/opt/novel-generator",
    [int]$AppPort = 8000,
    # 首次部署才用：把本机 novels\ 与 config.json 一起推上去（会覆盖服务器同名文件）
    [switch]$WithData,
    # 只上传，不执行 setup-server.sh、不重启服务
    [switch]$UploadOnly
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

function Info($m) { Write-Host "==> $m" -ForegroundColor Cyan }
function Warn($m) { Write-Host "[注意] $m" -ForegroundColor Yellow }
function Die($m) { Write-Host "[错误] $m" -ForegroundColor Red; exit 1 }

foreach ($exe in @("ssh", "scp", "tar")) {
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) {
        Die "找不到 $exe —— 请先安装 OpenSSH 客户端（Windows 设置 → 可选功能）。"
    }
}

$target = "$User@$Server"
# accept-new：首次连接自动记住主机指纹，之后指纹变了仍然会报错
$sshOpts = @("-p", "$SshPort", "-o", "StrictHostKeyChecking=accept-new", "-o", "ServerAliveInterval=30")

function Invoke-Remote([string]$Command) {
    & ssh @sshOpts $target $Command
    if ($LASTEXITCODE -ne 0) { Die "远端命令失败（exit $LASTEXITCODE）：$Command" }
}

# --- 1. 打包 -----------------------------------------------------------------
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$stage = Join-Path ([System.IO.Path]::GetTempPath()) "novel-deploy-$stamp"
New-Item -ItemType Directory -Path $stage -Force | Out-Null

Info "打包本机文件"

# 要传的：跑服务真正需要的东西
$codeItems = @("app.py", "requirements.txt", "README.md", "static", "tests", "deploy")
foreach ($item in $codeItems) {
    $src = Join-Path $root $item
    if (Test-Path $src) {
        Copy-Item $src -Destination $stage -Recurse -Force
    } else {
        Warn "本机没有 $item，跳过"
    }
}

# 不传的（保持这个名单，别加）：
#   pylibs\        Windows 的 *.pyd 二进制依赖。服务器上用 venv；传过去反而会被
#                  app.py 插到 sys.path 最前面，顶掉 venv 里的同名包。
#   wheels\ .tmp\ __pycache__\ .pytest_cache\ .idea\ *.bat\ *.ps1   本机产物
#   根目录那本 9MB 的 .txt   只是续写素材，服务端不读它
Get-ChildItem -Path $stage -Recurse -Directory -Force |
    Where-Object { $_.Name -in @("__pycache__", ".pytest_cache") } |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

if ($WithData) {
    Warn "带了 -WithData：将覆盖服务器上的 novels\ 与 config.json（含明文 API Key）"
    Copy-Item (Join-Path $root "novels") -Destination $stage -Recurse -Force
    $cfg = Join-Path $root "config.json"
    if (Test-Path $cfg) { Copy-Item $cfg -Destination $stage -Force }
}

$pkg = Join-Path ([System.IO.Path]::GetTempPath()) "novel-$stamp.tar.gz"
& tar -czf $pkg -C $stage .
if ($LASTEXITCODE -ne 0) { Die "打包失败" }
$sizeMB = [math]::Round((Get-Item $pkg).Length / 1MB, 2)
Write-Host "    $pkg（$sizeMB MB）" -ForegroundColor DarkGray

# --- 2. 上传 -----------------------------------------------------------------
Info "上传到 ${target}:/tmp/"
& scp -P $SshPort -o StrictHostKeyChecking=accept-new $pkg "${target}:/tmp/novel-deploy.tar.gz"
if ($LASTEXITCODE -ne 0) { Die "上传失败。先手动执行一次 `ssh $target` 确认能连上、密钥已配好。" }

# --- 3. 解包 -----------------------------------------------------------------
Info "解包到 $AppDir"
Invoke-Remote "mkdir -p '$AppDir' && tar -xzf /tmp/novel-deploy.tar.gz -C '$AppDir' && rm -f /tmp/novel-deploy.tar.gz && echo '    解包完成'"

# --- 4. 初始化 / 更新 --------------------------------------------------------
if ($UploadOnly) {
    Warn "指定了 -UploadOnly：跳过环境安装与服务重启"
} else {
    Info "在服务器上安装 / 更新环境并重启服务（需要 root）"
    Invoke-Remote "APP_DIR='$AppDir' APP_USER='novelgen' PORT=$AppPort bash '$AppDir/deploy/setup-server.sh'"
}

# --- 5. 验证 -----------------------------------------------------------------
Info "验证服务状态"
Invoke-Remote "systemctl is-active novel-generator; curl -s -o /dev/null -w '本机 HTTP %{http_code}\n' http://127.0.0.1:$AppPort/"

# --- 6. 清理本机临时文件 -----------------------------------------------------
Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $pkg -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "完成。浏览器打开  http://${Server}:${AppPort}/" -ForegroundColor Green
Write-Host "记得在云控制台「安全组」里只放行你自己的出口 IP 访问 ${AppPort} 端口。" -ForegroundColor Yellow
