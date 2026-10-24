# 小说生成器 —— 关闭脚本
# 作用：结束小说生成器的服务进程（含子进程）
# 用法：pwsh -NoProfile -File tools\stop.ps1   （或双击根目录 关服务.bat）
# 实现说明：用 netstat 找端口占用者、用 Get-Process 取进程名；
#           不用 Get-NetTCPConnection / Get-CimInstance（受限环境下会被拒绝访问）。

$ErrorActionPreference = 'SilentlyContinue'
$port = 8000
$killed = @()

# 找出「正在监听 8000 端口」的进程号
function Get-PortOwner([int]$p) {
    $owners = @()
    foreach ($line in (netstat -ano | Select-String -Pattern "TCP\s+\S+:$p\s+\S+\s+LISTENING\s+(\d+)")) {
        $owners += [int]$line.Matches[0].Groups[1].Value
    }
    @($owners | Sort-Object -Unique)
}

$owners = @(Get-PortOwner $port)
$targets = @()
foreach ($ownerPid in $owners) {
    if (-not $ownerPid -or $ownerPid -eq 0) { continue }
    $proc = Get-Process -Id $ownerPid -ErrorAction SilentlyContinue
    if ($proc -and $proc.ProcessName -like 'python*') {
        $targets += $ownerPid
    }
}

# 端口被别的程序占用：不做任何关闭
if ($owners.Count -gt 0 -and $targets.Count -eq 0) {
    Write-Host "端口 $port 被其他程序占用（不是本项目的 python 服务），未做任何关闭。" -ForegroundColor Yellow
    foreach ($ownerPid in $owners) {
        $proc = Get-Process -Id $ownerPid -ErrorAction SilentlyContinue
        Write-Host "  进程号 $ownerPid  $($proc.ProcessName)" -ForegroundColor DarkGray
    }
    exit 1
}

foreach ($targetPid in $targets) {
    # 优先 taskkill（会连同子进程一起结束）；被策略拒绝时退回 Stop-Process
    $ok = $false
    if (Get-Command taskkill -ErrorAction SilentlyContinue) {
        taskkill /f /t /pid "$targetPid" 2>$null | Out-Null
        $ok = ($LASTEXITCODE -eq 0)
    }
    if (-not $ok) {
        Stop-Process -Id $targetPid -Force -ErrorAction SilentlyContinue
    }
    $killed += $targetPid
}

Start-Sleep -Milliseconds 600
$still = @(Get-PortOwner $port)

if ($still.Count -gt 0) {
    Write-Host "关闭失败：端口 $port 仍被占用（进程号：$($still -join ', ')）。" -ForegroundColor Red
    Write-Host "也可以直接关掉「开服务.bat」那个窗口。" -ForegroundColor DarkGray
    exit 1
}

if ($killed.Count -gt 0) {
    Write-Host "已关闭小说生成器（进程号：$($killed -join ', ')）。" -ForegroundColor Green
} else {
    Write-Host "没有发现正在运行的小说生成器服务（端口 $port 空闲）。" -ForegroundColor Yellow
}
