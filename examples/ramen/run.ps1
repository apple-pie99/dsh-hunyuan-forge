#requires -Version 5.1
<#
.SYNOPSIS
    一键跑完 ②搭结构 → ③生成 → ④归位/材质/渲染。

.EXAMPLE
    .\run.ps1
    .\run.ps1 -Blender "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
    .\run.ps1 -Bridge "http://127.0.0.1:8081" -Python "py"
#>
param(
    [string]$Blender = $env:BLENDER_EXE,
    [string]$Python = "python",
    [string]$Bridge = $(if ($env:HY3D_BRIDGE) { $env:HY3D_BRIDGE } else { "http://127.0.0.1:8081" })
)

# 原生程序往 stderr 写东西在 PS 里会被当成错误，这里不要 Stop
$ErrorActionPreference = "Continue"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $here

function Find-Blender {
    $candidates = @()
    if ($env:BLENDER_EXE) { $candidates += $env:BLENDER_EXE }
    $candidates += Get-ChildItem "C:\Program Files\Blender Foundation" -Directory -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending | ForEach-Object { Join-Path $_.FullName "blender.exe" }
    $cmd = Get-Command blender -ErrorAction SilentlyContinue
    if ($cmd) { $candidates += $cmd.Source }
    foreach ($c in $candidates) {
        if ($c -and (Test-Path $c)) { return $c }
    }
    return $null
}

function Step($title) {
    Write-Host ""
    Write-Host "==> $title" -ForegroundColor Cyan
}

try {
    Step "环境检查"

    if (-not $Blender) { $Blender = Find-Blender }
    if (-not $Blender) {
        Write-Host "找不到 Blender。用 -Blender <路径> 指定，或设置环境变量 BLENDER_EXE。" -ForegroundColor Red
        exit 2
    }
    Write-Host "  Blender : $Blender"

    & $Python -c "import requests" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  Python  : $Python（缺少 requests，先 pip install -r requirements.txt）" -ForegroundColor Red
        exit 2
    }
    Write-Host "  Python  : $Python"

    try {
        $health = Invoke-RestMethod -Uri "$Bridge/health" -TimeoutSec 6
    } catch {
        Write-Host "  桥接    : $Bridge 不可达" -ForegroundColor Red
        Write-Host "            先起 Hunyuan3D(8080) 和 bridge/server.py(8081)，见 docs/hunyuan-deploy.md" -ForegroundColor Yellow
        exit 2
    }
    if (-not $health.ok) {
        Write-Host "  桥接    : 上游 8080 没起（$($health.error)）" -ForegroundColor Red
        exit 2
    }
    Write-Host "  桥接    : $Bridge → $($health.upstream)"

    Step "① 搭结构 + 出参考图"
    $out = & $Blender -b --factory-startup -P run_build.py 2>&1
    $out | Select-String -Pattern "^\[forge\]|BUILD_DONE" | ForEach-Object { "  $_" }
    if (-not ($out | Select-String -Pattern "BUILD_DONE" -Quiet)) {
        Write-Host "  构建失败，完整输出：" -ForegroundColor Red
        $out | Select-Object -Last 30
        exit 1
    }

    Step "② 生成（Hunyuan3D）"
    & $Python gen_props.py
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  生成没有全部成功，检查 gen_report.json" -ForegroundColor Yellow
    }

    Step "③ 归位 + 材质 + 渲染 + 导出"
    $out = & $Blender -b stall_base.blend -P run_place.py 2>&1
    $out | Select-String -Pattern "^\[forge\]|placed|PLACE_DONE" | ForEach-Object { "  $_" }
    if (-not ($out | Select-String -Pattern "PLACE_DONE" -Quiet)) {
        Write-Host "  归位失败，完整输出：" -ForegroundColor Red
        $out | Select-Object -Last 30
        exit 1
    }

    Write-Host ""
    Write-Host "完成：" -ForegroundColor Green
    Get-ChildItem render.png, stall.blend, stall.glb -ErrorAction SilentlyContinue |
        ForEach-Object { "  {0,-14} {1,8:N1} KB" -f $_.Name, ($_.Length / 1KB) }
}
finally {
    Pop-Location
}
