import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from web_app import (  # noqa: E402
    AppConfigStore,
    LLMConfig,
    _normalize_llm_endpoint,
    analyze_resume_uploads,
    iter_resume_analysis_events,
    parse_server_args,
    test_llm_connection,
)


class WebAppTests(unittest.TestCase):
    def test_analyze_resume_uploads_returns_chinese_fields_sorted_by_score(self):
        jd_text = "必须条件：Python, FastAPI, 本科\n加分项：Docker"
        uploads = [
            ("weak.txt", b"Java backend"),
            ("strong.txt", "Python FastAPI 本科 Docker 5年经验".encode("utf-8")),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            rows = analyze_resume_uploads(jd_text, uploads, Path(tmp))

        self.assertEqual(rows[0]["文件名"], "strong.txt")
        self.assertGreater(rows[0]["匹配分"], rows[1]["匹配分"])
        self.assertIn("推荐结论", rows[0])
        self.assertIn("缺失必须条件", rows[0])

    def test_analyze_resume_uploads_rejects_empty_jd(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                analyze_resume_uploads("", [("resume.txt", b"Python")], Path(tmp))

    def test_parse_server_args_uses_linux_deploy_environment(self):
        env = {"HR_RESUME_HOST": "0.0.0.0", "HR_RESUME_PORT": "8080"}

        args = parse_server_args([], env)

        self.assertEqual(args.host, "0.0.0.0")
        self.assertEqual(args.port, 8080)

    def test_analyze_resume_uploads_can_add_llm_evaluation(self):
        jd_text = "required: Python, LLM"
        uploads = [("ai.txt", b"Python LLM Agent")]
        config = LLMConfig(
            enabled=True,
            provider="openai_compatible",
            base_url="https://example.test/v1/chat/completions",
            model="test-model",
            api_key="secret",
        )

        def fake_client(config, jd_text, resume_text, rule_row):
            return {
                "llm_score": 92,
                "llm_recommendation": "优先沟通",
                "llm_summary": "LLM Agent 经验匹配。",
                "llm_risks": "需要确认生产落地经验。",
                "interview_questions": "讲一个 Agent 项目。",
            }

        with tempfile.TemporaryDirectory() as tmp:
            rows = analyze_resume_uploads(
                jd_text, uploads, Path(tmp), llm_config=config, llm_client=fake_client
            )

        self.assertEqual(rows[0]["LLM评分"], 92)
        self.assertEqual(rows[0]["LLM结论"], "优先沟通")
        self.assertIn("Agent", rows[0]["LLM理由"])
        self.assertIn("生产", rows[0]["风险点"])
        self.assertIn("Agent", rows[0]["面试问题"])

    def test_config_store_persists_llm_settings_and_jobs(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = AppConfigStore(Path(tmp) / "config.json")

            store.save_settings(
                {
                    "llm_provider": "openai_compatible",
                    "llm_base_url": "https://api.example.com/v1",
                    "llm_model": "gpt-test",
                    "llm_api_key": "secret",
                    "llm_enabled": True,
                    "save_api_key": True,
                }
            )
            saved_job = store.upsert_job("AI 工程师", "必须条件：Python, LLM")

            reloaded = AppConfigStore(Path(tmp) / "config.json")
            data = reloaded.load()

        self.assertEqual(data["settings"]["llm_provider"], "openai_compatible")
        self.assertEqual(data["settings"]["llm_model"], "gpt-test")
        self.assertTrue(data["settings"]["llm_enabled"])
        self.assertEqual(data["settings"]["llm_api_key"], "secret")
        self.assertEqual(data["jobs"][0]["id"], saved_job["id"])
        self.assertEqual(data["jobs"][0]["title"], "AI 工程师")

    def test_config_store_does_not_store_api_key_unless_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = AppConfigStore(Path(tmp) / "config.json")

            store.save_settings(
                {
                    "llm_provider": "openai_compatible",
                    "llm_base_url": "https://api.example.com/v1",
                    "llm_model": "gpt-test",
                    "llm_api_key": "secret",
                    "save_api_key": False,
                }
            )

            data = store.load()

        self.assertEqual(data["settings"]["llm_api_key"], "")

    def test_config_store_can_delete_saved_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = AppConfigStore(Path(tmp) / "config.json")
            job = store.upsert_job("AI 工程师", "必须条件：Python")

            deleted = store.delete_job(job["id"])

        self.assertTrue(deleted)
        self.assertEqual(store.load()["jobs"], [])

    def test_llm_connection_test_uses_minimal_prompt(self):
        config = LLMConfig(
            enabled=True,
            provider="openai_compatible",
            base_url="https://example.test/v1",
            model="test-model",
            api_key="secret",
        )

        def fake_client(config, jd_text, resume_text, rule_row):
            self.assertIn("连接测试", jd_text)
            self.assertEqual(resume_text, "这是一次连接测试。")
            return {
                "llm_score": 100,
                "llm_recommendation": "可沟通",
                "llm_summary": "连接正常",
                "llm_risks": "",
                "interview_questions": "",
            }

        result = test_llm_connection(config, fake_client)

        self.assertTrue(result["ok"])
        self.assertIn("连接正常", result["message"])

    def test_bigmodel_base_url_appends_chat_completions_path(self):
        config = LLMConfig(
            provider="openai_compatible",
            base_url="https://open.bigmodel.cn/api/paas/v4",
            model="glm-5.2",
        )

        endpoint = _normalize_llm_endpoint(config)

        self.assertEqual(
            endpoint,
            "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        )

    def test_iter_resume_analysis_events_reports_progress(self):
        uploads = [
            ("one.txt", b"Python LLM"),
            ("two.txt", b"Java"),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            events = list(
                iter_resume_analysis_events(
                    "required: Python",
                    uploads,
                    Path(tmp),
                    llm_config=LLMConfig(enabled=False),
                )
            )

        progress_events = [event for event in events if event["type"] == "progress"]
        done_events = [event for event in events if event["type"] == "done"]
        self.assertEqual(len(progress_events), 2)
        self.assertEqual(progress_events[0]["current"], 1)
        self.assertEqual(progress_events[0]["total"], 2)
        self.assertEqual(progress_events[0]["file_name"], "one.txt")
        self.assertEqual(done_events[0]["count"], 2)


if __name__ == "__main__":
    unittest.main()
