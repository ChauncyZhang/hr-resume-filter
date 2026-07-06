import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from resume_filter import (  # noqa: E402
    CandidateScore,
    _estimate_years,
    extract_text,
    score_resume,
    run_screening,
)


class ResumeFilterTests(unittest.TestCase):
    def test_extract_text_reads_utf8_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            resume = Path(tmp) / "candidate.txt"
            resume.write_text("张三\nPython 后端工程师\n5年经验\n本科", encoding="utf-8")

            self.assertIn("Python 后端工程师", extract_text(resume))

    def test_score_resume_marks_required_terms_and_ranks_match(self):
        jd = """
        岗位：Python 后端工程师
        必须条件：Python, FastAPI, 本科
        加分项：Docker, PostgreSQL
        """
        resume = "李四，5年 Python / FastAPI 后端经验，本科，熟悉 Docker。"

        result = score_resume(resume, jd, "李四.txt")

        self.assertIsInstance(result, CandidateScore)
        self.assertEqual(result.required_hit_count, 3)
        self.assertEqual(result.required_missing, "")
        self.assertGreaterEqual(result.score, 80)
        self.assertIn("Python", result.matched_terms)

    def test_score_resume_lists_missing_required_terms(self):
        jd = "必须条件：Python, FastAPI, 本科"
        resume = "王五，Java 后端，专科，3年经验。"

        result = score_resume(resume, jd, "王五.txt")

        self.assertLess(result.score, 60)
        self.assertIn("Python", result.required_missing)
        self.assertIn("FastAPI", result.required_missing)
        self.assertIn("本科", result.required_missing)

    def test_run_screening_exports_ranked_csv(self):
        jd = "必须条件：Python, FastAPI, 本科\n加分项：Docker"
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            input_dir = base / "resumes"
            input_dir.mkdir()
            (input_dir / "strong.txt").write_text(
                "Python FastAPI 本科 Docker 后端工程师", encoding="utf-8"
            )
            (input_dir / "weak.txt").write_text("Java 专科", encoding="utf-8")
            jd_path = base / "jd.txt"
            jd_path.write_text(jd, encoding="utf-8")
            output_csv = base / "candidates.csv"

            rows = run_screening(input_dir, jd_path, output_csv)

            self.assertEqual([row.file_name for row in rows], ["strong.txt", "weak.txt"])
            with output_csv.open("r", encoding="utf-8-sig", newline="") as handle:
                exported = list(csv.DictReader(handle))
            self.assertEqual(exported[0]["文件名"], "strong.txt")
            self.assertIn("缺失必须条件", exported[0])

    def test_estimate_years_ignores_four_digit_dates(self):
        text = "2024年09月 - 2026年05月，拥有5年 Python 后端经验。"

        self.assertEqual(_estimate_years(text), 5)


if __name__ == "__main__":
    unittest.main()
