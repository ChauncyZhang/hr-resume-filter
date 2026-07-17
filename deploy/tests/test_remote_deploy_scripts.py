from pathlib import Path


ROOT = Path(__file__).parents[2]
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


def test_remote_release_preserves_project_identity_and_rolls_back_services() -> None:
    assert "docker compose -p beyondcandidate" in REMOTE_SHELL
    assert 'previous_release=$(readlink -f "$app_root/current")' in REMOTE_SHELL
    assert "rollback_services" in REMOTE_SHELL
    assert "python -m alembic -c server/alembic.ini upgrade head" in REMOTE_SHELL
    assert "10-provision-app-role.sh" in REMOTE_SHELL
    assert "https://$domain/health/ready" in REMOTE_SHELL
    assert 'mv -Tf "$app_root/current.new" "$app_root/current"' in REMOTE_SHELL


def test_production_smoke_accepts_problem_json_for_anonymous_identity() -> None:
    assert r"application\/(?:problem\+)?json" in PRODUCTION_SMOKE


def test_remote_rollback_is_version_guarded_and_health_checked() -> None:
    assert 'current_release=$(readlink -f "$app_root/current")' in REMOTE_ROLLBACK
    assert 'if [ "$current_release" != "$expected_path" ]' in REMOTE_ROLLBACK
    assert "docker compose -p beyondcandidate" in REMOTE_ROLLBACK
    assert 'https://$domain/health/ready' in REMOTE_ROLLBACK
    assert 'mv -Tf "$app_root/current.new" "$app_root/current"' in REMOTE_ROLLBACK
