# 小说生成器 —— 状态检查
# 作用：查看服务是否在运行
# 用法：pwsh -NoProfile -File tools\status.ps1   （或双击 状态.bat）
# 实现说明：用 netstat 找端口占用者、用 Get-Process 取进程名；
#           不用 Get-NetTCPConnection / Get-CimInstance（受限环境下会被拒绝访问）。

$ErrorActionPreference = 'SilentlyContinue'
$port = 8000
$url = "http://127.0.0.1:$port"

$owners = @()
foreach ($line in (netstat -ano | Select-String -Pattern "TCP\s+\S+:$port\s+\S+\s+LISTENING\s+(\d+)")) {
    $owners += [int]$line.Matches[0].Groups[1].Value
}
$owners = @($owners | Sort-Object -Unique)

if ($owners.Count -eq 0) {
    Write-Host "未运行：端口 $port 空闲。" -ForegroundColor Yellow
    exit 1
}

foreach ($ownerPid in $owners) {
    $proc = Get-Process -Id $ownerPid -ErrorAction SilentlyContinue
    $name = if ($proc) { $proc.ProcessName } else { '未知' }
    $tag = if ($name -like 'python*') { '小说生成器' } else { '其他程序' }
    Write-Host "运行中：进程号 $ownerPid  $name  [$tag]" -ForegroundColor Green
}

try {
    $r = Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 3
    Write-Host "可访问：$url  (HTTP $($r.StatusCode))" -ForegroundColor Green
} catch {
    Write-Host "端口在监听，但 $url 暂无响应。" -ForegroundColor Yellow
}
