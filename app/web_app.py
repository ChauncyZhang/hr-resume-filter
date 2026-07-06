from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import tempfile
import uuid
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from http import HTTPStatus
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Callable, Iterable
from urllib import error, request
from urllib.parse import urlparse

from resume_filter import CSV_COLUMNS, extract_text, score_resume


ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"
DEFAULT_CONFIG_PATH = ROOT / "data" / "config.json"
EXAMPLE_CONFIG_PATH = ROOT / "data" / "config.example.json"
DEFAULT_PORT = 8765
DEFAULT_HOST = "127.0.0.1"
MAX_UPLOAD_BYTES = 80 * 1024 * 1024
LLM_TEXT_LIMIT = 9000
LLM_COLUMNS = [
    "LLM评分",
    "LLM结论",
    "LLM理由",
    "风险点",
    "面试问题",
    "LLM错误",
]


@dataclass(frozen=True)
class LLMConfig:
    enabled: bool = False
    provider: str = "none"
    base_url: str = ""
    model: str = ""
    api_key: str = ""
    timeout_seconds: int = 45


class AppConfigStore:
    def __init__(self, path: Path = DEFAULT_CONFIG_PATH):
        self.path = path

    def load(self) -> dict[str, object]:
        if not self.path.exists():
            return self._default_config()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return self._default_config()
        return self._normalize_config(data)

    def save_settings(self, settings: dict[str, object]) -> dict[str, object]:
        data = self.load()
        current = data["settings"]
        current.update(
            {
                "llm_provider": str(settings.get("llm_provider", "openai_compatible")),
                "llm_base_url": str(settings.get("llm_base_url", "")),
                "llm_model": str(settings.get("llm_model", "")),
                "llm_enabled": bool(settings.get("llm_enabled", False)),
                "save_api_key": bool(settings.get("save_api_key", False)),
                "llm_api_key": str(settings.get("llm_api_key", ""))
                if settings.get("save_api_key")
                else "",
            }
        )
        self._write(data)
        return data

    def upsert_job(self, title: str, jd_text: str, job_id: str = "") -> dict[str, str]:
        title = title.strip()
        jd_text = jd_text.strip()
        if not title:
            raise ValueError("请填写岗位名称。")
        if not jd_text:
            raise ValueError("请填写岗位 JD。")

        data = self.load()
        now = datetime.now(timezone.utc).isoformat()
        jobs = data["jobs"]
        target = None
        if job_id:
            target = next((job for job in jobs if job.get("id") == job_id), None)

        if target is None:
            target = {
                "id": job_id or uuid.uuid4().hex,
                "title": title,
                "jd_text": jd_text,
                "created_at": now,
                "updated_at": now,
            }
            jobs.append(target)
        else:
            target["title"] = title
            target["jd_text"] = jd_text
            target["updated_at"] = now

        jobs.sort(key=lambda job: str(job.get("updated_at", "")), reverse=True)
        self._write(data)
        return target

    def delete_job(self, job_id: str) -> bool:
        data = self.load()
        original_count = len(data["jobs"])
        data["jobs"] = [job for job in data["jobs"] if job.get("id") != job_id]
        changed = len(data["jobs"]) != original_count
        if changed:
            self._write(data)
        return changed

    def _write(self, data: dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _base_config(self) -> dict[str, object]:
        return {
            "settings": {
                "llm_provider": "openai_compatible",
                "llm_base_url": "https://api.openai.com/v1",
                "llm_model": "",
                "llm_api_key": "",
                "llm_enabled": False,
                "save_api_key": False,
            },
            "jobs": [],
        }

    def _default_config(self) -> dict[str, object]:
        if self.path == DEFAULT_CONFIG_PATH and EXAMPLE_CONFIG_PATH.exists():
            try:
                data = json.loads(EXAMPLE_CONFIG_PATH.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return self._normalize_config(data)
            except (json.JSONDecodeError, OSError):
                pass
        return self._base_config()

    def _normalize_config(self, data: dict[str, object]) -> dict[str, object]:
        default = self._base_config()
        settings = data.get("settings") if isinstance(data, dict) else {}
        jobs = data.get("jobs") if isinstance(data, dict) else []
        if isinstance(settings, dict):
            default["settings"].update(
                {
                    "llm_provider": str(settings.get("llm_provider", "openai_compatible")),
                    "llm_base_url": str(settings.get("llm_base_url", "")),
                    "llm_model": str(settings.get("llm_model", "")),
                    "llm_api_key": str(settings.get("llm_api_key", "")),
                    "llm_enabled": bool(settings.get("llm_enabled", False)),
                    "save_api_key": bool(settings.get("save_api_key", False)),
                }
            )
        if isinstance(jobs, list):
            default["jobs"] = [
                {
                    "id": str(job.get("id", "")),
                    "title": str(job.get("title", "")),
                    "jd_text": str(job.get("jd_text", "")),
                    "created_at": str(job.get("created_at", "")),
                    "updated_at": str(job.get("updated_at", "")),
                }
                for job in jobs
                if isinstance(job, dict) and job.get("id") and job.get("title")
            ]
        return default


def analyze_resume_uploads(
    jd_text: str,
    uploads: Iterable[tuple[str, bytes]],
    work_dir: Path,
    llm_config: LLMConfig | None = None,
    llm_client: Callable[[LLMConfig, str, str, dict[str, object]], dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    jd_text = jd_text.strip()
    if not jd_text:
        raise ValueError("请先填写或上传 JD。")

    upload_list = [(name, content) for name, content in uploads if content]
    if not upload_list:
        raise ValueError("请至少上传一份简历。")

    resume_dir = work_dir / "resumes"
    resume_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    llm_config = llm_config or LLMConfig()
    llm_client = llm_client or evaluate_with_llm
    for original_name, content in upload_list:
        safe_name = _safe_file_name(original_name)
        resume_path = resume_dir / safe_name
        resume_path.write_bytes(content)
        text = extract_text(resume_path)
        row = _score_to_chinese_dict(score_resume(text, jd_text, safe_name))
        _ensure_llm_fields(row)
        if llm_config.enabled:
            try:
                llm_result = llm_client(llm_config, jd_text, text, row)
                row.update(_normalize_llm_result(llm_result))
            except Exception as exc:
                row["LLM错误"] = str(exc)
        rows.append(row)

    rows.sort(key=lambda row: (-int(row.get("匹配分", 0)), str(row.get("文件名", "")).lower()))
    return rows


def iter_resume_analysis_events(
    jd_text: str,
    uploads: Iterable[tuple[str, bytes]],
    work_dir: Path,
    llm_config: LLMConfig | None = None,
    llm_client: Callable[[LLMConfig, str, str, dict[str, object]] , dict[str, object]] | None = None,
):
    jd_text = jd_text.strip()
    if not jd_text:
        raise ValueError("Please provide a JD.")

    upload_list = [(name, content) for name, content in uploads if content]
    if not upload_list:
        raise ValueError("Please upload at least one resume.")

    resume_dir = work_dir / "resumes"
    resume_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    llm_config = llm_config or LLMConfig()
    llm_client = llm_client or evaluate_with_llm
    total = len(upload_list)
    file_header = CSV_COLUMNS[0][1]
    score_header = CSV_COLUMNS[1][1]
    error_header = LLM_COLUMNS[-1]

    for index, (original_name, content) in enumerate(upload_list, start=1):
        safe_name = _safe_file_name(original_name)
        yield {
            "type": "progress",
            "current": index,
            "total": total,
            "file_name": safe_name,
            "message": f"正在处理 {index}/{total}：{safe_name}",
        }
        resume_path = resume_dir / safe_name
        resume_path.write_bytes(content)
        text = extract_text(resume_path)
        row = _score_to_chinese_dict(score_resume(text, jd_text, safe_name))
        _ensure_llm_fields(row)
        if llm_config.enabled:
            try:
                llm_result = llm_client(llm_config, jd_text, text, row)
                row.update(_normalize_llm_result(llm_result))
            except Exception as exc:
                row[error_header] = str(exc)
        rows.append(row)

    rows.sort(key=lambda row: (-int(row.get(score_header, 0)), str(row.get(file_header, "")).lower()))
    yield {"type": "done", "rows": rows, "count": len(rows)}


def evaluate_with_llm(
    config: LLMConfig, jd_text: str, resume_text: str, rule_row: dict[str, object]
) -> dict[str, object]:
    if not config.enabled:
        return {}
    if not config.model.strip():
        raise ValueError("请填写 LLM 模型名称。")
    endpoint = _normalize_llm_endpoint(config)
    messages = [
        {
            "role": "system",
            "content": (
                "你是招聘筛选助手。请只基于给定 JD 和简历文本评估候选人与岗位的匹配度。"
                "不要编造简历中不存在的信息。必须返回严格 JSON，不要输出 Markdown。"
            ),
        },
        {
            "role": "user",
            "content": (
                "请返回 JSON 字段："
                "llm_score(0-100整数), llm_recommendation(优先沟通/可沟通/需人工复核/暂缓), "
                "llm_summary(不超过80字), llm_risks(不超过80字), interview_questions(1-3个问题)。\n\n"
                f"规则初筛结果：{json.dumps(rule_row, ensure_ascii=False)}\n\n"
                f"JD：\n{jd_text[:LLM_TEXT_LIMIT]}\n\n"
                f"简历文本：\n{resume_text[:LLM_TEXT_LIMIT]}"
            ),
        },
    ]
    payload = {
        "model": config.model.strip(),
        "messages": messages,
        "temperature": 0.2,
    }
    headers = {"Content-Type": "application/json"}
    if config.api_key.strip():
        headers["Authorization"] = f"Bearer {config.api_key.strip()}"

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(endpoint, data=data, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=config.timeout_seconds) as resp:
            response_payload = json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(_format_llm_http_error(exc.code, detail)) from exc
    except error.URLError as exc:
        raise RuntimeError(f"LLM 服务不可达：{exc.reason}") from exc

    content = (
        response_payload.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )
    if not content:
        raise RuntimeError("LLM 没有返回内容。")
    return _parse_llm_json(content)


def _format_llm_http_error(status_code: int, detail: str) -> str:
    try:
        payload = json.loads(detail)
    except json.JSONDecodeError:
        payload = {}
    error_payload = payload.get("error", {}) if isinstance(payload, dict) else {}
    code = str(error_payload.get("code", ""))
    message = str(error_payload.get("message", "")).strip()
    if status_code == 429 and code == "1113":
        return (
            "LLM 请求失败：BigModel 返回 1113。通常不是本工具额度问题，而是当前 "
            "API Key / 模型 / 资源包 不匹配，或该资源包不支持这个调用入口。"
            "如果你买的是 GLM Coding Plan，请尝试 Base URL："
            "https://open.bigmodel.cn/api/coding/paas/v4。"
            f" 原始错误：{message or detail[:200]}"
        )
    return f"LLM 请求失败：HTTP {status_code} {detail[:300]}"


def test_llm_connection(
    config: LLMConfig,
    llm_client: Callable[[LLMConfig, str, str, dict[str, object]], dict[str, object]] | None = None,
) -> dict[str, object]:
    if not config.provider or config.provider == "none":
        raise ValueError("请选择 LLM Provider。")
    llm_client = llm_client or evaluate_with_llm
    result = llm_client(
        config,
        "连接测试：请返回 JSON，说明连接正常。",
        "这是一次连接测试。",
        {"文件名": "连接测试", "匹配分": 0, "推荐结论": "连接测试"},
    )
    message = str(result.get("llm_summary") or result.get("llm_recommendation") or "连接正常")
    return {"ok": True, "message": f"LLM 连接测试成功：{message}"}


class ResumeFilterHandler(SimpleHTTPRequestHandler):
    server_version = "HRResumeFilter/1.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_ROOT), **kwargs)

    def do_GET(self) -> None:
        route = urlparse(self.path).path
        if route == "/api/config":
            self._send_json(AppConfigStore().load())
            return
        if route == "/":
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self) -> None:
        route = urlparse(self.path).path
        if route == "/api/settings":
            self._handle_save_settings()
            return
        if route == "/api/llm-test":
            self._handle_llm_test()
            return
        if route == "/api/jobs":
            self._handle_save_job()
            return
        if route == "/api/analyze-stream":
            self._handle_analyze_stream()
            return
        if route != "/api/analyze":
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length <= 0:
                raise ValueError("没有收到上传内容。")
            if content_length > MAX_UPLOAD_BYTES:
                raise ValueError("上传文件过大，请分批筛选。")

            body = self.rfile.read(content_length)
            jd_text, uploads, llm_config = _parse_multipart(
                self.headers.get("Content-Type", ""), body
            )
            with tempfile.TemporaryDirectory(prefix="hr-resume-filter-") as tmp:
                rows = analyze_resume_uploads(jd_text, uploads, Path(tmp), llm_config=llm_config)
            self._send_json({"rows": rows, "count": len(rows)})
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def do_DELETE(self) -> None:
        route = urlparse(self.path).path
        match = re.fullmatch(r"/api/jobs/([A-Za-z0-9_-]+)", route)
        if not match:
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        deleted = AppConfigStore().delete_job(match.group(1))
        self._send_json({"deleted": deleted})

    def log_message(self, format: str, *args) -> None:
        return

    def _send_json(self, payload: dict[str, object], status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _handle_analyze_stream(self) -> None:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length <= 0:
                raise ValueError("No upload content received.")
            if content_length > MAX_UPLOAD_BYTES:
                raise ValueError("Upload is too large. Please split into batches.")

            body = self.rfile.read(content_length)
            jd_text, uploads, llm_config = _parse_multipart(
                self.headers.get("Content-Type", ""), body
            )
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            with tempfile.TemporaryDirectory(prefix="hr-resume-filter-") as tmp:
                for event in iter_resume_analysis_events(
                    jd_text, uploads, Path(tmp), llm_config=llm_config
                ):
                    data = json.dumps(event, ensure_ascii=False).encode("utf-8") + b"\n"
                    self.wfile.write(data)
                    self.wfile.flush()
        except Exception as exc:
            try:
                data = json.dumps(
                    {"type": "error", "error": str(exc)}, ensure_ascii=False
                ).encode("utf-8") + b"\n"
                self.wfile.write(data)
                self.wfile.flush()
            except Exception:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def _handle_save_settings(self) -> None:
        try:
            payload = self._read_json_body()
            data = AppConfigStore().save_settings(payload)
            self._send_json(data)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def _handle_save_job(self) -> None:
        try:
            payload = self._read_json_body()
            job = AppConfigStore().upsert_job(
                str(payload.get("title", "")),
                str(payload.get("jd_text", "")),
                str(payload.get("id", "")),
            )
            self._send_json({"job": job, **AppConfigStore().load()})
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def _handle_llm_test(self) -> None:
        try:
            payload = self._read_json_body()
            config = LLMConfig(
                enabled=True,
                provider=str(payload.get("llm_provider", "openai_compatible")),
                base_url=str(payload.get("llm_base_url", "")),
                model=str(payload.get("llm_model", "")),
                api_key=str(payload.get("llm_api_key", "")),
            )
            self._send_json(test_llm_connection(config))
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def _read_json_body(self) -> dict[str, object]:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            return {}
        body = self.rfile.read(content_length)
        return json.loads(body.decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    args = parse_server_args(argv)
    address = (args.host, args.port)
    server = ThreadingHTTPServer(address, ResumeFilterHandler)
    browser_host = "127.0.0.1" if args.host in {"0.0.0.0", "::"} else args.host
    url = f"http://{browser_host}:{args.port}"
    print(f"HR简历筛选工具已启动：{url}")
    print(f"监听地址：{args.host}:{args.port}")
    print("关闭这个窗口即可停止服务。")
    if not args.no_browser:
        webbrowser.open(url)
    server.serve_forever()
    return 0


def parse_server_args(
    argv: list[str] | None = None, env: dict[str, str] | None = None
) -> argparse.Namespace:
    env = os.environ if env is None else env
    parser = argparse.ArgumentParser(description="Start the HR resume filter web app.")
    parser.add_argument("--host", default=env.get("HR_RESUME_HOST", DEFAULT_HOST))
    parser.add_argument("--port", type=int, default=int(env.get("HR_RESUME_PORT", DEFAULT_PORT)))
    parser.add_argument("--no-browser", action="store_true")
    return parser.parse_args(argv)


def _parse_multipart(
    content_type: str, body: bytes
) -> tuple[str, list[tuple[str, bytes]], LLMConfig]:
    if "multipart/form-data" not in content_type:
        raise ValueError("请求格式不正确。")

    raw_message = (
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8")
        + body
    )
    message = BytesParser(policy=policy.default).parsebytes(raw_message)
    jd_text = ""
    uploads: list[tuple[str, bytes]] = []
    fields: dict[str, str] = {}

    for part in message.iter_parts():
        disposition = part.get_content_disposition()
        if disposition != "form-data":
            continue
        name = part.get_param("name", header="content-disposition")
        filename = part.get_filename()
        payload = part.get_payload(decode=True) or b""
        if name == "jd_text":
            jd_text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
            fields[name] = jd_text
        elif name == "jd_file" and filename and payload:
            jd_text = _decode_uploaded_text(filename, payload)
        elif name == "resumes" and filename and payload:
            uploads.append((filename, payload))
        elif name and not filename:
            fields[name] = payload.decode(part.get_content_charset() or "utf-8", errors="replace")

    return jd_text, uploads, _llm_config_from_fields(fields)


def _decode_uploaded_text(filename: str, payload: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in {".txt", ".md", ".csv"}:
        for encoding in ("utf-8-sig", "utf-8", "gb18030"):
            try:
                return payload.decode(encoding)
            except UnicodeDecodeError:
                continue
        return payload.decode("utf-8", errors="replace")

    with tempfile.TemporaryDirectory(prefix="hr-jd-") as tmp:
        path = Path(tmp) / _safe_file_name(filename)
        path.write_bytes(payload)
        return extract_text(path)


def _score_to_chinese_dict(row) -> dict[str, object]:
    return {header: getattr(row, field_name) for field_name, header in CSV_COLUMNS}


def _ensure_llm_fields(row: dict[str, object]) -> None:
    for column in LLM_COLUMNS:
        row.setdefault(column, "")


def _normalize_llm_result(result: dict[str, object]) -> dict[str, object]:
    return {
        "LLM评分": _clamp_score(result.get("llm_score", "")),
        "LLM结论": str(result.get("llm_recommendation", "")),
        "LLM理由": str(result.get("llm_summary", "")),
        "风险点": str(result.get("llm_risks", "")),
        "面试问题": str(result.get("interview_questions", "")),
        "LLM错误": "",
    }


def _parse_llm_json(content: str) -> dict[str, object]:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def _llm_config_from_fields(fields: dict[str, str]) -> LLMConfig:
    enabled = fields.get("llm_enabled", "").lower() in {"1", "true", "yes", "on"}
    provider = fields.get("llm_provider", "none").strip() or "none"
    base_url = fields.get("llm_base_url", "").strip()
    model = fields.get("llm_model", "").strip()
    api_key = fields.get("llm_api_key", "").strip()
    if provider == "ollama" and not base_url:
        base_url = "http://127.0.0.1:11434/v1/chat/completions"
    return LLMConfig(
        enabled=enabled,
        provider=provider,
        base_url=base_url,
        model=model,
        api_key=api_key,
    )


def _normalize_llm_endpoint(config: LLMConfig) -> str:
    endpoint = config.base_url.strip().rstrip("/")
    if not endpoint:
        raise ValueError("请填写 LLM Base URL。")
    if endpoint.endswith("/chat/completions"):
        return endpoint
    if endpoint.endswith("/completions"):
        return endpoint
    if re.search(r"/(?:v1|v\d+)$", endpoint):
        return endpoint + "/chat/completions"
    return endpoint


def _clamp_score(value: object) -> int | str:
    if value == "":
        return ""
    try:
        return max(0, min(100, int(float(str(value)))))
    except ValueError:
        return ""


def _safe_file_name(name: str) -> str:
    candidate = Path(name).name.strip() or "resume.txt"
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", candidate)


if __name__ == "__main__":
    raise SystemExit(main())
