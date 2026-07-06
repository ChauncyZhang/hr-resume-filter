import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


class LauncherTests(unittest.TestCase):
    def test_macos_launcher_bootstraps_venv_and_starts_web_app(self):
        script = (REPO_ROOT / "Mac用户点我启动.command").read_text(encoding="utf-8")

        self.assertIn('APP_DIR="${SCRIPT_DIR}/app"', script)
        self.assertIn("python3 -m venv", script)
        self.assertIn(".venv/bin/python", script)
        self.assertIn("requirements.txt", script)
        self.assertIn("web_app.py", script)
        self.assertIn("--port", script)
        self.assertIn("open \"${URL}\"", script)

    def test_windows_launcher_bootstraps_venv_and_starts_web_app(self):
        script_path = REPO_ROOT / "Windows用户点我启动.bat"
        script = script_path.read_text(encoding="ascii")

        self.assertIn('cd /d "%~dp0app"', script)
        self.assertIn("HRResumeFilter.exe", script)
        self.assertIn("-m venv .venv", script)
        self.assertIn("requirements.txt", script)
        self.assertIn("web_app.py", script)
        self.assertIn("--port", script)
        script_path.read_bytes().decode("ascii")

    def test_windows_package_builder_includes_web_assets_and_launcher(self):
        script = (REPO_ROOT / "app" / "build_windows_package.ps1").read_text(encoding="utf-8")

        self.assertIn("PyInstaller", script)
        self.assertIn('Filter "Windows*.bat"', script)
        self.assertIn("config.example.json", script)
        self.assertIn("Compress-Archive", script)


if __name__ == "__main__":
    unittest.main()
