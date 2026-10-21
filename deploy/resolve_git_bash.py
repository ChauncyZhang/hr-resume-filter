import shutil
import sys
from pathlib import Path


def resolve_git_bash(git_executable: str | None = None) -> str:
    """Use Git for Windows' Bash, not a WindowsApps/WSL PATH shim."""
    git_executable = git_executable or shutil.which("git")
    if not git_executable:
        raise RuntimeError("Git is required to locate Git Bash for deployment checks")
    git_dir = Path(git_executable).resolve().parent
    for candidate in (
        git_dir / "bash.exe",
        git_dir.parent / "bin" / "bash.exe",
        git_dir.parent.parent / "bin" / "bash.exe",
    ):
        if candidate.is_file():
            return str(candidate)
    raise RuntimeError(f"Git Bash is required beside the active Git installation: {git_executable}")


if __name__ == "__main__":
    try:
        print(resolve_git_bash(sys.argv[1] if len(sys.argv) > 1 else None))
    except RuntimeError as error:
        sys.exit(str(error))
