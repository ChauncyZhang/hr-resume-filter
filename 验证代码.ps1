$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$config = Import-PowerShellDataFile "$root/deploy/target.psd1"

& git -C $root submodule update --init --recursive
if ($LASTEXITCODE -ne 0) { throw '初始化 product 子模块失败。' }

$previous = $env:PUBLIC_PROHIBITED_TERMS
try {
    $env:PUBLIC_PROHIBITED_TERMS = @(
        'aurora-tek', '120.79.184.221', 'admin@aurora',
        'ChauncyZhang/hr-resume-filter'
    ) -join ','
    & python "$root/product/scripts/check_public_tree.py"
    if ($LASTEXITCODE -ne 0) { throw '公开代码脱敏检查失败。' }
} finally {
    $env:PUBLIC_PROHIBITED_TERMS = $previous
}

Push-Location "$root/product/frontend"
try {
    & npm.cmd ci --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw '安装前端依赖失败。' }
    & npm.cmd test
    if ($LASTEXITCODE -ne 0) { throw '前端测试失败。' }
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw '前端构建失败。' }
} finally {
    Pop-Location
}

& python -m pytest `
    "$root/deploy/tests/test_shared_nginx_release_validator.py" `
    "$root/deploy/tests/test_remote_deploy_scripts.py" `
    "$root/deploy/tests/test_shared_nginx_smoke.py" -q -p no:cacheprovider
if ($LASTEXITCODE -ne 0) { throw '企业部署测试失败。' }

Write-Host '公开代码边界、前端和企业部署测试均通过。'
