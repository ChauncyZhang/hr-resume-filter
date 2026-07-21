[CmdletBinding()]
param(
    [ValidateSet("frontend", "all")]
    [string]$Scope = "all",
    [string]$RemoteHost = "root@120.79.184.221",
    [string]$Domain = "hr.aurora-tek.cn",
    [string]$RemoteRoot = "/opt/beyondcandidate",
    [switch]$AllowDirty,
    [switch]$SkipTests,
    [switch]$KeepArtifacts,
    [switch]$ValidateOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-Native {
    if ($args.Count -lt 1) { throw "Invoke-Native requires a command" }
    $commandName = [string]$args[0]
    [string[]]$commandArguments = if ($args.Count -gt 1) { @($args[1..($args.Count - 1)]) } else { @() }

    & $commandName @commandArguments
    if ($LASTEXITCODE -ne 0) {
        throw "$commandName failed with exit code $LASTEXITCODE"
    }
}

function Assert-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name is required"
    }
}

function Copy-RemoteArtifact([string]$Source, [string]$Destination) {
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        & scp -C -o BatchMode=yes -o ConnectTimeout=15 -o ServerAliveInterval=15 -o ServerAliveCountMax=4 `
            $Source $Destination
        if ($LASTEXITCODE -eq 0) { return }
        if ($attempt -lt 3) {
            Write-Warning "Artifact upload attempt $attempt failed; retrying"
            Start-Sleep -Seconds (2 * $attempt)
        }
    }
    throw "scp failed after 3 attempts: $([System.IO.Path]::GetFileName($Source))"
}

function Remove-SafeStagingDirectory([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $resolvedPath = (Resolve-Path -LiteralPath $Path).Path
    $tempRoot = (Resolve-Path -LiteralPath ([System.IO.Path]::GetTempPath())).Path.TrimEnd("\\")
    $allowedPrefix = Join-Path $tempRoot "beyondcandidate-deploy-"
    if (-not $resolvedPath.StartsWith($allowedPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove unexpected staging path: $resolvedPath"
    }
    Remove-Item -LiteralPath $resolvedPath -Recurse -Force
}

function Invoke-SharedNginxReleaseGate([string]$RepositoryRoot) {
    $gitBash = "C:\Program Files\Git\bin\bash.exe"
    if (-not (Test-Path -LiteralPath $gitBash -PathType Leaf)) {
        throw "Git Bash is required for the shared Nginx release gate"
    }

    Push-Location $RepositoryRoot
    try {
        Invoke-Native python -m pytest `
            deploy/tests/test_shared_nginx_release_validator.py `
            deploy/tests/test_remote_deploy_scripts.py `
            -q -p no:cacheprovider
        Invoke-Native $gitBash -n deploy/shared-nginx-smoke.sh
    } finally {
        Pop-Location
    }
}

if ($RemoteHost -notmatch '^[A-Za-z0-9_.-]+@[A-Za-z0-9_.-]+$') {
    throw "RemoteHost must use the form user@host"
}
if ($Domain -notmatch '^[A-Za-z0-9.-]+$') {
    throw "Domain contains unsupported characters"
}
if ($RemoteRoot -notmatch '^/[A-Za-z0-9._/-]+$') {
    throw "RemoteRoot must be an absolute Linux path"
}

foreach ($command in @("git", "docker", "ssh", "scp", "tar")) {
    Assert-Command $command
}

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$prototypeRoot = Join-Path $repositoryRoot "docs\design\prototypes\ats-low-fi-option-2"
$commit = (& git -C $repositoryRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $commit -notmatch '^[0-9a-f]{40}$') {
    throw "Unable to resolve the release commit"
}
$shortCommit = $commit.Substring(0, 8)
$dirtyLines = @(& git -C $repositoryRoot status --porcelain --untracked-files=normal)
if ($LASTEXITCODE -ne 0) { throw "Unable to inspect repository status" }
$isDirty = $dirtyLines.Count -gt 0

$dirtySuffix = if ($isDirty) { "-dirty" } else { "" }
$releaseId = "{0}-{1}{2}" -f [DateTime]::UtcNow.ToString("yyyyMMdd-HHmmss"), $shortCommit, $dirtySuffix
$localStaging = Join-Path ([System.IO.Path]::GetTempPath()) "beyondcandidate-deploy-$releaseId"
$remoteStaging = "/tmp/beyondcandidate-deploy-$releaseId"
$frontendImage = "beyondcandidate-frontend:$releaseId"
$appImage = "beyondcandidate-server:$releaseId"
$sourceArchive = Join-Path $localStaging "source.tar.gz"
$frontendArchive = Join-Path $localStaging "frontend-image.tar"
$appArchive = Join-Path $localStaging "app-image.tar"

Write-Host "[deploy] release=$releaseId scope=$Scope host=$RemoteHost"
Write-Host "[deploy] commit=$commit dirty=$isDirty"
Invoke-SharedNginxReleaseGate $repositoryRoot
if ($ValidateOnly) {
    Write-Host "[deploy] shared Nginx release gate passed; no build or remote change performed"
    return
}
if ($isDirty -and -not $AllowDirty) {
    throw "Refusing to deploy a dirty worktree. Commit the release or use -AllowDirty for an explicit emergency deployment."
}

try {
    Invoke-Native docker info --format "{{.ServerVersion}}"

    if (-not $SkipTests) {
        Push-Location $prototypeRoot
        try {
            Assert-Command "npm.cmd"
            Invoke-Native npm.cmd test
            Invoke-Native npm.cmd run build
        } finally {
            Pop-Location
        }

        if ($Scope -eq "all") {
            $testImage = "beyondcandidate-server-test:$releaseId"
            Invoke-Native docker build --target test -t $testImage -f (Join-Path $repositoryRoot "server\Dockerfile") $repositoryRoot
            Invoke-Native docker run --rm $testImage python -m pytest server/tests `
                --ignore=server/tests/test_backup_restore_contract.py `
                --ignore=server/tests/test_observability_preflight.py `
                --ignore=server/tests/test_production_topology.py `
                --ignore=server/tests/test_observability_topology.py `
                -q
        }
    }

    Invoke-Native docker build -f (Join-Path $repositoryRoot "deploy\nginx\Dockerfile") -t $frontendImage $prototypeRoot
    if ($Scope -eq "all") {
        Invoke-Native docker build --target runtime -f (Join-Path $repositoryRoot "server\Dockerfile") -t $appImage $repositoryRoot
    }

    New-Item -ItemType Directory -Force -Path $localStaging | Out-Null
    Invoke-Native docker save -o $frontendArchive $frontendImage
    if ($Scope -eq "all") {
        Invoke-Native docker save -o $appArchive $appImage
    }
    Push-Location $localStaging
    try {
        Invoke-Native tar -czf "source.tar.gz" `
            --exclude=.git `
            --exclude=.worktrees `
            --exclude=.tmp `
            --exclude=.pytest_cache `
            --exclude=.superpowers `
            --exclude=node_modules `
            --exclude=dist `
            "--exclude=.venv*" `
            --exclude=__pycache__ `
            -C $repositoryRoot .
    } finally {
        Pop-Location
    }

    $sourceSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $sourceArchive).Hash.ToLowerInvariant()
    Invoke-Native ssh -o BatchMode=yes -o ConnectTimeout=15 $RemoteHost "mkdir -p '$remoteStaging'"
    Copy-RemoteArtifact $sourceArchive "${RemoteHost}:${remoteStaging}/source.tar.gz"
    Copy-RemoteArtifact $frontendArchive "${RemoteHost}:${remoteStaging}/frontend-image.tar"
    if ($Scope -eq "all") {
        Copy-RemoteArtifact $appArchive "${RemoteHost}:${remoteStaging}/app-image.tar"
    }

    $bootstrap = @'
set -eu
release="$1"
scope="$2"
domain="$3"
app_root="$4"
staging="$5"
commit="$6"
source_sha="$7"
release_dir="$app_root/releases/$release"
if [ -e "$release_dir" ]; then
  printf 'release directory already exists: %s\n' "$release_dir" >&2
  exit 1
fi
mkdir -p "$release_dir"
tar -xzf "$staging/source.tar.gz" -C "$release_dir"
chmod 750 "$release_dir/deploy/remote-release.sh"
chmod 750 "$release_dir/deploy/remote-rollback.sh"
exec "$release_dir/deploy/remote-release.sh" "$release" "$scope" "$domain" "$app_root" "$staging" "$commit" "$source_sha"
'@
    $bootstrap = $bootstrap -replace "`r`n", "`n"
    $bootstrap | & ssh -o BatchMode=yes $RemoteHost "bash -s -- '$releaseId' '$Scope' '$Domain' '$RemoteRoot' '$remoteStaging' '$commit' '$sourceSha'"
    if ($LASTEXITCODE -ne 0) { throw "Remote release failed with exit code $LASTEXITCODE" }

    Push-Location $prototypeRoot
    try {
        $previousProductionUrl = $env:UX09_PRODUCTION_URL
        try {
            $env:UX09_PRODUCTION_URL = "https://$Domain/"
            Invoke-Native node scripts/production-browser-smoke.cjs
        } catch {
            Write-Warning "Production browser smoke failed; requesting release rollback"
            & ssh -o BatchMode=yes -o ConnectTimeout=15 $RemoteHost `
                "'$RemoteRoot/current/deploy/remote-rollback.sh' '$RemoteRoot' '$Domain' '$releaseId'"
            if ($LASTEXITCODE -ne 0) {
                Write-Warning "Automatic rollback failed; inspect release $releaseId immediately"
            }
            throw
        } finally {
            $env:UX09_PRODUCTION_URL = $previousProductionUrl
        }
    } finally {
        Pop-Location
    }
    Write-Host "[deploy] release $releaseId is healthy at https://$Domain/"
} finally {
    if (-not $KeepArtifacts) {
        try {
            Remove-SafeStagingDirectory $localStaging
        } catch {
            Write-Warning "Local staging cleanup was skipped: $($_.Exception.Message)"
        }
    } else {
        Write-Host "[deploy] retained local artifacts: $localStaging"
    }
}
