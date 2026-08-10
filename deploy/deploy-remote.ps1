[CmdletBinding()]
param(
    [ValidateSet("auto", "frontend", "all")]
    [string]$Scope = "auto",
    [string]$RemoteHost = "root@120.79.184.221",
    [string]$Domain = "hr.aurora-tek.cn",
    [string]$RemoteRoot = "/opt/beyondcandidate",
    [switch]$AllowDirty,
    [switch]$RunFullTests,
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

function Assert-PublishedMainCommit(
    [string]$RepositoryRoot,
    [string]$Commit,
    [string]$RepositoryLabel,
    [switch]$AllowPinnedAncestor
) {
    $fetched = $false
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        & git -C $RepositoryRoot fetch --quiet origin main
        if ($LASTEXITCODE -eq 0) {
            $fetched = $true
            break
        }
        if ($attempt -lt 3) {
            Write-Warning "Published commit check for $RepositoryLabel failed on attempt $attempt; retrying"
            Start-Sleep -Seconds (2 * $attempt)
        }
    }
    if (-not $fetched) {
        throw "Unable to resolve origin/main for $RepositoryLabel"
    }
    $remoteCommit = (& git -C $RepositoryRoot rev-parse FETCH_HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $remoteCommit -notmatch '^[0-9a-f]{40}$') {
        throw "Unable to resolve the fetched origin/main commit for $RepositoryLabel"
    }
    if ($AllowPinnedAncestor) {
        & git -C $RepositoryRoot merge-base --is-ancestor $Commit $remoteCommit
        if ($LASTEXITCODE -ne 0) {
            throw "$RepositoryLabel HEAD is not published in origin/main history. Push the reviewed commit before deployment."
        }
    } elseif ($remoteCommit -ne $Commit) {
        throw "$RepositoryLabel HEAD is not published at origin/main. Push the reviewed commit before deployment."
    }
}

function Resolve-DeploymentScope(
    [string]$RequestedScope,
    [string]$ProductRoot,
    [string]$ProductCommit,
    [string]$RemoteHost,
    [string]$RemoteRoot
) {
    if ($RequestedScope -ne "auto") { return $RequestedScope }

    $metadataPath = "$RemoteRoot/current/deploy/release-info.txt"
    $remoteCommand = "if [ -f '$metadataPath' ]; then sed -n 's/^git_commit=//p' '$metadataPath' | head -1; fi"
    $currentCommitLines = @(& ssh -o BatchMode=yes -o ConnectTimeout=15 -o ConnectionAttempts=3 -o ServerAliveInterval=15 -o ServerAliveCountMax=4 $RemoteHost $remoteCommand)
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Unable to inspect the active release; using full deployment scope"
        return "all"
    }
    $currentCommit = if ($currentCommitLines.Count -gt 0) { ([string]$currentCommitLines[0]).Trim() } else { "" }
    if ($currentCommit -notmatch '^[0-9a-f]{40}$') {
        Write-Host "[deploy] no comparable active product commit; selected scope=all"
        return "all"
    }

    & git -C $ProductRoot cat-file -e "$currentCommit^{commit}" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Active product commit is unavailable locally; using full deployment scope"
        return "all"
    }
    $changedFiles = @(& git -C $ProductRoot diff --name-only "$currentCommit..$ProductCommit" --)
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Unable to compare product commits; using full deployment scope"
        return "all"
    }
    $backendChanges = @($changedFiles | Where-Object { $_ -notlike 'frontend/*' })
    $resolvedScope = if ($backendChanges.Count -eq 0) { "frontend" } else { "all" }
    Write-Host "[deploy] auto scope=$resolvedScope changed_files=$($changedFiles.Count)"
    return $resolvedScope
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

function Invoke-SharedRouteSafetyGate([string]$RepositoryRoot) {
    $gitBash = "C:\Program Files\Git\bin\bash.exe"
    if (-not (Test-Path -LiteralPath $gitBash -PathType Leaf)) {
        throw "Git Bash is required for the shared route safety gate"
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
$productRoot = (Resolve-Path (Join-Path $repositoryRoot "product")).Path
$prototypeRoot = Join-Path $productRoot "frontend"
$internalCommit = (& git -C $repositoryRoot rev-parse HEAD).Trim()
$commit = (& git -C $productRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $commit -notmatch '^[0-9a-f]{40}$' -or $internalCommit -notmatch '^[0-9a-f]{40}$') {
    throw "Unable to resolve the internal or product release commit"
}
$shortCommit = $commit.Substring(0, 8)
$shortInternalCommit = $internalCommit.Substring(0, 8)
$dirtyLines = @(& git -C $repositoryRoot status --porcelain --untracked-files=normal)
if ($LASTEXITCODE -ne 0) { throw "Unable to inspect repository status" }
$productDirtyLines = @(& git -C $productRoot status --porcelain --untracked-files=normal)
if ($LASTEXITCODE -ne 0) { throw "Unable to inspect product submodule status" }
$isDirty = $dirtyLines.Count -gt 0 -or $productDirtyLines.Count -gt 0

if ($isDirty -and -not $AllowDirty) {
    throw "Refusing to deploy a dirty worktree. Commit the release or use -AllowDirty for an explicit emergency deployment."
}
if (-not $AllowDirty) {
    Assert-PublishedMainCommit $repositoryRoot $internalCommit "internal repository"
    Assert-PublishedMainCommit $productRoot $commit "product repository" -AllowPinnedAncestor
}
$Scope = Resolve-DeploymentScope $Scope $productRoot $commit $RemoteHost $RemoteRoot

$dirtySuffix = if ($isDirty) { "-dirty" } else { "" }
$releaseId = "{0}-{1}-{2}{3}" -f [DateTime]::UtcNow.ToString("yyyyMMdd-HHmmss"), $shortCommit, $shortInternalCommit, $dirtySuffix
$localStaging = Join-Path ([System.IO.Path]::GetTempPath()) "beyondcandidate-deploy-$releaseId"
$remoteStaging = "/tmp/beyondcandidate-deploy-$releaseId"
$frontendImage = "beyondcandidate-frontend:$releaseId"
$appImage = "beyondcandidate-server:$releaseId"
$sourceArchive = Join-Path $localStaging "source.tar.gz"
$frontendArchive = Join-Path $localStaging "frontend-image.tar"
$appArchive = Join-Path $localStaging "app-image.tar"
$releaseTree = Join-Path $localStaging "release-tree"
$productArchive = Join-Path $localStaging "product.tar"

Write-Host "[deploy] release=$releaseId scope=$Scope host=$RemoteHost"
Write-Host "[deploy] product_commit=$commit internal_commit=$internalCommit dirty=$isDirty"
Invoke-SharedRouteSafetyGate $repositoryRoot
if ($ValidateOnly) {
    Write-Host "[deploy] shared route safety gate passed; existing Nginx configuration was not changed"
    return
}

try {
    Invoke-Native docker info --format "{{.ServerVersion}}"

    Push-Location $prototypeRoot
    try {
        Assert-Command "npm.cmd"
        Invoke-Native npm.cmd ci --no-audit --no-fund
    } finally {
        Pop-Location
    }

    if ($RunFullTests) {
        Push-Location $prototypeRoot
        try {
            Invoke-Native npm.cmd test
        } finally {
            Pop-Location
        }

        if ($Scope -eq "all") {
            $testImage = "beyondcandidate-server-test:$releaseId"
            Invoke-Native docker build --target test -t $testImage -f (Join-Path $productRoot "server\Dockerfile") $productRoot
            Invoke-Native docker run --rm $testImage python -m pytest server/tests `
                --ignore=server/tests/test_backup_restore_contract.py `
                --ignore=server/tests/test_observability_preflight.py `
                --ignore=server/tests/test_production_topology.py `
                --ignore=server/tests/test_observability_topology.py `
                -q
        }
    } else {
        Write-Host "[deploy] release mode: full product tests are not repeated; use -RunFullTests only when explicitly required"
    }

    Invoke-Native docker build -f (Join-Path $productRoot "deploy\nginx\Dockerfile") -t $frontendImage $productRoot
    if ($Scope -eq "all") {
        Invoke-Native docker build --target runtime -f (Join-Path $productRoot "server\Dockerfile") -t $appImage $productRoot
    }

    New-Item -ItemType Directory -Force -Path $localStaging | Out-Null
    Invoke-Native docker save -o $frontendArchive $frontendImage
    if ($Scope -eq "all") {
        Invoke-Native docker save -o $appArchive $appImage
    }
    New-Item -ItemType Directory -Force -Path $releaseTree | Out-Null
    if ($isDirty -and $AllowDirty) {
        Invoke-Native tar -cf $productArchive `
            --exclude=.git --exclude=.tmp --exclude=.pytest_cache `
            --exclude=node_modules --exclude=dist "--exclude=.venv*" --exclude=__pycache__ `
            -C $productRoot .
    } else {
        Invoke-Native git -C $productRoot archive --format=tar --output=$productArchive HEAD
    }
    Invoke-Native tar -xf $productArchive -C $releaseTree
    foreach ($privateFile in @(
        "remote-release.sh",
        "remote-rollback.sh",
        "shared_nginx_release_validator.py",
        "shared-nginx-smoke.sh"
    )) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot $privateFile) `
            -Destination (Join-Path $releaseTree "deploy\$privateFile") -Force
    }
    Invoke-Native tar -czf $sourceArchive -C $releaseTree .

    $sourceSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $sourceArchive).Hash.ToLowerInvariant()
    Invoke-Native ssh -o BatchMode=yes -o ConnectTimeout=15 -o ConnectionAttempts=3 -o ServerAliveInterval=15 -o ServerAliveCountMax=4 $RemoteHost "mkdir -p '$remoteStaging'"
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
    $bootstrap | & ssh -o BatchMode=yes -o ConnectTimeout=15 -o ConnectionAttempts=3 -o ServerAliveInterval=15 -o ServerAliveCountMax=4 $RemoteHost "bash -s -- '$releaseId' '$Scope' '$Domain' '$RemoteRoot' '$remoteStaging' '$commit' '$sourceSha'"
    if ($LASTEXITCODE -ne 0) { throw "Remote release failed with exit code $LASTEXITCODE" }

    Push-Location $prototypeRoot
    try {
        $previousProductionUrl = $env:UX09_PRODUCTION_URL
        $previousNodePath = $env:NODE_PATH
        try {
            $env:UX09_PRODUCTION_URL = "https://$Domain/"
            $env:NODE_PATH = Join-Path $prototypeRoot "node_modules"
            Invoke-Native node (Join-Path $PSScriptRoot "production-browser-smoke.cjs")
        } catch {
            Write-Warning "Production browser smoke failed; requesting release rollback"
            & ssh -o BatchMode=yes -o ConnectTimeout=15 -o ConnectionAttempts=3 -o ServerAliveInterval=15 -o ServerAliveCountMax=4 $RemoteHost `
                "'$RemoteRoot/current/deploy/remote-rollback.sh' '$RemoteRoot' '$Domain' '$releaseId'"
            if ($LASTEXITCODE -ne 0) {
                Write-Warning "Automatic rollback failed; inspect release $releaseId immediately"
            }
            throw
        } finally {
            $env:UX09_PRODUCTION_URL = $previousProductionUrl
            $env:NODE_PATH = $previousNodePath
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
