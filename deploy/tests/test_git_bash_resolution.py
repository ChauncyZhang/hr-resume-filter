from pathlib import Path
import subprocess

import pytest

from deploy.resolve_git_bash import resolve_git_bash


@pytest.mark.parametrize("git_location", ["cmd/git.exe", "bin/git.exe", "mingw64/bin/git.exe"])
def test_resolves_bash_in_relocated_git_installation(tmp_path, monkeypatch, git_location):
    root = tmp_path / "relocated tools" / "Git"
    git = root / git_location
    git.parent.mkdir(parents=True)
    git.touch()
    bash = root / "bin" / "bash.exe"
    bash.parent.mkdir(parents=True, exist_ok=True)
    bash.touch()
    shim = tmp_path / "WindowsApps" / "bash.exe"
    shim.parent.mkdir()
    shim.touch()
    monkeypatch.setattr("shutil.which", lambda name: str(git if name == "git" else shim))

    assert resolve_git_bash() == str(bash)
    assert resolve_git_bash(str(git)) == str(bash)


def test_missing_git_or_bash_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    with pytest.raises(RuntimeError, match="Git is required"):
        resolve_git_bash()
    git = tmp_path / "Git" / "cmd" / "git.exe"
    git.parent.mkdir(parents=True)
    git.touch()
    with pytest.raises(RuntimeError, match="Git Bash is required"):
        resolve_git_bash(str(git))


def test_resolved_bash_really_checks_shell_syntax():
    bash = resolve_git_bash()
    for source, expected_success in [("echo valid\n", True), ("if then\n", False)]:
        result = subprocess.run([bash, "-n"], input=source, capture_output=True, text=True)
        assert (result.returncode == 0) is expected_success, result.stderr


def test_release_gate_uses_resolver_without_removing_executable_checks():
    root = Path(__file__).parents[2]
    source = (root / "deploy" / "deploy-remote.ps1").read_text(encoding="utf-8")
    assert "Get-Command git -CommandType Application" in source
    assert '& python (Join-Path $RepositoryRoot "deploy\\resolve_git_bash.py") $gitCommand.Source' in source
    assert "$LASTEXITCODE -ne 0 -or $gitBashLines.Count -ne 1" in source
    assert "Invoke-Native $testPython -m pytest" in source
    assert "Invoke-Native $gitBash -n deploy/shared-nginx-smoke.sh" in source
    assert "deploy/tests/test_git_bash_resolution.py" in source
    verify = (root / "验证代码.ps1").read_text(encoding="utf-8")
    assert '"$root/deploy/tests/test_git_bash_resolution.py"' in verify
