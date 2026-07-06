import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class UiLayoutTests(unittest.TestCase):
    def test_llm_settings_are_in_settings_dialog_not_main_sidebar(self):
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

        self.assertIn('id="settingsBtn"', html)
        self.assertIn('id="settingsDialog"', html)
        self.assertIn('id="llmEnabled"', html)
        side_stack = html.split('<div class="side-stack">', 1)[1].split("</div>", 1)[0]
        self.assertNotIn('id="llmEnabled"', side_stack)


if __name__ == "__main__":
    unittest.main()
