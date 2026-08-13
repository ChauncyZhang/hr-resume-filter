from pathlib import Path
from subprocess import CompletedProcess

from deploy.ensure_deployment_test_env import (
    PINNED_PYTEST_VERSION,
    ensure_deployment_test_python,
    venv_python_path,
)


class FakeRunner:
    def __init__(self, root: Path, versions: list[str | None]) -> None:
        self.root = root
        self.versions = versions
        self.calls: list[list[str]] = []

    def __call__(self, command, **kwargs):
        command = [str(item) for item in command]
        self.calls.append(command)
        if command[1:4] == ["-m", "venv", str(self.root / ".venv")]:
            python = venv_python_path(self.root)
            python.parent.mkdir(parents=True, exist_ok=True)
            python.touch()
            return CompletedProcess(command, 0, "", "")
        if command[1:3] == ["-m", "pip"]:
            return CompletedProcess(command, 0, "", "")
        version = self.versions.pop(0)
        return CompletedProcess(command, 0 if version is not None else 1, f"{version or ''}\n", "")


def test_reuses_environment_only_when_pytest_version_matches(tmp_path: Path) -> None:
    python = venv_python_path(tmp_path)
    python.parent.mkdir(parents=True)
    python.touch()
    runner = FakeRunner(tmp_path, [PINNED_PYTEST_VERSION])

    assert ensure_deployment_test_python(tmp_path, run=runner) == python
    assert len(runner.calls) == 1


def test_repairs_an_existing_environment_with_the_wrong_pytest_version(tmp_path: Path) -> None:
    python = venv_python_path(tmp_path)
    python.parent.mkdir(parents=True)
    python.touch()
    runner = FakeRunner(tmp_path, ["7.4.0", PINNED_PYTEST_VERSION])

    assert ensure_deployment_test_python(tmp_path, run=runner) == python
    assert any(f"pytest=={PINNED_PYTEST_VERSION}" in call for call in runner.calls)
    assert all(call[1:3] != ["-m", "venv"] for call in runner.calls)


def test_creates_the_environment_when_it_does_not_exist(tmp_path: Path) -> None:
    runner = FakeRunner(tmp_path, [PINNED_PYTEST_VERSION])

    python = ensure_deployment_test_python(tmp_path, bootstrap_python="bootstrap-python", run=runner)

    assert python == venv_python_path(tmp_path)
    assert runner.calls[0] == ["bootstrap-python", "-m", "venv", str(tmp_path / ".venv")]
    assert any(f"pytest=={PINNED_PYTEST_VERSION}" in call for call in runner.calls)
