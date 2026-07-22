[CmdletBinding()]
param([string]$ConfigPath = (Join-Path $PSScriptRoot 'target.psd1'))

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function New-RandomToken([int]$Bytes = 32) {
    $buffer = [byte[]]::new($Bytes)
    [Security.Cryptography.RandomNumberGenerator]::Fill($buffer)
    return ([Convert]::ToBase64String($buffer)).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function New-FernetKey {
    $buffer = [byte[]]::new(32)
    [Security.Cryptography.RandomNumberGenerator]::Fill($buffer)
    return [Convert]::ToBase64String($buffer).Replace('+', '-').Replace('/', '_')
}

$config = Import-PowerShellDataFile $ConfigPath
$remoteHost = [string]$config.RemoteHost
$remoteRoot = [string]$config.RemoteRoot
$sharedWebsiteContainer = [string]$config.SharedWebsiteContainer
if (-not $remoteHost -or -not $remoteRoot -or -not $sharedWebsiteContainer) {
    throw 'target.psd1 缺少 RemoteHost、RemoteRoot 或 SharedWebsiteContainer。'
}
if ($sharedWebsiteContainer -notmatch '^[A-Za-z0-9_.-]+$') {
    throw 'SharedWebsiteContainer 包含不支持的字符。'
}

& ssh -o BatchMode=yes -o ConnectTimeout=15 $remoteHost "test -L '$remoteRoot/current' || test -f '$remoteRoot/bootstrap/.env'"
if ($LASTEXITCODE -eq 0) {
    Write-Host '远端已经初始化或已有可重试的初始化材料，无需重复生成密钥。'
    return
}

foreach ($pathKey in @('TlsCertificatePath', 'TlsPrivateKeyPath')) {
    $path = [string]$config[$pathKey]
    if (-not $path -or -not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "全新服务器必须在 target.psd1 配置有效的 $pathKey。"
    }
}

$staging = Join-Path ([IO.Path]::GetTempPath()) ("beyondcandidate-bootstrap-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $staging | Out-Null
$adminPassword = New-RandomToken 24
try {
    $values = [ordered]@{
        APP_ENVIRONMENT = 'production'
        APP_IMAGE = 'registry.example.test/beyondcandidate-server'
        APP_IMAGE_DIGEST = 'sha256:' + ('0' * 64)
        FRONTEND_IMAGE = 'registry.example.test/beyondcandidate-frontend'
        FRONTEND_IMAGE_DIGEST = 'sha256:' + ('0' * 64)
        DEFAULT_ORGANIZATION_SLUG = [string]$config.OrganizationSlug
        DEFAULT_ORGANIZATION_NAME = [string]$config.OrganizationName
        POSTGRES_DB = 'ux09'
        POSTGRES_USER = 'ux09_owner'
        POSTGRES_PASSWORD = New-RandomToken
        APP_DB_USER = 'ux09_app'
        APP_DB_PASSWORD = New-RandomToken
        GOVERNANCE_DB_USER = 'ux09_governance'
        GOVERNANCE_DB_PASSWORD = New-RandomToken
        MINIO_ROOT_USER = 'bc-root-' + (New-RandomToken 9)
        MINIO_ROOT_PASSWORD = New-RandomToken
        APP_OBJECT_STORAGE_ACCESS_KEY = 'bc-app-' + (New-RandomToken 9)
        APP_OBJECT_STORAGE_SECRET_KEY = New-RandomToken
        OBJECT_STORAGE_BUCKET = 'resumes'
        GOVERNANCE_DELETE_ACCESS_KEY = 'bc-delete-' + (New-RandomToken 9)
        GOVERNANCE_DELETE_SECRET_KEY = New-RandomToken
        GOVERNANCE_RESUME_BUCKET = 'resumes'
        GOVERNANCE_RESUME_PREFIX = 'clean/'
        GOVERNANCE_EXPORT_BUCKET = 'resumes'
        GOVERNANCE_EXPORT_PREFIX = 'exports/'
        GOVERNANCE_LEDGER_ACCESS_KEY = 'bc-ledger-' + (New-RandomToken 9)
        GOVERNANCE_LEDGER_SECRET_KEY = New-RandomToken
        GOVERNANCE_LEDGER_BUCKET = 'governance-ledger'
        GOVERNANCE_LEDGER_PREFIX = 'deletions/'
        PREVIOUS_GOVERNANCE_DELETE_ACCESS_KEY = ''
        PREVIOUS_GOVERNANCE_LEDGER_ACCESS_KEY = ''
        GOVERNANCE_LEDGER_SIGNING_KEY = New-RandomToken 48
        GOVERNANCE_RETENTION_SWEEP_BATCH_SIZE = '100'
        GOVERNANCE_RECOVERY_MAX_LEDGERS = '10000'
        CONTACT_ENCRYPTION_KEY = New-FernetKey
        CONTACT_LOOKUP_SECRET = New-RandomToken 48
        LLM_CONFIG_ENCRYPTION_KEY = New-FernetKey
        FEISHU_CONFIG_ENCRYPTION_KEY = New-FernetKey
        LLM_PROVIDER_ALLOWLIST_JSON = '{}'
        OBJECT_STORAGE_CONNECT_TIMEOUT_SECONDS = '1'
        OBJECT_STORAGE_READ_TIMEOUT_SECONDS = '3'
        OBJECT_STORAGE_TOTAL_TIMEOUT_SECONDS = '4'
        CORS_ORIGINS = '["https://' + [string]$config.Domain + '"]'
        READINESS_TIMEOUT_SECONDS = '5'
        AURORA_WEB_SMOKE_MARKER = [string]$config.SharedWebsiteMarker
    }
    $envPath = Join-Path $staging '.env'
    [IO.File]::WriteAllLines($envPath, @($values.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }), [Text.UTF8Encoding]::new($false))
    $adminPath = Join-Path $staging 'bootstrap-admin.json'
    [IO.File]::WriteAllText($adminPath, (@{
        organization_slug = [string]$config.OrganizationSlug
        organization_name = [string]$config.OrganizationName
        email = [string]$config.BootstrapAdminEmail
        display_name = [string]$config.BootstrapAdminName
        password = $adminPassword
    } | ConvertTo-Json -Compress), [Text.UTF8Encoding]::new($false))

    $install = @'
set -eu
if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  command -v apt-get >/dev/null 2>&1 || { echo 'Only apt-based Linux is supported for automatic Docker installation.' >&2; exit 1; }
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io docker-compose-v2 || \
    DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io docker-compose-plugin
  systemctl enable --now docker
fi
docker info >/dev/null
'@
    $install -replace "`r`n", "`n" | & ssh -o BatchMode=yes $remoteHost 'bash -s'
    if ($LASTEXITCODE -ne 0) { throw '远端 Docker 初始化失败。' }
    & ssh -o BatchMode=yes $remoteHost "test `"`$(docker inspect --format '{{.State.Running}}' '$sharedWebsiteContainer')`" = true"
    if ($LASTEXITCODE -ne 0) {
        throw "共享官网容器 $sharedWebsiteContainer 未运行。为避免覆盖官网，部署已停止。"
    }

    & ssh -o BatchMode=yes $remoteHost "install -d -m 700 '$remoteRoot/bootstrap' /etc/beyondcandidate/tls"
    if ($LASTEXITCODE -ne 0) { throw '创建远端目录失败。' }
    $uploads = @(
        @($envPath, "${remoteHost}:$remoteRoot/bootstrap/.env"),
        @($adminPath, "${remoteHost}:$remoteRoot/bootstrap/bootstrap-admin.json"),
        @("$PSScriptRoot/bootstrap/compose.server-https.yaml", "${remoteHost}:$remoteRoot/bootstrap/compose.server-https.yaml"),
        @("$PSScriptRoot/bootstrap/production.conf.template", "${remoteHost}:$remoteRoot/bootstrap/production.conf.template"),
        @([string]$config.TlsCertificatePath, "${remoteHost}:/etc/beyondcandidate/tls/fullchain.pem"),
        @([string]$config.TlsPrivateKeyPath, "${remoteHost}:/etc/beyondcandidate/tls/private.key")
    )
    foreach ($upload in $uploads) {
        & scp -o BatchMode=yes $upload[0] $upload[1]
        if ($LASTEXITCODE -ne 0) { throw "上传初始化文件失败：$($upload[0])" }
    }
    & ssh -o BatchMode=yes $remoteHost "chmod 600 '$remoteRoot/bootstrap/.env' '$remoteRoot/bootstrap/bootstrap-admin.json' /etc/beyondcandidate/tls/private.key; chmod 644 /etc/beyondcandidate/tls/fullchain.pem"
    if ($LASTEXITCODE -ne 0) { throw '设置远端文件权限失败。' }

    Write-Host "全新服务器初始化材料已就绪。管理员：$($config.BootstrapAdminEmail)"
    Write-Host "一次性初始密码：$adminPassword"
    Write-Host '请在首次登录后立即修改密码。'
} finally {
    if (Test-Path -LiteralPath $staging) {
        Remove-Item -LiteralPath $staging -Recurse -Force
    }
}
