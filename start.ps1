# 模块职责：一键启动脚本：检查虚拟环境、构建向量索引、后台启动后端与前端，退出时统一清理进程。

param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$venvPython = Join-Path $Root "backend\.venv\Scripts\python.exe"

# 1. 检查虚拟环境，不存在则创建并安装依赖
if (-not (Test-Path $venvPython)) {
    Write-Host "[1/4] 创建虚拟环境并安装依赖..."
    & python -m venv (Join-Path $Root "backend\.venv")
    & $venvPython -m pip install -r (Join-Path $Root "backend\requirements.txt")
} else {
    Write-Host "[1/4] 虚拟环境已存在"
}
# 2. 构建向量索引（对应 compose 里的 init 服务）
Write-Host "[2/4] 构建向量索引..."
Push-Location (Join-Path $Root "backend")
try {
    & $venvPython -m scripts.build_vector_index
} finally {
    Pop-Location
}
# 3. 后台启动后端
$backendDir = Join-Path $Root "backend"
Write-Host "[3/4] 启动后端 http://127.0.0.1:8000 ..."
$backend = Start-Process -FilePath $venvPython `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" `
    -WorkingDirectory $backendDir `
    -PassThru -WindowStyle Hidden

# 4. 后台启动前端
$frontendDir = Join-Path $Root "frontend"
if (-not (Test-Path (Join-Path $frontendDir "node_modules"))) {
    Write-Host "[4/4] 安装前端依赖（首次）..."
    Push-Location $frontendDir
    try { & npm install } finally { Pop-Location }
}
Write-Host "[4/4] 启动前端 http://localhost:5173 ..."
$frontend = Start-Process -FilePath "npm.cmd" `
    -ArgumentList "run", "dev" `
    -WorkingDirectory $frontendDir `
    -PassThru -WindowStyle Hidden

# 5. 等待退出并清理
try {
    Write-Host ""
    Write-Host "全部服务已启动：后端 http://127.0.0.1:8000/docs  |  前端 http://localhost:5173"
    Read-Host "按回车停止所有服务"
} finally {
    Write-Host "正在停止服务..."
    taskkill /PID $backend.Id /T /F 2>$null
    taskkill /PID $frontend.Id /T /F 2>$null
}
