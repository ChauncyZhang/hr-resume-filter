import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LauncherTests(unittest.TestCase):
    def test_macos_launcher_bootstraps_venv_and_starts_web_app(self):
        script = (ROOT / "start_hr_resume_filter.command").read_text(encoding="utf-8")

        self.assertIn("python3 -m venv", script)
        self.assertIn(".venv/bin/python", script)
        self.assertIn("requirements.txt", script)
        self.assertIn("web_app.py", script)
        self.assertIn("--port", script)
        self.assertIn("open \"${URL}\"", script)


if __name__ == "__main__":
    unittest.main()
