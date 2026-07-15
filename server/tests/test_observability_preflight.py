from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[2]
PREFLIGHT = ROOT / "deploy" / "observability-preflight.sh"


def _shell_path(path: Path) -> str:
    value = path.resolve().as_posix()
    if len(value) >= 3 and value[1:3] == ":/":
        return f"/{value[0].lower()}{value[2:]}"
    return value


def test_observability_preflight_is_executable_and_calls_fixed_three_file_model(
    tmp_path: Path,
) -> None:
    assert PREFLIGHT.is_file()
    index_entry = subprocess.run(
        ["git", "ls-files", "--stage", "--", str(PREFLIGHT.relative_to(ROOT))],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert index_entry.startswith("100755 ")
    source = PREFLIGHT.read_text(encoding="utf-8")
    assert "production-preflight.sh" in source

    docker_shim = tmp_path / "docker"
    docker_shim.write_text(
        """#!/bin/sh
printf '%s\n' "$*" >> "$COMPOSE_CALL_LOG"
if [ "$1" = compose ] && [ "$2" = version ] && [ "$3" = --short ]; then
    printf '%s\n' '2.24.4'
fi
""",
        encoding="utf-8",
    )
    docker_shim.chmod(0o755)
    call_log = tmp_path / "compose-calls.log"
    environment = os.environ.copy()
    environment.update(
        {
            "COMPOSE_CALL_LOG": _shell_path(call_log),
            "COMPOSE_ENV_FILE": "deploy/.env.example",
        }
    )
    shell = shutil.which("sh") or "sh"

    result = subprocess.run(
        [
            shell,
            "-c",
            'PATH="$1:$PATH"; export PATH; exec sh "$2"',
            "observability-preflight-test",
            _shell_path(tmp_path),
            _shell_path(PREFLIGHT),
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    calls = call_log.read_text(encoding="utf-8").splitlines()
    assert calls[0] == "compose version --short"
    config_calls = [line.replace("\\", "/") for line in calls if " config " in line]
    assert len(config_calls) == 2
    assert "deploy/compose.yaml" in config_calls[0]
    assert "deploy/compose.production.yaml" in config_calls[0]
    assert "deploy/compose.observability.yaml" not in config_calls[0]
    assert "deploy/compose.yaml" in config_calls[1]
    assert "deploy/compose.production.yaml" in config_calls[1]
    assert "deploy/compose.observability.yaml" in config_calls[1]
