import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select

from server.app.identity.models import AuditLog, Job, User
from server.app.identity.policy import Principal
from server.app.queue.models import BackgroundJob
from server.app.recruiting.authorization import RecruitingAction, RecruitingAuthorizationService
from server.app.recruiting.models import Application, ApplicationStageEvent, Candidate
from server.app.screening.models import ScreeningItem, ScreeningResult, ScreeningRun
from server.app.interviews.models import Interview, InterviewFeedback, InterviewParticipant
from server.app.reports.csv_export import render_application_csv
from server.app.reports.models import ExportDownloadTicket, ExportRecord


AUTHORIZATION = RecruitingAuthorizationService()
PASS_RECOMMENDATIONS = {"优先沟通", "可沟通"}


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def authorized_job_ids(db, principal: Principal, job_id: uuid.UUID | None = None) -> list[uuid.UUID]:
    query = select(Job.id).where(
        Job.organization_id == principal.organization_id,
        AUTHORIZATION.job_predicate(principal, RecruitingAction.READ, Job),
    )
    if job_id is not None:
        query = query.where(Job.id == job_id)
    return list(db.scalars(query.order_by(Job.id)))


def _date_scope(column, from_: datetime | None, to: datetime | None):
    predicates = []
    if from_ is not None:
        predicates.append(column >= from_)
    if to is not None:
        predicates.append(column <= to)
    return predicates


def recruiting_funnel(db, principal: Principal, job_ids: list[uuid.UUID], from_: datetime | None, to: datetime | None, now: datetime) -> dict:
    applications = list(
        db.scalars(
            select(Application)
            .where(
                Application.organization_id == principal.organization_id,
                Application.job_id.in_(job_ids),
                *_date_scope(Application.created_at, from_, to),
            )
            .order_by(Application.created_at, Application.id)
        )
    ) if job_ids else []
    application_ids = [item.id for item in applications]
    events = list(
        db.scalars(
            select(ApplicationStageEvent)
            .where(
                ApplicationStageEvent.organization_id == principal.organization_id,
                ApplicationStageEvent.application_id.in_(application_ids),
            )
            .order_by(ApplicationStageEvent.application_id, ApplicationStageEvent.created_at, ApplicationStageEvent.id)
        )
    ) if application_ids else []
    by_application: dict[uuid.UUID, list[ApplicationStageEvent]] = {}
    for event in events:
        by_application.setdefault(event.application_id, []).append(event)

    current_counts: dict[str, int] = {}
    durations: dict[str, list[float]] = {}
    for application in applications:
        current_counts[application.stage] = current_counts.get(application.stage, 0) + 1
        history = by_application.get(application.id, [])
        current_stage = "new" if history else application.stage
        entered_at = _aware(application.created_at)
        for event in history:
            event_at = _aware(event.created_at)
            from_stage = event.payload.get("from_stage")
            to_stage = event.payload.get("to_stage")
            if isinstance(from_stage, str) and isinstance(to_stage, str):
                durations.setdefault(from_stage, []).append(max(0.0, (event_at - entered_at).total_seconds()))
                current_stage = to_stage
                entered_at = event_at
        durations.setdefault(current_stage, []).append(max(0.0, (_aware(now) - entered_at).total_seconds()))

    stage_names = list(set(current_counts) | set(durations))
    canonical = ["new", "review", "contact", "interview_pending", "interviewing", "decision", "passed", "hired", "rejected", "withdrawn"]
    stage_names.sort(key=lambda value: canonical.index(value) if value in canonical else len(canonical))
    stages = [
        {
            "stage": stage,
            "current_count": current_counts.get(stage, 0),
            "average_time_in_stage_seconds": round(sum(durations.get(stage, [])) / len(durations[stage]), 6) if durations.get(stage) else 0.0,
        }
        for stage in stage_names
    ]
    return {
        "total_applications": len(applications),
        "stages": stages,
        "interviews": interview_metrics(db, principal, application_ids, from_, to),
    }


def interview_metrics(db, principal: Principal, application_ids: list[uuid.UUID], from_: datetime | None, to: datetime | None) -> dict:
    interviews = list(
        db.scalars(
            select(Interview).where(
                Interview.organization_id == principal.organization_id,
                Interview.application_id.in_(application_ids),
                *_date_scope(Interview.starts_at, from_, to),
            )
        )
    ) if application_ids else []
    interview_ids = [item.id for item in interviews]
    required = list(
        db.scalars(
            select(InterviewParticipant).where(
                InterviewParticipant.organization_id == principal.organization_id,
                InterviewParticipant.interview_id.in_(interview_ids),
                InterviewParticipant.required_feedback.is_(True),
            )
        )
    ) if interview_ids else []
    feedbacks = list(
        db.scalars(
            select(InterviewFeedback).where(
                InterviewFeedback.organization_id == principal.organization_id,
                InterviewFeedback.interview_id.in_(interview_ids),
                InterviewFeedback.status.in_(("submitted", "amended")),
            )
        )
    ) if interview_ids else []
    submitted = {(item.interview_id, item.author_id): item for item in feedbacks}
    completed = [participant for participant in required if (participant.interview_id, participant.user_id) in submitted]
    interviews_by_id = {item.id: item for item in interviews}
    turnaround = [
        max(
            0.0,
            (
                _aware(submitted[(participant.interview_id, participant.user_id)].submitted_at)
                - _aware(interviews_by_id[participant.interview_id].ends_at)
            ).total_seconds(),
        )
        for participant in completed
    ]
    return {
        "count": len(interviews),
        "required_feedback_completed": len(completed),
        "required_feedback_total": len(required),
        "required_feedback_completion_rate": _rate(len(completed), len(required)),
        "average_feedback_turnaround_seconds": round(sum(turnaround) / len(turnaround), 6) if turnaround else 0.0,
    }


def screening_quality(db, principal: Principal, job_ids: list[uuid.UUID], from_: datetime | None, to: datetime | None) -> dict:
    items = list(
        db.scalars(
            select(ScreeningItem)
            .join(
                ScreeningRun,
                and_(
                    ScreeningRun.organization_id == ScreeningItem.organization_id,
                    ScreeningRun.id == ScreeningItem.run_id,
                ),
            )
            .where(
                ScreeningItem.organization_id == principal.organization_id,
                ScreeningRun.job_id.in_(job_ids),
                *_date_scope(ScreeningRun.created_at, from_, to),
            )
        )
    ) if job_ids else []
    item_ids = [item.id for item in items]
    results = list(
        db.scalars(
            select(ScreeningResult).where(
                ScreeningResult.organization_id == principal.organization_id,
                ScreeningResult.item_id.in_(item_ids),
            )
        )
    ) if item_ids else []
    parser_succeeded = sum(item.status in {"parsed", "scoring", "scored"} for item in items)
    llm_terminal = [item for item in items if item.llm_status in {"succeeded", "failed"}]
    llm_succeeded = sum(item.llm_status == "succeeded" for item in llm_terminal)
    rule_passed = sum(item.recommendation in PASS_RECOMMENDATIONS for item in results)
    return {
        "resume_parsing": {
            "succeeded": parser_succeeded,
            "total": len(items),
            "success_rate": _rate(parser_succeeded, len(items)),
        },
        "rule_screening": {
            "passed": rule_passed,
            "total": len(results),
            "pass_rate": _rate(rule_passed, len(results)),
        },
        "llm": {
            "succeeded": llm_succeeded,
            "total": len(llm_terminal),
            "success_rate": _rate(llm_succeeded, len(llm_terminal)),
        },
    }


def create_export_record(db, principal: Principal, job_ids: list[uuid.UUID], from_: datetime | None, to: datetime | None, trace_id: str, idempotency_key: str) -> ExportRecord:
    export_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    background = BackgroundJob(
        id=uuid.uuid4(),
        organization_id=principal.organization_id,
        type="reports.export",
        payload={"organization_id": str(principal.organization_id), "export_id": str(export_id)},
        status="queued",
        priority=0,
        attempts=0,
        max_attempts=3,
        run_after=now,
        dedupe_key=hashlib.sha256(f"{principal.user_id}:{idempotency_key}".encode()).hexdigest(),
        trace_id=trace_id,
        created_at=now,
        updated_at=now,
    )
    export = ExportRecord(
        id=export_id,
        organization_id=principal.organization_id,
        requested_by=principal.user_id,
        background_job_id=background.id,
        filters={
            "job_ids": [str(item) for item in job_ids],
            "from": from_.isoformat() if from_ else None,
            "to": to.isoformat() if to else None,
        },
        created_at=now,
        updated_at=now,
    )
    db.add_all([background, export])
    db.flush()
    db.add(
        AuditLog(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            event_type="report_export.created",
            outcome="success",
            trace_id=trace_id,
            metadata_json={"export_id": str(export.id), "job_count": len(job_ids)},
        )
    )
    db.flush()
    return export


def _principal_for_export(db, export: ExportRecord) -> Principal | None:
    user = db.get(User, export.requested_by)
    if user is None or getattr(user.status, "value", user.status) != "active":
        return None
    return Principal(
        user_id=user.id,
        organization_id=user.organization_id,
        roles=frozenset(role.role for role in user.roles),
        active=True,
    )


def generate_export(db, export_id: uuid.UUID, storage) -> ExportRecord:
    export = db.scalar(select(ExportRecord).where(ExportRecord.id == export_id).with_for_update())
    if export is None:
        raise LookupError("export unavailable")
    principal = _principal_for_export(db, export)
    requested_job_ids = [uuid.UUID(item) for item in export.filters.get("job_ids", [])]
    if principal is None:
        raise PermissionError("export requester unavailable")
    currently_authorized = authorized_job_ids(db, principal)
    allowed = set(requested_job_ids) & set(currently_authorized)
    from_ = datetime.fromisoformat(export.filters["from"]) if export.filters.get("from") else None
    to = datetime.fromisoformat(export.filters["to"]) if export.filters.get("to") else None
    rows = db.execute(
        select(Application, Candidate)
        .join(
            Candidate,
            and_(Candidate.organization_id == Application.organization_id, Candidate.id == Application.candidate_id),
        )
        .join(Job, and_(Job.organization_id == Application.organization_id, Job.id == Application.job_id))
        .where(
            Application.organization_id == export.organization_id,
            Application.job_id.in_(allowed),
            AUTHORIZATION.job_predicate(principal, RecruitingAction.READ, Job),
            *_date_scope(Application.created_at, from_, to),
        )
        .order_by(Application.created_at, Application.id)
    ).all() if allowed else []
    content = render_application_csv(
        [
            {
                "application_id": application.id,
                "job_id": application.job_id,
                "candidate_id": application.candidate_id,
                "candidate_name": candidate.display_name,
                "stage": application.stage,
                "source": application.source,
                "created_at": _aware(application.created_at).isoformat(),
            }
            for application, candidate in rows
        ]
    )
    object_key = f"exports/{export.organization_id}/{export.id}.csv"
    storage.write(object_key, content, "text/csv; charset=utf-8")
    export.object_key = object_key
    export.row_count = len(rows)
    export.status = "succeeded"
    export.completed_at = datetime.now(timezone.utc)
    export.updated_at = export.completed_at
    db.flush()
    return export


def issue_export_ticket(db, export: ExportRecord, principal: Principal, clock, tokens) -> str:
    raw = tokens.new_token()
    db.add(
        ExportDownloadTicket(
            organization_id=principal.organization_id,
            export_id=export.id,
            user_id=principal.user_id,
            token_hash=hashlib.sha256(raw.encode()).hexdigest(),
            expires_at=clock.current_time() + timedelta(seconds=60),
        )
    )
    db.flush()
    return raw


def consume_export_ticket(db, raw: str, principal: Principal, export: ExportRecord, clock) -> ExportDownloadTicket:
    ticket = db.scalar(
        select(ExportDownloadTicket)
        .where(ExportDownloadTicket.token_hash == hashlib.sha256(raw.encode()).hexdigest())
        .with_for_update()
    )
    if (
        ticket is None
        or ticket.consumed_at is not None
        or _aware(ticket.expires_at) <= clock.current_time()
        or ticket.organization_id != principal.organization_id
        or ticket.user_id != principal.user_id
        or ticket.export_id != export.id
    ):
        raise LookupError("ticket unavailable")
    ticket.consumed_at = clock.current_time()
    db.flush()
    return ticket
