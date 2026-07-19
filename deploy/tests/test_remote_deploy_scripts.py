from pathlib import Path
import subprocess


ROOT = Path(__file__).parents[2]
BASH = r"C:\Program Files\Git\bin\bash.exe"
POWERSHELL = (ROOT / "deploy" / "deploy-remote.ps1").read_text(encoding="utf-8")
REMOTE_SHELL = (ROOT / "deploy" / "remote-release.sh").read_text(encoding="utf-8")
REMOTE_ROLLBACK = (ROOT / "deploy" / "remote-rollback.sh").read_text(encoding="utf-8")
PRODUCTION_SMOKE = (
    ROOT
    / "docs"
    / "design"
    / "prototypes"
    / "ats-low-fi-option-2"
    / "scripts"
    / "production-browser-smoke.cjs"
).read_text(encoding="utf-8")


def test_local_deploy_fails_closed_and_uses_versioned_artifacts() -> None:
    assert "Refusing to deploy a dirty worktree" in POWERSHELL
    assert '[ValidateSet("frontend", "all")]' in POWERSHELL
    assert 'beyondcandidate-frontend:$releaseId' in POWERSHELL
    assert 'beyondcandidate-server:$releaseId' in POWERSHELL
    assert 'beyondcandidate-deploy-$releaseId' in POWERSHELL
    assert "--exclude=.tmp" in POWERSHELL
    assert "--exclude=.venv*" in POWERSHELL
    assert 'Join-Path $tempRoot "beyondcandidate-deploy-"' in POWERSHELL
    assert "Local staging cleanup was skipped" in POWERSHELL
    assert "[Parameter(ValueFromRemainingArguments" not in POWERSHELL
    assert "function Invoke-Native" in POWERSHELL
    assert "$commandName = [string]$args[0]" in POWERSHELL
    assert "function Copy-RemoteArtifact" in POWERSHELL
    assert "ServerAliveInterval=15" in POWERSHELL
    assert "scp failed after 3 attempts" in POWERSHELL
    assert "Production browser smoke failed; requesting release rollback" in POWERSHELL
    assert "remote-rollback.sh" in POWERSHELL


def test_container_test_gate_excludes_contracts_that_require_host_tools() -> None:
    assert "--ignore=server/tests/test_backup_restore_contract.py" in POWERSHELL
    assert "--ignore=server/tests/test_observability_preflight.py" in POWERSHELL
    assert "--ignore=server/tests/test_production_topology.py" in POWERSHELL
    assert "--ignore=server/tests/test_observability_topology.py" in POWERSHELL


def test_remote_release_preserves_project_identity_and_rolls_back_services() -> None:
    assert "docker compose -p beyondcandidate" in REMOTE_SHELL
    assert 'previous_release=$(readlink -f "$app_root/current")' in REMOTE_SHELL
    assert "rollback_services" in REMOTE_SHELL
    assert "python -m alembic -c server/alembic.ini upgrade head" in REMOTE_SHELL
    assert "10-provision-app-role.sh" in REMOTE_SHELL
    assert "shared-nginx-smoke.sh" in REMOTE_SHELL
    assert 'mv -Tf "$app_root/current.new" "$app_root/current"' in REMOTE_SHELL


def test_release_inherits_shared_nginx_before_compose_validation() -> None:
    copy_index = REMOTE_SHELL.index("production.conf.template")
    config_index = REMOTE_SHELL.index("config --quiet")
    assert copy_index < config_index


def test_release_and_rollback_use_three_domain_smoke_without_orphan_cleanup() -> None:
    for source in (REMOTE_SHELL, REMOTE_ROLLBACK):
        assert "shared-nginx-smoke.sh" in source
        assert "--remove-orphans" not in source


def test_rollback_uses_current_release_smoke_for_legacy_target() -> None:
    assert 'smoke_tool="$current_release/deploy/shared-nginx-smoke.sh"' in REMOTE_ROLLBACK
    assert '"$previous_release/deploy/shared-nginx-smoke.sh"' not in REMOTE_ROLLBACK


def test_release_revalidates_previous_services_after_automatic_rollback() -> None:
    assert "restore_previous_and_verify" in REMOTE_SHELL
    assert "rollback verification failed; previous release is not healthy" in REMOTE_SHELL


def test_release_marker_failure_rolls_back_without_composing_aurora_web(tmp_path) -> None:
    def bash_path(path: Path) -> str:
        value = path.as_posix()
        return f"/{value[0].lower()}{value[2:]}"

    app_root = tmp_path / "app"
    previous = app_root / "releases" / "previous"
    candidate = app_root / "releases" / "candidate"
    staging = tmp_path / "staging"
    for release in (previous, candidate):
        (release / "deploy" / "nginx").mkdir(parents=True)
        (release / "deploy" / ".env").write_text(
            "AURORA_WEB_SMOKE_MARKER=expected website marker\n",
            encoding="utf-8",
        )
        (release / "deploy" / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
        (release / "deploy" / "compose.server-https.yaml").write_text(
            "services:\n  proxy:\n    image: beyondcandidate-frontend:old\n",
            encoding="utf-8",
        )
        (release / "deploy" / "nginx" / "production.conf.template").write_text(
            """
server { server_name hr.aurora-tek.cn; location / { proxy_pass http://api:8000; } }
server { server_name aurora-tek.cn www.aurora-tek.cn; location / { proxy_pass http://aurora-web:3000; } }
""",
            encoding="utf-8",
        )
    (candidate / "deploy" / "remote-release.sh").write_text(REMOTE_SHELL, encoding="utf-8")
    (candidate / "deploy" / "shared_nginx_release_validator.py").write_text(
        (ROOT / "deploy" / "shared_nginx_release_validator.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    smoke_script = candidate / "deploy" / "shared-nginx-smoke.sh"
    smoke_script.write_text(
        (ROOT / "deploy" / "shared-nginx-smoke.sh").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (staging / "frontend-image.tar").parent.mkdir()
    (staging / "frontend-image.tar").write_bytes(b"image")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    compose_log = tmp_path / "compose.log"
    curl_log = tmp_path / "curl.log"
    compose_log.touch()
    curl_log.touch()
    (bin_dir / "docker").write_text(
        """#!/bin/sh
if [ \"$1\" = compose ]; then
    printf '%s\\n' \"$*\" >> \"$COMPOSE_LOG\"
    exit 0
fi
if [ \"$1\" = inspect ]; then
    case \"$*\" in
        *Networks*) printf '%s\\n' '{\"beyondcandidate_edge\":{}}' ;;
        *aurora-web*) printf '%s\\n' 'aurora-web-stable-id' ;;
        *) printf '%s\\n' healthy ;;
    esac
fi
exit 0
""",
        encoding="utf-8",
    )
    (bin_dir / "curl").write_text(
        """#!/bin/sh
printf '%s\\n' \"$*\" >> \"$CURL_LOG\"
case \"$*\" in
    *aurora-tek.cn*) printf '%s\\n' 'wrong website marker' ;;
esac
exit 0
""",
        encoding="utf-8",
    )
    (bin_dir / "readlink").write_text(
        f"#!/bin/sh\nprintf '%s\\n' '{bash_path(previous)}'\n",
        encoding="utf-8",
    )
    (bin_dir / "python3").write_text(
        "#!/bin/sh\nprintf '%s\\n' 'expected website marker'\n",
        encoding="utf-8",
    )
    for command in (bin_dir / "docker", bin_dir / "curl", bin_dir / "readlink", bin_dir / "python3"):
        command.chmod(0o755)

    result = subprocess.run(
        [
            r"C:\Program Files\Git\bin\bash.exe",
            "-c",
            'export PATH="$1:$PATH" COMPOSE_LOG="$2" CURL_LOG="$3"; shift 3; exec "$@"',
            "bash",
            bash_path(bin_dir),
            bash_path(compose_log),
            bash_path(curl_log),
            bash_path(candidate / "deploy" / "remote-release.sh"),
            "candidate",
            "frontend",
            "hr.aurora-tek.cn",
            bash_path(app_root),
            bash_path(staging),
            "commit",
            "sha256",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "shared routing verification failed; rolling back services" in result.stderr, (
        f"stdout={result.stdout!r} stderr={result.stderr!r} "
        f"compose={compose_log.read_text(encoding='utf-8')!r}"
    )
    assert "rollback verification failed; previous release is not healthy" in result.stderr
    assert "aurora-web" not in compose_log.read_text(encoding="utf-8")
    assert compose_log.read_text(encoding="utf-8").count("exec -T proxy nginx -t") == 2
    assert len(curl_log.read_text(encoding="utf-8").splitlines()) == 6


def test_rollback_uses_current_smoke_when_legacy_target_has_none(tmp_path) -> None:
    def bash_path(path: Path) -> str:
        value = path.as_posix()
        return f"/{value[0].lower()}{value[2:]}"

    app_root = tmp_path / "app"
    current = app_root / "releases" / "current"
    legacy = app_root / "releases" / "f6be6dc"
    template = (
        "server { server_name hr.aurora-tek.cn; location / { proxy_pass http://api:8000; } }\n"
        "server { server_name aurora-tek.cn www.aurora-tek.cn; location / { proxy_pass http://aurora-web:3000; } }\n"
    )
    for release in (current, legacy):
        (release / "deploy" / "nginx").mkdir(parents=True)
        (release / "deploy" / ".env").write_text("AURORA_WEB_SMOKE_MARKER=marker\n", encoding="utf-8")
        (release / "deploy" / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
        (release / "deploy" / "compose.server-https.yaml").write_text("services: {}\n", encoding="utf-8")
        (release / "deploy" / "nginx" / "production.conf.template").write_text(template, encoding="utf-8")
    (current / "deploy" / "release-info.txt").write_text(
        f"scope=frontend\nprevious_release={bash_path(legacy)}\n", encoding="utf-8"
    )
    for name in ("remote-rollback.sh", "shared-nginx-smoke.sh"):
        (current / "deploy" / name).write_text((ROOT / "deploy" / name).read_text(encoding="utf-8"), encoding="utf-8")
    (legacy / "deploy" / "shared_nginx_release_validator.py").write_text(
        (ROOT / "deploy" / "shared_nginx_release_validator.py").read_text(encoding="utf-8"), encoding="utf-8"
    )

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    curl_log = tmp_path / "curl.log"
    curl_log.touch()
    (bin_dir / "docker").write_text(
        """#!/bin/sh
if [ "$1" = inspect ]; then case "$*" in *Networks*) echo '{"beyondcandidate_edge":{}}' ;; *aurora-web*) echo aurora-web-id ;; *) echo healthy ;; esac; fi
""", encoding="utf-8"
    )
    (bin_dir / "curl").write_text("#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$CURL_LOG\"\necho marker\n", encoding="utf-8")
    (bin_dir / "readlink").write_text(f"#!/bin/sh\necho '{bash_path(current)}'\n", encoding="utf-8")
    (bin_dir / "python3").write_text("#!/bin/sh\necho marker\n", encoding="utf-8")
    for command in bin_dir.iterdir():
        command.chmod(0o755)

    result = subprocess.run(
        [BASH, "-c", 'export PATH="$1:$PATH" CURL_LOG="$2"; shift 2; exec "$@"', "bash", bash_path(bin_dir), bash_path(curl_log), bash_path(current / "deploy" / "remote-rollback.sh"), bash_path(app_root), "hr.aurora-tek.cn", "current"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert len(curl_log.read_text(encoding="utf-8").splitlines()) == 4
    assert not (legacy / "deploy" / "shared-nginx-smoke.sh").exists()


def test_production_smoke_accepts_problem_json_for_anonymous_identity() -> None:
    assert r"application\/(?:problem\+)?json" in PRODUCTION_SMOKE


def test_remote_rollback_is_version_guarded_and_health_checked() -> None:
    assert 'current_release=$(readlink -f "$app_root/current")' in REMOTE_ROLLBACK
    assert 'if [ "$current_release" != "$expected_path" ]' in REMOTE_ROLLBACK
    assert "docker compose -p beyondcandidate" in REMOTE_ROLLBACK
    assert "shared-nginx-smoke.sh" in REMOTE_ROLLBACK
    assert 'mv -Tf "$app_root/current.new" "$app_root/current"' in REMOTE_ROLLBACK
