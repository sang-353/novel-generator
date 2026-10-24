# 小说生成器 —— 首次安装并启动
# 作用：把依赖装到工作区 pylibs\（绕开沙箱对系统临时目录的限制），然后启动服务
# 用法：pwsh -NoProfile -File tools\install.ps1   （或双击 安装并启动.bat）

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$libs = Join-Path $root 'pylibs'

if (-not (Test-Path $libs)) {
    Write-Host '首次运行：正在把依赖安装到 pylibs\（约需 1-2 分钟）...' -ForegroundColor Cyan
    New-Item -ItemType Directory -Path $libs -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $root '.tmp') -Force | Out-Null

    # pip 的临时目录指到工作区内，避免系统临时目录权限被拦截
    $env:TMP = Join-Path $root '.tmp'
    $env:TEMP = Join-Path $root '.tmp'

    Copy-Item (Join-Path $root 'pylibs_sitecustomize.py') (Join-Path $libs 'sitecustomize.py') -Force
    $env:PYTHONPATH = $libs

    python -m pip install --no-cache-dir --target pylibs flask requests
    if ($LASTEXITCODE -ne 0) {
        Write-Host '依赖安装失败，请检查上面的 pip 报错信息。' -ForegroundColor Red
        exit 1
    }
    Write-Host '依赖安装完成。' -ForegroundColor Green
} else {
    Write-Host 'pylibs\ 已存在，跳过依赖安装。' -ForegroundColor DarkGray
}

# 交给统一的启动入口（会打开浏览器、显示服务日志）
& (Join-Path $root '开服务.bat')
