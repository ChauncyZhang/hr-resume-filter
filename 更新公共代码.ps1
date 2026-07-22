$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

& git -C $root submodule update --init --recursive
if ($LASTEXITCODE -ne 0) { throw '初始化 product 子模块失败。' }
& git -C "$root/product" fetch origin main
if ($LASTEXITCODE -ne 0) { throw '获取公开仓库更新失败。' }
& git -C "$root/product" checkout main
if ($LASTEXITCODE -ne 0) { throw '切换 product/main 失败。' }
& git -C "$root/product" merge --ff-only origin/main
if ($LASTEXITCODE -ne 0) { throw 'product 无法快进到 origin/main，请先处理本地提交。' }

$commit = (& git -C "$root/product" rev-parse --short HEAD).Trim()
Write-Host "公开产品代码已更新到 $commit。请验证后提交本仓库中的 product 指针。"
