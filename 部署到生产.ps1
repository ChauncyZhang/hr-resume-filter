[CmdletBinding()]
param(
    [ValidateSet('frontend', 'all')]
    [string]$Scope = 'all',
    [switch]$SkipTests,
    [switch]$ValidateOnly,
    [string]$ConfigPath = (Join-Path $PSScriptRoot 'deploy/target.psd1')
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$config = Import-PowerShellDataFile $ConfigPath

& git -C $root submodule update --init --recursive
if ($LASTEXITCODE -ne 0) { throw '初始化 product 子模块失败。' }

if (-not $ValidateOnly) {
    & ssh -o BatchMode=yes -o ConnectTimeout=15 $config.RemoteHost "test -L '$($config.RemoteRoot)/current' || test -f '$($config.RemoteRoot)/bootstrap/.env'"
    if ($LASTEXITCODE -ne 0) {
        & "$root/deploy/bootstrap-remote.ps1" -ConfigPath $ConfigPath
        if ($LASTEXITCODE -ne 0) { throw '远端首次初始化失败。' }
    }
}

$deployParameters = @{
    Scope = $Scope
    RemoteHost = $config.RemoteHost
    Domain = $config.Domain
    RemoteRoot = $config.RemoteRoot
    SkipTests = $SkipTests
    ValidateOnly = $ValidateOnly
}
& "$root/deploy/deploy-remote.ps1" @deployParameters
exit $LASTEXITCODE
