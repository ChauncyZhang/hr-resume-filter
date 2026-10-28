"""Offline branding gate: strict config, release packaging, scope and Compose merge."""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest

from deploy.resolve_git_bash import resolve_git_bash


ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "deploy/deploy-remote.ps1"
PWSH = shutil.which("pwsh")


def test_deployed_display_name_matches_requested_capitalization():
    config = json.loads((ROOT / "deploy/branding.json").read_text(encoding="utf-8"))
    assert config["name"] == "Ji Guang"
    assert config["short_name"] == "JG"


@pytest.fixture
def ps_helpers(tmp_path):
    harness = tmp_path / "helpers.ps1"
    harness.write_text(
        """$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$ast = [System.Management.Automation.Language.Parser]::ParseFile($env:BRAND_SCRIPT, [ref]$null, [ref]$null)
$ast.FindAll({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst]}, $false) | ForEach-Object {
    Invoke-Expression $_.Extent.Text
}
""",
        encoding="utf-8",
    )

    def run(body, **environment):
        command = tmp_path / "case.ps1"
        command.write_text(harness.read_text(encoding="utf-8") + body, encoding="utf-8")
        return subprocess.run(
            [PWSH, "-NoProfile", "-File", str(command)],
            env={**os.environ, "BRAND_SCRIPT": str(SCRIPT), **environment},
            capture_output=True, text=True, encoding="utf-8", check=False,
        )

    return run


def make_brand(path, config=None):
    path.mkdir(parents=True, exist_ok=True)
    (path / "branding").mkdir(exist_ok=True)
    (path / "branding/logo.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8")
    (path / "branding.json").write_text(
        json.dumps(config if config is not None else {"name": "jiguang", "short_name": "JG", "logo_url": "/branding/logo.svg"}),
        encoding="utf-8",
    )
    shutil.copyfile(ROOT / "deploy/compose.branding.yaml", path / "compose.branding.yaml")
    return path


@pytest.mark.parametrize("config", [
    {"name": "jiguang", "short_name": "JG", "logo_url": None},
    {"name": "  jiguang  ", "short_name": "JG123", "logo_url": "/branding/logo.svg", "favicon_url": None},
    {"name": "x" * 80, "short_name": "A1", "logo_url": "/favicon.svg"},
    {"name": "\U0001f600" * 80, "short_name": "JG", "logo_url": None},
])
def test_valid_brand_config(ps_helpers, tmp_path, config):
    root = make_brand(tmp_path / "source", config)
    result = ps_helpers("Get-ProductBrandingHash $env:BRAND_ROOT", BRAND_ROOT=str(root))
    assert result.returncode == 0, result.stderr
    assert re.fullmatch(r"[0-9a-f]{64}\s*", result.stdout)


@pytest.mark.parametrize("field,value", [
    ("name", " "), ("name", "x" * 81), ("name", 5),
    ("name", "a\tb"), ("name", "a\nb"), ("name", "a\x7fb"), ("name", "\U0001f600" * 81),
    ("short_name", "JG_"), ("short_name", "j" * 9), ("short_name", "非"),
    ("logo_url", "https://example.test/logo.svg"), ("logo_url", "//example.test/x"),
    ("logo_url", "/x?query"), ("logo_url", "/x#hash"), ("logo_url", "/x\\y"),
    ("logo_url", "/a/../x"), ("logo_url", "/a/.."), ("logo_url", "/a\nx"),
    ("logo_url", "/a/%2e%2e/x"), ("logo_url", "/%2fhost/x"),
    ("logo_url", "/a/%252e%252e/x"), ("logo_url", "/a/%2525255cx"),
    ("logo_url", "/a b"), ("logo_url", "/a%"), ("logo_url", "/%FF"),
    ("logo_url", "/branding/missing.svg"), ("favicon_url", False), ("extra", "value"),
])
def test_invalid_brand_config_fails_closed(ps_helpers, tmp_path, field, value):
    root = make_brand(tmp_path / "source")
    config = json.loads((root / "branding.json").read_text(encoding="utf-8"))
    config[field] = value
    (root / "branding.json").write_text(json.dumps(config), encoding="utf-8")
    result = ps_helpers("Get-ProductBrandingHash $env:BRAND_ROOT", BRAND_ROOT=str(root))
    assert result.returncode != 0


@pytest.mark.parametrize("raw", [
    '[]', '{}', '{"name":"one","name":"two","short_name":"JG","logo_url":null}',
    '{"name":"one","short_name":"JG","logo_url":null,}',
    '{/* comment */"name":"one","short_name":"JG","logo_url":null}',
])
def test_json_is_strict(ps_helpers, tmp_path, raw):
    root = make_brand(tmp_path / "source")
    (root / "branding.json").write_text(raw, encoding="utf-8")
    result = ps_helpers("Get-ProductBrandingHash $env:BRAND_ROOT", BRAND_ROOT=str(root))
    assert result.returncode != 0


def test_missing_logo_key_is_rejected(ps_helpers, tmp_path):
    root = make_brand(tmp_path / "source", {"name": "jiguang", "short_name": "JG"})
    result = ps_helpers("Get-ProductBrandingHash $env:BRAND_ROOT", BRAND_ROOT=str(root))
    assert result.returncode != 0
    assert "Branding is missing logo_url" in result.stderr


@pytest.mark.parametrize("filename", [".env", "private.pem", "index.html"])
def test_non_image_assets_are_rejected(ps_helpers, tmp_path, filename):
    root = make_brand(tmp_path / "source")
    nested = root / "branding/nested"
    nested.mkdir()
    (nested / filename).write_text("not a public image", encoding="utf-8")
    result = ps_helpers("Get-ProductBrandingHash $env:BRAND_ROOT", BRAND_ROOT=str(root))
    assert result.returncode != 0
    assert "Branding assets must use an allowed image extension" in result.stderr


@pytest.mark.parametrize("extension", ["SVG", "PNG", "JPG", "JPEG", "GIF", "WEBP", "ICO", "AVIF", "BMP"])
def test_image_extensions_allow_subdirectories_and_case(ps_helpers, tmp_path, extension):
    root = make_brand(tmp_path / "source")
    nested = root / "branding/nested"
    nested.mkdir()
    (nested / f"image.{extension}").write_bytes(b"trusted image fixture")
    result = ps_helpers("Get-ProductBrandingHash $env:BRAND_ROOT", BRAND_ROOT=str(root))
    assert result.returncode == 0, result.stderr


def test_packaged_files_and_digest_track_config_assets_and_names(ps_helpers, tmp_path):
    source = make_brand(tmp_path / "source")
    destination = tmp_path / "release/deploy"
    destination.mkdir(parents=True)
    result = ps_helpers("""
$first = Get-ProductBrandingHash $env:BRAND_ROOT
Copy-ProductBranding $env:BRAND_ROOT $env:DESTINATION
$copy = Get-ProductBrandingHash $env:DESTINATION
[IO.File]::AppendAllText((Join-Path $env:BRAND_ROOT 'branding/logo.svg'), 'changed')
$asset = Get-ProductBrandingHash $env:BRAND_ROOT
Rename-Item -LiteralPath (Join-Path $env:BRAND_ROOT 'branding/logo.svg') -NewName 'other.svg'
$json = '{"name":"jiguang","short_name":"JG","logo_url":null}'
[IO.File]::WriteAllText((Join-Path $env:BRAND_ROOT 'branding.json'), $json)
$renamed = Get-ProductBrandingHash $env:BRAND_ROOT
@($first, $copy, $asset, $renamed) | ConvertTo-Json -Compress
""", BRAND_ROOT=str(source), DESTINATION=str(destination))
    assert result.returncode == 0, result.stderr
    first, copied, asset, renamed = json.loads(result.stdout)
    assert first == copied
    assert len({first, asset, renamed}) == 3
    assert (destination / "branding.sha256").read_text().strip() == first
    for name in ("branding.json", "branding/logo.svg", "compose.branding.yaml"):
        assert (destination / name).is_file()


@pytest.mark.parametrize("requested,active,files,expected", [
    ("auto", "same", "frontend/App.tsx", "frontend"),
    ("auto", "same", "server/app.py", "all"),
    ("auto", "same", "", "frontend"),
    ("auto", "different", "", "all"),
    ("auto", "", "", "all"),
    ("frontend", "same", "", "frontend"),
    ("frontend", "different", "", "reject"),
    ("frontend", "", "", "reject"),
    ("frontend", "unreachable", "", "reject"),
    ("all", "different", "", "all"),
])
def test_scope_compares_private_digest_even_without_product_change(ps_helpers, requested, active, files, expected):
    result = ps_helpers("""
function ssh {
    if ($env:ACTIVE -eq 'unreachable') { $global:LASTEXITCODE = 1; return }
    $global:LASTEXITCODE = 0
    'a' * 40
    if ($env:ACTIVE -eq 'same') { 'b' * 64 }
    elseif ($env:ACTIVE -eq 'different') { 'c' * 64 }
}
function git { $global:LASTEXITCODE = 0; if ($args -contains 'diff' -and $env:FILES) { $env:FILES } }
Resolve-DeploymentScope $env:REQUESTED '.' ('a' * 40) 'user@host' '/opt/app' ('b' * 64)
""", REQUESTED=requested, ACTIVE=active, FILES=files)
    if expected == "reject":
        assert result.returncode != 0
        assert "scope=all" in result.stderr
    else:
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip().splitlines()[-1] == expected


def test_actual_compose_merge_preserves_tls_and_uses_only_private_brand(ps_helpers, tmp_path):
    # Use the canonical sibling while the submodule intentionally remains pinned.
    public = ROOT.parent / "beyondcandidate"
    if not public.is_dir():
        public = ROOT / "product"
    deploy = tmp_path / "release/deploy"
    deploy.mkdir(parents=True)
    shutil.copyfile(public / "deploy/compose.yaml", deploy / "compose.yaml")
    shutil.copyfile(ROOT / "deploy/bootstrap/compose.server-https.yaml", deploy / "compose.server-https.yaml")
    shutil.copyfile(public / "deploy/.env.example", deploy / ".env")
    result = ps_helpers("Copy-ProductBranding $env:BRAND_ROOT $env:DESTINATION", BRAND_ROOT=str(ROOT / "deploy"), DESTINATION=str(deploy))
    assert result.returncode == 0, result.stderr

    def render(branding):
        command = ["docker", "compose", "--env-file", str(deploy / ".env"), "-f", str(deploy / "compose.yaml"), "-f", str(deploy / "compose.server-https.yaml")]
        if branding:
            command += ["-f", str(deploy / "compose.branding.yaml")]
        process = subprocess.run(command + ["config", "--format", "json"], capture_output=True, text=True, check=False)
        assert process.returncode == 0, process.stderr
        return json.loads(process.stdout)["services"]

    before, after = render(False), render(True)
    for service in ("api", "worker", "proxy"):
        target = "/usr/share/nginx/html/branding.json" if service == "proxy" else "/run/product-branding.json"
        mounts = {mount["target"]: mount for mount in after[service]["volumes"]}
        assert Path(mounts[target]["source"]).resolve() == (deploy / "branding.json").resolve()
        assert mounts[target]["read_only"]
        for old in before[service].get("volumes", []):
            if old["target"] != target:
                assert mounts[old["target"]] == old
        if service != "proxy":
            assert after[service]["environment"]["PRODUCT_BRANDING_FILE"] == target
    proxy = {mount["target"]: mount for mount in after["proxy"]["volumes"]}
    assert proxy["/usr/share/nginx/html/branding"]["read_only"]
    assert "/etc/nginx/tls/tls.crt" in proxy
    assert "/etc/nginx/tls/tls.key" in proxy
    for service in after:
        if service not in ("api", "worker", "proxy"):
            assert after[service] == before[service]


def bash_path(path):
    value = path.as_posix()
    return f"/{value[0].lower()}{value[2:]}" if path.drive else value


@pytest.mark.parametrize("script,function", [("remote-release.sh", "compose_at"), ("remote-rollback.sh", "compose_previous")])
@pytest.mark.parametrize("branded", [False, True])
def test_release_and_rollback_append_optional_overlay_last(tmp_path, script, function, branded):
    release = tmp_path / "release"
    (release / "deploy").mkdir(parents=True)
    if branded:
        (release / "deploy/compose.branding.yaml").touch()
    source = (ROOT / "deploy" / script).read_text(encoding="utf-8")
    helper = re.search(rf"^{function}\(\) \{{.*?^\}}", source, re.M | re.S).group()
    invocation = f'{function} "$previous_release" config --quiet' if function == "compose_at" else f'{function} config --quiet'
    result = subprocess.run([resolve_git_bash(), "-c", f'previous_release="$1"; docker() {{ printf "%s\\n" "$@"; }};\n{helper}\n{invocation}', "bash", bash_path(release)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    args = result.stdout.splitlines()
    overlays = [arg for arg in args if arg.endswith(".yaml")]
    assert [Path(arg).name for arg in overlays] == ["compose.yaml", "compose.server-https.yaml"] + (["compose.branding.yaml"] if branded else [])
    assert args[-2:] == ["config", "--quiet"]


def test_branding_is_packaged_before_source_archive_and_allows_bootstrap():
    source = SCRIPT.read_text(encoding="utf-8")
    assert source.index("Copy-ProductBranding $PSScriptRoot") < source.index("Invoke-Native tar -czf $sourceArchive")
    remote = (ROOT / "deploy/remote-release.sh").read_text(encoding="utf-8")
    # First release consumes this same source package, never server bootstrap branding.
    assert 'configuration_root=$app_root/bootstrap' in remote
    assert '"$release_dir/deploy/branding.json"' in remote
    assert 'branding_changed=1' in remote
    assert 'recreate_option=--force-recreate' in remote
    assert "printf 'branding_sha256=%s\\n'" in remote


@pytest.mark.parametrize("scope,changed,bootstrap", [
    ("frontend", True, False), ("frontend", False, False),
    ("all", True, False), ("all", True, True),
])
def test_remote_release_brand_guard_and_restart_without_real_services(tmp_path, scope, changed, bootstrap):
    app = tmp_path / "app"
    previous = app / "releases/previous"
    candidate = app / "releases/candidate"
    staging = tmp_path / "staging"
    staging.mkdir()
    for name in ("frontend-image.tar", "app-image.tar"):
        (staging / name).touch()
    configuration = app / "bootstrap" if bootstrap else previous / "deploy"
    configuration.mkdir(parents=True)
    (configuration / ".env").write_text("AURORA_WEB_SMOKE_MARKER=marker\n", encoding="utf-8")
    shutil.copyfile(ROOT / "deploy/bootstrap/compose.server-https.yaml", configuration / "compose.server-https.yaml")
    template = configuration / "production.conf.template" if bootstrap else configuration / "nginx/production.conf.template"
    template.parent.mkdir(exist_ok=True)
    template.write_text("mock template", encoding="utf-8")
    if bootstrap:
        (configuration / "bootstrap-admin.json").write_text("{}", encoding="utf-8")
    else:
        (configuration / "release-info.txt").write_text(f"branding_sha256={'c' * 64 if changed else 'b' * 64}\n", encoding="utf-8")
    deploy = make_brand(candidate / "deploy")
    (deploy / "nginx").mkdir()
    (deploy / "branding.sha256").write_text("b" * 64, encoding="utf-8")
    (deploy / "compose.yaml").write_text("services: {}", encoding="utf-8")
    (deploy / "shared-nginx-smoke.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (deploy / "shared_nginx_release_validator.py").touch()
    shutil.copyfile(ROOT / "deploy/remote-release.sh", deploy / "remote-release.sh")
    binary = tmp_path / "bin"
    binary.mkdir()
    log = tmp_path / "docker.log"
    docker = '''#!/bin/sh
printf '%s\\n' "$*" >> "$DOCKER_LOG"
if [ "$1" = inspect ]; then
    case "$*" in
        *Networks*) echo '{"beyondcandidate_edge":{}}' ;;
        *aurora-web*) echo website-stable-id ;;
        *) echo healthy ;;
    esac
fi
exit 0
'''
    (binary / "docker").write_text(docker, encoding="utf-8")
    (binary / "readlink").write_text(f"#!/bin/sh\necho '{'' if bootstrap else bash_path(previous)}'\n", encoding="utf-8")
    (binary / "python3").write_text("#!/bin/sh\necho marker\n", encoding="utf-8")
    # Do not switch links or remove fixtures; these are not needed for the restart contract.
    for name in ("mv", "ln", "rm"):
        (binary / name).write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    for path in binary.iterdir():
        path.chmod(0o755)
    result = subprocess.run([
        resolve_git_bash(), "-c",
        'export PATH="$1:$PATH" DOCKER_LOG="$2"; shift 2; exec sh "$@"',
        "bash", bash_path(binary), bash_path(log), bash_path(deploy / "remote-release.sh"),
        "candidate", scope, "example.test", bash_path(app), bash_path(staging), "commit", "source-sha",
    ], capture_output=True, text=True, encoding="utf-8", check=False)
    if scope == "frontend" and changed:
        assert result.returncode != 0
        assert "branding changed; scope=all is required" in result.stderr
        assert not log.exists()
        return
    assert result.returncode == 0, result.stderr
    calls = log.read_text(encoding="utf-8").splitlines()
    up = [line for line in calls if " up " in line and "api worker proxy" in line]
    if scope == "all":
        assert len(up) == 1
        assert "--no-deps --no-build --force-recreate api worker proxy" in up[0]
        assert "compose.branding.yaml" in up[0]
    else:
        assert not up
        assert any("--force-recreate proxy" in line for line in calls)
    assert f"branding_sha256={'b' * 64}" in (deploy / "release-info.txt").read_text(encoding="utf-8")
    assert not any("aurora-web" in line for line in calls if line.startswith("compose "))
