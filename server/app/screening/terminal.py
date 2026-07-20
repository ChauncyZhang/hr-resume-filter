import uuid
from dataclasses import dataclass

from sqlalchemy import select

from server.app.llm.models import LlmProviderConfig, PromptVersion
from server.app.queue.service import normalize_safe_code
from server.app.recruiting.models import Application, Candidate, JobJdVersion, Resume
from server.app.recruiting.tasks import normalize_llm_terminal_safe_error_code
from server.app.screening.models import ScreeningItem, ScreeningResult, ScreeningRun
from server.app.screening.progress import aggregate_run
from server.app.screening.routing import route_llm_screening_terminal


_LLM_PAYLOAD_FIELDS = (
    "organization_id",
    "screening_item_id",
    "screening_result_id",
    "application_id",
    "config_id",
    "prompt_version_id",
)
_LLM_WORKER_EXHAUSTION_CODES = {
    "handler_failed": "llm_handler_failed",
    "lease_expired": "llm_handler_failed",
    "llm_handler_failed": "llm_handler_failed",
}


@dataclass(frozen=True)
class _LlmDeadLetterContext:
    item: ScreeningItem | None
    run: ScreeningRun | None
    technical_code: str | None = None
    already_terminal: bool = False


def _uuid_value(value):
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _llm_payload(job):
    organization_id = _uuid_value(getattr(job, "organization_id", None))
    payload = job.payload if isinstance(getattr(job, "payload", None), dict) else {}
    values = {name: _uuid_value(payload.get(name)) for name in _LLM_PAYLOAD_FIELDS}
    raw_version = payload.get("config_version")
    try:
        config_version = None if isinstance(raw_version, bool) else int(raw_version)
    except (TypeError, ValueError):
        config_version = None
    return organization_id, values, config_version


def _tenant_record(session, model, organization_id, record_id, *criteria, lock=False):
    if record_id is None:
        return None
    statement = select(model).where(
        model.organization_id == organization_id,
        model.id == record_id,
        *criteria,
    )
    if lock:
        statement = statement.with_for_update()
    return session.scalar(statement)


def _llm_dead_letter_context(session, job):
    organization_id, values, config_version = _llm_payload(job)
    item_id = values["screening_item_id"]
    if organization_id is None or item_id is None:
        return _LlmDeadLetterContext(None, None, "llm_job_payload_invalid")

    identity = session.execute(
        select(ScreeningItem.candidate_id).where(
            ScreeningItem.organization_id == organization_id,
            ScreeningItem.id == item_id,
        )
    ).one_or_none()
    if identity is None:
        return _LlmDeadLetterContext(None, None, "llm_job_payload_invalid")

    candidate = None
    if identity.candidate_id is not None:
        candidate = _tenant_record(
            session, Candidate, organization_id, identity.candidate_id, lock=True
        )
    item = _tenant_record(
        session, ScreeningItem, organization_id, item_id, lock=True
    )
    if item is None:
        return _LlmDeadLetterContext(None, None, "llm_job_payload_invalid")
    if item.llm_status in {"succeeded", "failed", "skipped"}:
        return _LlmDeadLetterContext(item, None, already_terminal=True)

    application = None
    if item.application_id is not None:
        application = _tenant_record(
            session, Application, organization_id, item.application_id, lock=True
        )
    run = _tenant_record(
        session, ScreeningRun, organization_id, item.run_id, lock=True
    )

    payload_invalid = (
        any(values[name] is None for name in _LLM_PAYLOAD_FIELDS)
        or values["organization_id"] != organization_id
        or config_version is None
        or config_version < 1
    )
    if payload_invalid:
        return _LlmDeadLetterContext(item, run, "llm_job_payload_invalid")
    if candidate is None or candidate.deleted_at is not None or application is None:
        return _LlmDeadLetterContext(item, run, "internal_error")
    if item.status != "scored":
        return _LlmDeadLetterContext(item, run, "llm_job_payload_invalid")
    if (
        values["application_id"] != item.application_id
        or application.candidate_id != item.candidate_id
        or application.resume_id != item.resume_id
        or run is None
        or application.job_id != run.job_id
    ):
        return _LlmDeadLetterContext(item, run, "llm_job_payload_invalid")

    result = _tenant_record(
        session,
        ScreeningResult,
        organization_id,
        values["screening_result_id"],
        ScreeningResult.item_id == item.id,
    )
    resume = _tenant_record(
        session,
        Resume,
        organization_id,
        item.resume_id,
        Resume.candidate_id == candidate.id,
        Resume.file_object_id == item.file_object_id,
    )
    jd = _tenant_record(
        session,
        JobJdVersion,
        organization_id,
        run.jd_version_id,
        JobJdVersion.job_id == run.job_id,
    )
    prompt = _tenant_record(
        session,
        PromptVersion,
        organization_id,
        values["prompt_version_id"],
        PromptVersion.name == "screening-evaluation",
    )
    config = _tenant_record(
        session,
        LlmProviderConfig,
        organization_id,
        values["config_id"],
        lock=True,
    )
    if any(value is None for value in (result, resume, jd, prompt, config)):
        return _LlmDeadLetterContext(item, run, "llm_job_payload_invalid")
    if (
        result.application_id != application.id
        or result.resume_id != resume.id
        or config.version != config_version
    ):
        return _LlmDeadLetterContext(item, run, "llm_job_payload_invalid")
    return _LlmDeadLetterContext(item, run)


def _finish_llm_technical_failure(session, context, now):
    item = context.item
    if item is None or context.already_terminal:
        return
    code = normalize_llm_terminal_safe_error_code(context.technical_code)
    if item.status == "scored":
        item.llm_status = "failed"
        item.llm_safe_error_code = code
        item.llm_finished_at = item.llm_finished_at or now
    else:
        item.status = "failed"
        item.safe_error_code = code
    item.finished_at = item.finished_at or now
    if context.run is not None:
        aggregate_run(session, context.run)


def _llm_dead_letter_safe_code(value):
    normalized = normalize_safe_code(value)
    if normalized in _LLM_WORKER_EXHAUSTION_CODES:
        return _LLM_WORKER_EXHAUSTION_CODES[normalized]
    if normalized.startswith(("provider_", "llm_provider_")):
        safe_code = normalize_llm_terminal_safe_error_code(normalized)
        return safe_code if safe_code != "internal_error" else None
    return None


def finalize_screening_dead_letter(session, job, safe_code, now):
    item_id = _uuid_value(getattr(job, "payload", {}).get("screening_item_id"))
    if item_id is None:
        return
    item = _tenant_record(
        session, ScreeningItem, job.organization_id, item_id, lock=True
    )
    if item is None or item.status in {"scored", "cancelled"}:
        return
    item.status = "failed"
    item.safe_error_code = normalize_safe_code(safe_code)
    item.finished_at = item.finished_at or now
    run = _tenant_record(
        session, ScreeningRun, job.organization_id, item.run_id, lock=True
    )
    aggregate_run(session, run)


def finalize_llm_dead_letter(session, job, safe_code, now):
    context = _llm_dead_letter_context(session, job)
    if context.item is None or context.already_terminal:
        return
    if context.technical_code is not None:
        _finish_llm_technical_failure(session, context, now)
        return

    terminal_code = _llm_dead_letter_safe_code(safe_code)
    if terminal_code is None:
        _finish_llm_technical_failure(
            session,
            _LlmDeadLetterContext(context.item, context.run, "internal_error"),
            now,
        )
        return
    route_llm_screening_terminal(
        session,
        organization_id=job.organization_id,
        item_id=context.item.id,
        actor_user_id=context.run.created_by,
        score=None,
        ai_status="failed",
        safe_error_code=terminal_code,
        trace_id=getattr(job, "trace_id", None) or f"llm-dead:{job.id}",
    )
    context.item.llm_status = "failed"
    context.item.llm_safe_error_code = terminal_code
    context.item.llm_finished_at = context.item.llm_finished_at or now
    context.item.finished_at = context.item.finished_at or now
    aggregate_run(session, context.run)


def screening_terminal_callbacks():
    return {
        "screening.parse_item": finalize_screening_dead_letter,
        "screening.score_item": finalize_screening_dead_letter,
        "screening.llm_score_item": finalize_llm_dead_letter,
    }
