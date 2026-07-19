from pathlib import Path
import subprocess


ROOT = Path(__file__).parents[2]
SMOKE_SCRIPT = ROOT / "deploy" / "shared-nginx-smoke.sh"
BASH = r"C:\Program Files\Git\bin\bash.exe"


def _bash_path(path: Path) -> str:
    value = path.as_posix()
    return f"/{value[0].lower()}{value[2:]}"


def _run_smoke(tmp_path: Path, *, marker: str = "website marker", body: str = "website marker"):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    curl_log = tmp_path / "curl.log"
    curl_log.touch()
    (bin_dir / "docker").write_text(
        """#!/bin/sh
if [ "$1" = inspect ]; then
    case "$*" in
        *Networks*) printf '%s\\n' '{"beyondcandidate_edge":{}}' ;;
        *aurora-web*) printf '%s\\n' 'aurora-web-stable-id' ;;
    esac
fi
""",
        encoding="utf-8",
    )
    (bin_dir / "curl").write_text(
        """#!/bin/sh
printf '%s\\n' "$*" >> "$CURL_LOG"
printf '%s\\n' "$FAKE_CURL_BODY"
""",
        encoding="utf-8",
    )
    for command in (bin_dir / "docker", bin_dir / "curl"):
        command.chmod(0o755)

    result = subprocess.run(
        [
            BASH,
            "-c",
            'export PATH="$1:$PATH" CURL_LOG="$2" FAKE_CURL_BODY="$3" AURORA_WEB_SMOKE_MARKER="$4"; shift 4; exec "$@"',
            "bash",
            _bash_path(bin_dir),
            _bash_path(curl_log),
            body,
            marker,
            "sh",
            _bash_path(SMOKE_SCRIPT),
            "aurora-web-stable-id",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return result, curl_log.read_text(encoding="utf-8").splitlines()


def test_real_shared_smoke_checks_all_domains_and_follows_website_redirects(tmp_path) -> None:
    result, curl_calls = _run_smoke(tmp_path)

    assert result.returncode == 0, result.stderr
    assert len(curl_calls) == 4
    assert "https://hr.aurora-tek.cn/health/ready" in curl_calls[0]
    assert "https://hr.aurora-tek.cn/" in curl_calls[1]
    for call in curl_calls[2:]:
        assert "--location" in call
        assert "--max-redirs 3" in call
        assert "--connect-timeout 5" in call
        assert "--max-time 15" in call
        assert "--fail --silent --show-error" in call


def test_real_shared_smoke_rejects_empty_marker_without_curl(tmp_path) -> None:
    result, curl_calls = _run_smoke(tmp_path, marker="")

    assert result.returncode == 2
    assert "AURORA_WEB_SMOKE_MARKER is required" in result.stderr
    assert curl_calls == []


def test_real_shared_smoke_rejects_website_marker_mismatch(tmp_path) -> None:
    result, _ = _run_smoke(tmp_path, body="unexpected website")

    assert result.returncode != 0
