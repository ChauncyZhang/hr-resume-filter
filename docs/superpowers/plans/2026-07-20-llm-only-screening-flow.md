# LLM-Only Screening Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace rule-driven HR review with LLM-only multidimensional scoring that automatically routes candidates to hiring-manager review or a deferred talent pool and fails open when the model is unavailable.

**Architecture:** Keep legacy rule results for historical compatibility and as the existing foreign-key anchor, but remove them from Prompt inputs, new UI decisions, and stage routing. A single transactional routing service owns the terminal LLM side effects: evaluation/failure evidence, application stage event, audit, durable review task, or idempotent talent-pool membership.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL, Pydantic 2, React 19, Vite 6, Node test runner, pytest, Playwright

## Global Constraints

- LLM is the only scoring source for new screening tasks; rule score and rule missing facts cannot influence final score, recommendation, or stage.
- Scores `85-100` produce `优先评审`; `60-84` produce `建议评审`; `0-59` produce `暂缓`.
- A score of `60` enters `review`; a score of `59` enters `deferred`.
- Final LLM failure enters `review` with a null score and `AI评分不可用`; it never creates an HR manual-review task.
- Parser, malware, unsupported-format, missing-file, and candidate-creation failures remain technical failures and do not fail open.
- New flow must not produce `待HR审核`, `HR已审核`, `需人工复核`, or `待提交用人经理`.
- Historical rule results and Prompt v1 records remain readable and are not rewritten.
- Resume/JD bodies, Provider responses, API keys, prompts, and candidate PII must not enter logs, audit metadata, metrics, or frontend errors.
- Implement and verify `docs/superpowers/plans/2026-07-20-shared-nginx-release-protection.md` before any production deployment.

---

### Task 1: Add Deferred Stage, Dimension Storage, Durable Review Tasks, And System Pool Identity

**Files:**
- Create: `server/migrations/versions/0021_llm_only_auto_routing.py`
- Modify: `server/app/recruiting/models.py`
- Modify: `server/app/llm/models.py`
- Modify: `server/app/talent/models.py`
- Modify: `server/migrations/env.py`
- Modify: `server/tests/test_migrations.py`
- Modify: `server/tests/test_llm_postgres.py`
- Modify: `server/tests/test_talent_migration.py`

**Interfaces:**
- Produces: `ApplicationReviewTask`, `Application.stage == "deferred"`, `LlmScreeningEvaluation.dimensions`, and `TalentPool.system_key`.
- Consumed by: Tasks 3-7.

- [ ] **Step 1: Write failing model and migration tests**

```python
def test_llm_only_routing_migration_is_latest_revision():
    assert script_directory.get_current_head() == "0021_llm_only_auto_routing"


def test_application_review_task_has_one_active_task_per_application(session, organization, application, user):
    session.add(ApplicationReviewTask(
        organization_id=organization.id,
        application_id=application.id,
        assignee_id=user.id,
        status="open",
        ai_status="succeeded",
    ))
    session.commit()
    session.add(ApplicationReviewTask(
        organization_id=organization.id,
        application_id=application.id,
        assignee_id=user.id,
        status="open",
        ai_status="failed",
    ))
    with pytest.raises(IntegrityError):
        session.commit()
```

Also assert `deferred` satisfies `ck_applications_stage`, evaluation dimensions persist as JSON, and one organization cannot create two pools with `system_key="ai_screening_deferred"`.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```powershell
python -m pytest server/tests/test_migrations.py server/tests/test_llm_postgres.py server/tests/test_talent_migration.py -q
```

Expected: failures mention missing revision, missing `ApplicationReviewTask`, missing `dimensions`, and missing `system_key`.

- [ ] **Step 3: Add exact ORM fields and constraints**

```python
class ApplicationReviewTask(Record, Base):
    __tablename__ = "application_review_tasks"
    application_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    assignee_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="open")
    ai_status: Mapped[str] = mapped_column(String(16))
    safe_error_code: Mapped[str | None] = mapped_column(String(64))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

Use a PostgreSQL and SQLite partial unique index on `(organization_id, application_id)` where `status = 'open'`. Constrain task status to `open|closed|cancelled` and AI status to `succeeded|failed`.

Add `dimensions: Mapped[list] = mapped_column(JSON_DOCUMENT, default=list)` to `LlmScreeningEvaluation`, and `system_key: Mapped[str | None]` to `TalentPool` with an organization-scoped partial unique index for non-null keys.

- [ ] **Step 4: Implement forward-only migration `0021`**

The upgrade must:

```python
op.drop_constraint("ck_applications_stage", "applications", type_="check")
op.create_check_constraint(
    "ck_applications_stage",
    "applications",
    "stage in ('new','review','deferred','contact','interview_pending','interviewing','decision','passed','hired','rejected','withdrawn')",
)
op.add_column("llm_screening_evaluations", sa.Column("dimensions", postgresql.JSONB(), nullable=True))
op.execute("UPDATE llm_screening_evaluations SET dimensions = '[]'::jsonb WHERE dimensions IS NULL")
op.alter_column("llm_screening_evaluations", "dimensions", nullable=False)
```

Create the review-task table and pool system-key index without changing historical application stages, rule results, or Prompt rows. Downgrade drops only the new rows/columns and restores the old check constraint; downgrade must fail clearly if a `deferred` application still exists.

- [ ] **Step 5: Run model and migration tests**

Run:

```powershell
python -m pytest server/tests/test_migrations.py server/tests/test_llm_postgres.py server/tests/test_talent_migration.py -q
```

Expected: all focused tests pass.

- [ ] **Step 6: Commit persistence changes**

```powershell
git add server/migrations/versions/0021_llm_only_auto_routing.py server/migrations/env.py server/app/recruiting/models.py server/app/llm/models.py server/app/talent/models.py server/tests/test_migrations.py server/tests/test_llm_postgres.py server/tests/test_talent_migration.py
git commit -m "feat: persist LLM screening routes"
```

---

### Task 2: Introduce Prompt V2 And A Strict Multidimensional Score Contract

**Files:**
- Modify: `server/app/llm/screening.py`
- Modify: `server/app/llm/gateway.py`
- Modify: `server/app/screening/llm_pipeline.py`
- Modify: `server/app/screening/pipeline.py`
- Modify: `server/app/screening/schemas.py`
- Modify: `server/tests/test_llm_screening_contract.py`
- Modify: `server/tests/test_llm_gateway.py`
- Modify: `server/tests/test_llm_pipeline.py`
- Modify: `server/tests/test_screening_pipeline.py`

**Interfaces:**
- Produces: `DimensionScore`, Prompt version `2`, `ScreeningResult.dimensions`, and `OpenAiCompatibleGateway.evaluate(..., system_prompt: str)`.
- Consumed by: Tasks 3, 4, 6, and 7.

- [ ] **Step 1: Write failing contract tests for all five dimensions**

```python
def test_screening_result_requires_dimension_total_to_equal_score():
    with pytest.raises(ValidationError):
        ScreeningResult.model_validate({
            "score": 60,
            "dimensions": [
                {"key": "core_capability", "score": 35, "evidence": ["Python"], "gaps": []},
                {"key": "experience_depth", "score": 24, "evidence": ["RAG"], "gaps": []},
                {"key": "role_seniority", "score": 0, "evidence": [], "gaps": []},
                {"key": "transferability", "score": 0, "evidence": [], "gaps": []},
                {"key": "explicit_constraints", "score": 0, "evidence": [], "gaps": []},
            ],
            "summary": "匹配",
            "strengths": [], "gaps": [], "risks": [], "questions": [],
        })
```

Add tests that reject a missing key, duplicate key, score above the dimension maximum, model-supplied `recommendation`, and any request containing `rule_facts`.

- [ ] **Step 2: Run the contract tests and verify RED**

Run:

```powershell
python -m pytest server/tests/test_llm_screening_contract.py server/tests/test_llm_gateway.py -q
```

Expected: tests fail because the v1 contract still accepts recommendation and rule facts.

- [ ] **Step 3: Define the v2 schema and score validator**

```python
DIMENSION_LIMITS = {
    "core_capability": 35,
    "experience_depth": 25,
    "role_seniority": 20,
    "transferability": 10,
    "explicit_constraints": 10,
}

class DimensionScore(ContractModel):
    key: Literal[
        "core_capability", "experience_depth", "role_seniority",
        "transferability", "explicit_constraints",
    ]
    score: int = Field(ge=0)
    evidence: list[str] = Field(max_length=8)
    gaps: list[str] = Field(max_length=8)

class ScreeningRequest(ContractModel):
    job_description: str
    resume_text: str

class ScreeningResult(ContractModel):
    score: int = Field(ge=0, le=100)
    dimensions: list[DimensionScore] = Field(min_length=5, max_length=5)
    summary: str
    strengths: list[str]
    gaps: list[str]
    risks: list[str]
    questions: list[str]
```

Use an `after` model validator to require exactly the five keys, enforce each key's maximum, and require `sum(dimension.score) == score`.

- [ ] **Step 4: Make PromptVersion control the actual gateway prompt**

Change gateway invocation to:

```python
await gateway.evaluate(
    provider_id,
    model,
    api_key,
    request,
    organization_id=organization_id,
    system_prompt=prompt.content["system"],
)
```

Increment `_PROMPT_VERSION` to `2`, set schema version to `screening-evaluation-v2`, describe the exact dimension limits, and instruct the model to return no recommendation. New jobs bind v2; historical v1 invocations remain readable.

- [ ] **Step 5: Expose dimensions without exposing prompt or provider response**

Update `LlmEvaluationOut` to include:

```python
class LlmDimensionOut(ApiModel):
    key: str
    score: int
    evidence: list[str]
    gaps: list[str]
```

Keep `recommendation` in the API as a server-derived display value added in Task 3.

- [ ] **Step 6: Run focused v2 tests**

Run:

```powershell
python -m pytest server/tests/test_llm_screening_contract.py server/tests/test_llm_gateway.py server/tests/test_llm_pipeline.py server/tests/test_screening_pipeline.py -q
```

Expected: all tests pass; request-body assertions show JD and redacted resume only.

- [ ] **Step 7: Commit Prompt v2 and the contract**

```powershell
git add server/app/llm/screening.py server/app/llm/gateway.py server/app/screening/llm_pipeline.py server/app/screening/pipeline.py server/app/screening/schemas.py server/tests/test_llm_screening_contract.py server/tests/test_llm_gateway.py server/tests/test_llm_pipeline.py server/tests/test_screening_pipeline.py
git commit -m "feat: add multidimensional LLM screening contract"
```

---

### Task 3: Build Transactional Routing, Review Task, And Deferred Talent Services

**Files:**
- Create: `server/app/screening/routing.py`
- Create: `server/app/recruiting/tasks.py`
- Create: `server/app/talent/service.py`
- Modify: `server/app/governance/audit.py`
- Modify: `server/app/recruiting/service.py`
- Create: `server/tests/test_screening_routing.py`
- Create: `server/tests/test_recruiting_tasks.py`
- Create: `server/tests/test_talent_service.py`
- Modify: `server/tests/test_governance_audit.py`

**Interfaces:**
- Produces: `derive_screening_outcome(score)`, `route_llm_screening_terminal(...)`, `ensure_review_task(...)`, `close_review_task(...)`, and `ensure_deferred_membership(...)`.
- Consumed by: Tasks 4 and 5.

- [ ] **Step 1: Write failing route-boundary tests**

```python
@pytest.mark.parametrize(
    ("score", "recommendation", "stage"),
    [(85, "优先评审", "review"), (60, "建议评审", "review"), (59, "暂缓", "deferred"), (0, "暂缓", "deferred")],
)
def test_derive_screening_outcome(score, recommendation, stage):
    assert derive_screening_outcome(score) == ScreeningOutcome(recommendation, stage)


def test_final_llm_failure_fails_open_without_fake_score(session, screening_item):
    result = route_llm_screening_terminal(
        session,
        organization_id=screening_item.organization_id,
        item_id=screening_item.id,
        actor_user_id=screening_item.run.created_by,
        score=None,
        ai_status="failed",
        safe_error_code="provider_quota_or_rate_limited",
        trace_id="trace-safe",
    )
    assert result.stage == "review"
    assert result.score is None
    assert result.recommendation == "AI评分不可用"
```

Assert repeated routing returns the same outcome without a duplicate stage event, review task, talent membership, or audit event.

- [ ] **Step 2: Run new domain tests and verify RED**

Run:

```powershell
python -m pytest server/tests/test_screening_routing.py server/tests/test_recruiting_tasks.py server/tests/test_talent_service.py -q
```

Expected: collection fails because the three service modules do not exist.

- [ ] **Step 3: Implement server-derived outcome rules**

```python
@dataclass(frozen=True)
class ScreeningOutcome:
    recommendation: str
    stage: Literal["review", "deferred"]


def derive_screening_outcome(score: int) -> ScreeningOutcome:
    if not 0 <= score <= 100:
        raise ValueError("score_out_of_range")
    if score >= 85:
        return ScreeningOutcome("优先评审", "review")
    if score >= 60:
        return ScreeningOutcome("建议评审", "review")
    return ScreeningOutcome("暂缓", "deferred")
```

- [ ] **Step 4: Implement idempotent review-task creation and closure**

```python
def ensure_review_task(db, *, application, job, ai_status, safe_error_code=None):
    assignee_id = job.hiring_owner_id or job.owner_id
    existing = db.scalar(select(ApplicationReviewTask).where(
        ApplicationReviewTask.organization_id == application.organization_id,
        ApplicationReviewTask.application_id == application.id,
        ApplicationReviewTask.status == "open",
    ).with_for_update())
    if existing:
        return existing
    task = ApplicationReviewTask(
        organization_id=application.organization_id,
        application_id=application.id,
        assignee_id=assignee_id,
        status="open",
        ai_status=ai_status,
        safe_error_code=safe_error_code,
    )
    db.add(task)
    return task
```

`close_review_task` must close only an open task for the same tenant/application and preserve its assignee and AI status as history.

- [ ] **Step 5: Implement system pool and membership upsert**

`ensure_deferred_membership` must select/create one recruiting-team pool with `system_key="ai_screening_deferred"`; select a recruiting administrator as pool owner or fall back to the run creator; and upsert membership with:

```python
reason = "LLM 初筛分低于 60"
tags = [job.title, f"LLM {score}分", *transferable_capabilities[:5]]
source_application_id = application.id
owner_id = run.created_by
```

Use the organization retention policy already used by talent membership creation. Do not create a second membership when the candidate already belongs to the system pool.

- [ ] **Step 6: Implement one transactional terminal router**

`route_llm_screening_terminal` must lock Candidate, ScreeningItem, and Application in existing lock order; no-op when the application has left `new`; update stage/version; append `ApplicationStageEvent` and safe `AuditLog`; then call exactly one of `ensure_review_task` or `ensure_deferred_membership`. It must not commit internally so the caller controls one transaction.

- [ ] **Step 7: Close review tasks from existing manager workflow actions**

Update `apply_application_workflow_action_record()` so both manager approval and rejection call `close_review_task` in the same transaction that changes application stage.

- [ ] **Step 8: Run domain service tests**

Run:

```powershell
python -m pytest server/tests/test_screening_routing.py server/tests/test_recruiting_tasks.py server/tests/test_talent_service.py server/tests/test_application_workflow_actions.py -q
```

Expected: all tests pass, including idempotency and concurrent stale-version cases.

- [ ] **Step 9: Commit domain routing services**

```powershell
git add server/app/screening/routing.py server/app/recruiting/tasks.py server/app/talent/service.py server/app/recruiting/service.py server/tests/test_screening_routing.py server/tests/test_recruiting_tasks.py server/tests/test_talent_service.py server/tests/test_application_workflow_actions.py
git commit -m "feat: route LLM screening outcomes automatically"
```

---

### Task 4: Integrate Success, Retry Exhaustion, Skip, And Dead Letter With The Router

**Files:**
- Modify: `server/app/screening/llm_pipeline.py`
- Modify: `server/app/screening/terminal.py`
- Modify: `server/app/screening/progress.py`
- Modify: `server/app/screening/pipeline.py`
- Modify: `server/app/queue/payloads.py`
- Modify: `server/app/worker/main.py`
- Modify: `server/tests/test_llm_pipeline.py`
- Modify: `server/tests/test_screening_dead_letter_postgres.py`
- Modify: `server/tests/test_screening_progress.py`
- Modify: `server/tests/test_screening_worker.py`

**Interfaces:**
- Consumes: Task 2 Prompt result and Task 3 `route_llm_screening_terminal`.
- Produces: every terminal LLM path routes exactly once; `aggregate_run()` only aggregates.

- [ ] **Step 1: Write failing pipeline tests for four terminal paths**

```python
@pytest.mark.parametrize("safe_code", [
    "provider_unavailable",
    "provider_quota_or_rate_limited",
    "provider_response_invalid",
    "llm_config_disabled",
])
def test_final_llm_failure_routes_to_review_with_null_score(safe_code, pipeline_fixture):
    item, application = pipeline_fixture.finish_failure(safe_code, final=True)
    assert item.llm_status == "failed"
    assert application.stage == "review"
    assert pipeline_fixture.evaluation_for(item) is None
    assert pipeline_fixture.open_task_for(application).ai_status == "failed"
```

Add success tests for scores `60` and `59`, retry tests proving no route before final attempt, and dead-letter tests proving fail-open routing.

- [ ] **Step 2: Run focused integration tests and verify RED**

Run:

```powershell
python -m pytest server/tests/test_llm_pipeline.py server/tests/test_screening_dead_letter_postgres.py server/tests/test_screening_progress.py -q
```

Expected: current code stores results/failures but does not route at the LLM terminal boundary.

- [ ] **Step 3: Route successful evaluation in the existing transaction**

After persisting `LlmInvocation` and `LlmScreeningEvaluation`, store `dimensions`, derive recommendation on the server, and call:

```python
route_llm_screening_terminal(
    db,
    organization_id=ids["organization_id"],
    item_id=ids["screening_item_id"],
    actor_user_id=run.created_by,
    score=facts.score,
    ai_status="succeeded",
    safe_error_code=None,
    trace_id=job.trace_id,
)
```

- [ ] **Step 4: Route only final failure and skip outcomes**

`_finish_failure()` must keep the application in `new` while a retry is queued. On the last attempt, configuration skip, or terminal queue callback, call the same router with `score=None` and a normalized safe code. Do not synthesize an evaluation or score.

- [ ] **Step 5: Remove stage mutation from aggregate progress**

Delete the `Application.stage == "new"` bulk transition from `aggregate_run()`. Keep only processed/succeeded/failed counters and review summary queries based on already-persisted application stages.

- [ ] **Step 6: Preserve rule rows without consuming rule facts**

`ScreeningPipeline.score_item()` may continue to write `ScreeningResult` to satisfy existing foreign keys, but the queued LLM payload and `_request()` must not contain `required_hits`, `required_missing`, `bonus_hits`, rule score, or rule recommendation.

- [ ] **Step 7: Run Worker and terminal regression tests**

Run:

```powershell
python -m pytest server/tests/test_llm_pipeline.py server/tests/test_screening_dead_letter_postgres.py server/tests/test_screening_progress.py server/tests/test_screening_worker.py server/tests/test_screening_pipeline.py -q
```

Expected: all terminal paths pass and no test expects aggregate-time stage changes.

- [ ] **Step 8: Commit pipeline integration**

```powershell
git add server/app/screening/llm_pipeline.py server/app/screening/terminal.py server/app/screening/progress.py server/app/screening/pipeline.py server/app/queue/payloads.py server/app/worker/main.py server/tests/test_llm_pipeline.py server/tests/test_screening_dead_letter_postgres.py server/tests/test_screening_progress.py server/tests/test_screening_worker.py
git commit -m "feat: route terminal LLM results in worker transactions"
```

---

### Task 5: Expose LLM Results, Durable Manager Tasks, And Deferred Recovery APIs

**Files:**
- Modify: `server/app/screening/schemas.py`
- Modify: `server/app/screening/api.py`
- Modify: `server/app/recruiting/schemas.py`
- Modify: `server/app/recruiting/api.py`
- Modify: `server/app/talent/schemas.py`
- Modify: `server/app/talent/api.py`
- Modify: `server/tests/test_screening_api.py`
- Modify: `server/tests/test_recruiting_api.py`
- Modify: `server/tests/test_workbench_api.py`
- Modify: `server/tests/test_talent_api.py`
- Modify: `server/tests/test_talent_api_postgres.py`

**Interfaces:**
- Produces: screening item `ai_score`, `ai_recommendation`, and `route_result`; durable workbench review tasks; persisted LLM evidence in candidate detail; LLM score in candidate lists; and deferred membership `POST /talent-pool-memberships/{id}/review-referrals`.
- Consumed by: Tasks 6 and 7.

- [ ] **Step 1: Write failing API contract tests**

```python
def test_screening_item_uses_llm_recommendation_and_dimensions(client, auth, routed_item):
    body = client.get(f"/api/screening/items/{routed_item.id}", headers=auth).json()["data"]
    assert body["route_result"] == "review"
    assert body["ai_score"] == 72
    assert body["ai_recommendation"] == "建议评审"
    assert body["llm_evaluation"]["recommendation"] == "建议评审"
    assert len(body["llm_evaluation"]["dimensions"]) == 5
    assert body["rule_result"] is not None  # historical compatibility only


def test_deferred_membership_referral_reuses_application(client, auth, deferred_membership):
    response = client.post(
        f"/api/talent-pool-memberships/{deferred_membership.id}/review-referrals",
        headers={**auth, "Idempotency-Key": "referral-1", "If-Match": '"1"'},
        json={},
    )
    assert response.status_code == 200
    assert response.json()["data"]["application"]["stage"] == "review"
```

Add tests that manager workbench tasks are filtered by `assignee_id`, AI-failed tasks expose only a safe flag, and candidate min-score filtering uses LLM score rather than rule score.

- [ ] **Step 2: Run focused API tests and verify RED**

Run:

```powershell
python -m pytest server/tests/test_screening_api.py server/tests/test_recruiting_api.py server/tests/test_workbench_api.py server/tests/test_talent_api.py -q
```

Expected: route result, dimensions, durable task source, and referral endpoint are missing.

- [ ] **Step 3: Replace rule-derived API projections with LLM projections**

Join the latest `LlmScreeningEvaluation` by screening result/application. Return:

```json
{
  "route_result": "review",
  "ai_score": 72,
  "ai_recommendation": "建议评审",
  "llm_status": "succeeded",
  "llm_evaluation": {
    "score": 72,
    "recommendation": "建议评审",
    "dimensions": [],
    "summary": "...",
    "strengths": [],
    "gaps": [],
    "risks": [],
    "questions": []
  }
}
```

For final failure, return `ai_score: null`, `ai_recommendation: "AI评分不可用"`, `llm_evaluation: null`, and the existing allowlisted safe error code. Do not manufacture an empty evaluation row. Add the same persisted screening projection to candidate application summaries/details so a browser refresh restores dimensions, evidence, gaps, risks, and questions. Never return Prompt text or Provider bodies.

- [ ] **Step 4: Read manager workbench tasks from `ApplicationReviewTask`**

`get_workbench()` must select only open tasks assigned to the principal, join the application/job/candidate, and expose `task_id`, `ai_status`, `config_warning`, and the candidate link. Keep interview, decision, and passed task groups on their current sources. Remove the response invariant that review-task counts must equal every visible application in the `review` stage; only persisted open tasks count as manager review work.

Add run-summary fields `manager_review_count`, `deferred_count`, `ai_unavailable_count`, and `file_failed_count`. Derive them from item/application terminal state and never from rule recommendations.

- [ ] **Step 5: Add deferred-to-review referral without creating a new application**

Create `ReviewReferralInput` with no client-controlled stage or assignee. The endpoint must lock membership/source application, require `source.stage == "deferred"`, require an open job and valid hiring owner/fallback owner, transition the same application to `review`, create its stage event/audit/open review task, and preserve the membership as source history. Repeated idempotency key returns the same application.

- [ ] **Step 6: Run API and PostgreSQL tests**

Run:

```powershell
python -m pytest server/tests/test_screening_api.py server/tests/test_recruiting_api.py server/tests/test_workbench_api.py server/tests/test_talent_api.py server/tests/test_talent_api_postgres.py -q
```

Expected: all tests pass; tenant isolation and version conflicts remain enforced.

- [ ] **Step 7: Commit public API changes**

```powershell
git add server/app/screening/schemas.py server/app/screening/api.py server/app/recruiting/schemas.py server/app/recruiting/api.py server/app/talent/schemas.py server/app/talent/api.py server/tests/test_screening_api.py server/tests/test_recruiting_api.py server/tests/test_workbench_api.py server/tests/test_talent_api.py server/tests/test_talent_api_postgres.py
git commit -m "feat: expose automatic screening routes"
```

---

### Task 6: Remove HR Manual Review From Screening UI

**Files:**
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/screeningController.js`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/ScreeningViews.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/screeningController.test.js`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/ScreeningViews.test.js`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/product-theme-jobs-screening.css`

**Interfaces:**
- Consumes: Task 5 screening item response.
- Produces: read-only automatic-route result table with dimensions and no bulk HR review controls.

- [ ] **Step 1: Write failing normalization and render tests**

```javascript
test("normalizes server LLM outcome as the only current recommendation", () => {
  const file = normalizeScreeningTask(run, [{
    status: "scored",
    route_result: "review",
    application_stage: "review",
    rule_result: { score: 12, recommendation: "需人工复核" },
    llm_status: "succeeded",
    llm_evaluation: { score: 72, recommendation: "建议评审", dimensions: [] },
  }]).files[0];
  assert.equal(file.score, 72);
  assert.equal(file.recommendation, "建议评审");
  assert.equal(file.routeResult, "review");
});

test("screening task view contains no HR manual review controls", () => {
  const source = readFileSync(new URL("./ScreeningViews.jsx", import.meta.url), "utf8");
  for (const removed of ["待HR审核", "HR初筛进度", "待提交用人经理", "advance_to_review"]) {
    assert.equal(source.includes(removed), false);
  }
});
```

- [ ] **Step 2: Run frontend tests and verify RED**

Run:

```powershell
Set-Location docs/design/prototypes/ats-low-fi-option-2
npm.cmd test -- --test-name-pattern="screening"
```

Expected: current controller exposes rule recommendation and the view still contains HR review controls.

- [ ] **Step 3: Normalize route and dimensions from the API**

Replace current fields with:

```javascript
return {
  ...base,
  score: safeScore(item?.ai_score),
  recommendation: safeString(item?.ai_recommendation)
    || (item?.llm_status === "failed" ? "AI评分不可用" : "等待评分"),
  dimensions: normalizeDimensions(llmEvaluation?.dimensions),
  routeResult: safeString(item?.route_result),
  routeLabel: item?.route_result === "review" ? "已转交用人经理" : "已暂缓",
};
```

Remove `bulkAction`, undo-bulk state, selected row state, rule-score decision text, and HR review summary from current-flow rendering. Keep single-file technical retry for parser failures and explicitly retryable LLM jobs.

- [ ] **Step 4: Render the new result columns and summaries**

Use columns: `流转结果`, `候选人 / 文件`, `处理状态`, `LLM 结论`, `最终分`, `维度评分`, `主要优势与风险`, `查看候选人`. Show `AI评分不可用` with a neutral warning and `已转交用人经理`, not as a failed candidate.

- [ ] **Step 5: Make task totals match server route outcomes**

Render exactly four counters: `已转交用人经理`, `已暂缓`, `AI评分不可用`, and `文件处理失败`. Do not infer them from rule result presence.

- [ ] **Step 6: Run controller, view, and build checks**

Run:

```powershell
Set-Location docs/design/prototypes/ats-low-fi-option-2
npm.cmd test -- --test-name-pattern="screening"
npm.cmd run build
```

Expected: screening tests pass and Vite build completes without warnings about missing exports.

- [ ] **Step 7: Commit screening UI changes**

```powershell
git add docs/design/prototypes/ats-low-fi-option-2/src/screeningController.js docs/design/prototypes/ats-low-fi-option-2/src/ScreeningViews.jsx docs/design/prototypes/ats-low-fi-option-2/src/screeningController.test.js docs/design/prototypes/ats-low-fi-option-2/src/ScreeningViews.test.js docs/design/prototypes/ats-low-fi-option-2/src/product-theme-jobs-screening.css
git commit -m "feat: show automatic LLM screening outcomes"
```

---

### Task 7: Connect Manager Tasks And Deferred Talent Recovery UI

**Files:**
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/candidateController.js`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/candidateController.test.js`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/CandidateViews.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/InterviewMaterials.test.js`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/workbenchController.js`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/workbenchController.test.js`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/workbenchNotifications.js`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/workbenchNotifications.test.js`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/talentController.js`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/talentController.test.js`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/TalentPoolViews.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/talentPoolViews.test.js`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/App.jsx`

**Interfaces:**
- Consumes: Task 5 workbench task and review-referral APIs.
- Produces: direct manager review navigation, AI-unavailable marker, system deferred-pool entry, and same-application referral action.

- [ ] **Step 1: Write failing workbench and talent controller tests**

```javascript
test("keeps the server review task AI status", async () => {
  const data = await controller.load();
  assert.equal(data.tasks.review.items[0].aiStatus, "failed");
  assert.equal(data.tasks.review.items[0].aiLabel, "AI评分不可用");
});

test("refers a deferred membership to manager review", async () => {
  await controller.referToReview("membership-1", 3);
  assert.deepEqual(client.calls[0], {
    method: "POST",
    path: "/talent-pool-memberships/membership-1/review-referrals",
    headers: { "If-Match": '"3"' },
    body: {},
  });
});
```

- [ ] **Step 2: Run focused frontend tests and verify RED**

Run:

```powershell
Set-Location docs/design/prototypes/ats-low-fi-option-2
node --test src/workbenchController.test.js src/workbenchNotifications.test.js src/talentController.test.js src/talentPoolViews.test.js
```

Expected: AI status and review-referral action are not yet normalized.

- [ ] **Step 3: Normalize durable review task metadata**

Add `taskId`, `aiStatus`, `aiLabel`, and `configWarning` to review items. Change `validateEnvelope` so persisted review task count is validated against its own returned items, not inferred application-stage totals. Notification and workbench candidate rows must open the candidate detail at the screening-evidence tab. Show “岗位未配置用人经理” only when the API emits `config_warning`.

- [ ] **Step 4: Restore persisted LLM evidence in candidate detail**

Add `deferred: "AI 初筛暂缓"` to the stage map. `normalizeCandidateReview` must read the server screening projection and retain total score, recommendation, five dimensions, evidence, gaps, risks, and questions after a direct page load. `CandidateDetail` renders this under “筛选证据”; legacy rule facts appear only in a collapsed “旧版规则结果” section. Remove current-flow HR conclusion editing while preserving manager `review_approved` and `review_rejected` actions.

- [ ] **Step 5: Add system deferred-pool presentation and referral action**

Mark the pool by `system_key`, not editable name. Display original job, final score, deferred timestamp, main gaps, and follow-up owner. Replace the existing terminal reactivation action for this pool with `转交用人经理`; keep existing reactivation behavior for ordinary pools.

- [ ] **Step 6: Preserve route and page state after referral**

On success, update the membership's source application stage to `review`, retain the membership row, show `已转交用人经理`, refresh workbench counts, and keep the user on the same talent-pool detail route.

- [ ] **Step 7: Run frontend unit and build gates**

Run:

```powershell
Set-Location docs/design/prototypes/ats-low-fi-option-2
npm.cmd test
npm.cmd run build
```

Expected: all Node tests pass and production build succeeds.

- [ ] **Step 8: Commit manager and talent UI changes**

```powershell
git add docs/design/prototypes/ats-low-fi-option-2/src/candidateController.js docs/design/prototypes/ats-low-fi-option-2/src/candidateController.test.js docs/design/prototypes/ats-low-fi-option-2/src/CandidateViews.jsx docs/design/prototypes/ats-low-fi-option-2/src/InterviewMaterials.test.js docs/design/prototypes/ats-low-fi-option-2/src/workbenchController.js docs/design/prototypes/ats-low-fi-option-2/src/workbenchController.test.js docs/design/prototypes/ats-low-fi-option-2/src/workbenchNotifications.js docs/design/prototypes/ats-low-fi-option-2/src/workbenchNotifications.test.js docs/design/prototypes/ats-low-fi-option-2/src/talentController.js docs/design/prototypes/ats-low-fi-option-2/src/talentController.test.js docs/design/prototypes/ats-low-fi-option-2/src/TalentPoolViews.jsx docs/design/prototypes/ats-low-fi-option-2/src/talentPoolViews.test.js docs/design/prototypes/ats-low-fi-option-2/src/App.jsx
git commit -m "feat: connect manager review and deferred talent flows"
```

---

### Task 8: Update Operational Documentation And Run Full Release Gates

**Files:**
- Modify: `server/README.md`
- Modify: `README.md`
- Create: `server/tests/test_llm_only_screening_e2e.py`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/scripts/ux08-browser-audit.cjs`

**Interfaces:**
- Consumes: Tasks 1-7 and the completed shared-Nginx protection plan.
- Produces: reproducible end-to-end evidence and accurate operator/developer documentation.

- [ ] **Step 1: Write an end-to-end test for all three screening routes**

```python
@pytest.mark.parametrize(
    ("outcome", "expected_stage", "expected_task_count", "expected_membership_count"),
    [
        (screening_evaluation(score=60), "review", 1, 0),
        (screening_evaluation(score=59), "deferred", 0, 1),
        (GatewayError("provider_unavailable"), "review", 1, 0),
    ],
)
def test_import_to_terminal_route(
    tmp_path, outcome, expected_stage, expected_task_count, expected_membership_count
):
    app, cipher, job = prepared(tmp_path)
    pipeline = LlmScreeningPipeline(
        app.state.identity_store.sync_session, Gateway(outcome), cipher
    )
    if isinstance(outcome, GatewayError):
        job.attempts = job.max_attempts
    try:
        asyncio.run(pipeline.evaluate_item(job))
    except RetryableJobError:
        pytest.fail("final attempt must route instead of queueing another retry")
    with app.state.identity_store.sync_session() as db:
        application = db.get(Application, uuid.UUID(job.payload["application_id"]))
        assert application.stage == expected_stage
        assert db.scalar(select(func.count(ApplicationReviewTask.id))) == expected_task_count
        assert db.scalar(select(func.count(TalentPoolMembership.id))) == expected_membership_count
```

Define `screening_evaluation(score)` in this test file using the five exact v2 dimension keys and limits; import the existing `prepared` and `Gateway` helpers from `server.tests.test_llm_pipeline`. Update the queue payload in Task 4 to include `application_id` so the final assertion uses the routed application directly.

- [ ] **Step 2: Run the E2E test and fix only integration defects**

Run:

```powershell
python -m pytest server/tests/test_llm_only_screening_e2e.py -q
```

Expected: the complete import-to-routing flow passes without any HR stage mutation.

- [ ] **Step 3: Replace stale documentation claims**

Update `server/README.md` and root `README.md` so they state:

```text
New server screening tasks use LLM-only scoring.
60-100 automatically enters hiring-manager review.
0-59 automatically enters the AI deferred talent pool.
Final LLM failure enters manager review with no synthetic score.
Legacy local desktop rule screening remains a separate tool and does not describe server behavior.
```

Remove the server-runtime statements that rule results are authoritative fallback facts or that LLM failure never changes application stage.

- [ ] **Step 4: Run complete backend gates in the repository's Python 3.12 image**

Run:

```powershell
docker build --target test -t ux09-server-test -f server/Dockerfile .
docker run --rm ux09-server-test python -m pytest server/tests --ignore=server/tests/test_production_topology.py --ignore=server/tests/test_observability_topology.py -q
python -m pytest server/tests/test_production_topology.py server/tests/test_observability_topology.py -q
```

Expected: both backend test layers pass.

- [ ] **Step 5: Run complete frontend and browser checks**

Run:

```powershell
Set-Location docs/design/prototypes/ats-low-fi-option-2
npm.cmd test
npm.cmd run build
npm.cmd run test:ux08
```

Expected: Node tests, Vite build, and browser audit pass with screenshots showing no overlapping controls at desktop and mobile widths.

- [ ] **Step 6: Run deployment-protection and formatting gates**

Run from repository root:

```powershell
python -m pytest deploy/tests/test_shared_nginx_release_validator.py deploy/tests/test_remote_deploy_scripts.py server/tests/test_production_topology.py server/tests/test_nginx_security.py -q -p no:cacheprovider
PowerShell -ExecutionPolicy Bypass -File deploy/deploy-remote.ps1 -ValidateOnly
git diff --check
git status --short
```

Expected: all tests pass, validation makes no production mutation, `git diff --check` is empty, and only planned files are modified.

- [ ] **Step 7: Commit docs and full-flow evidence**

```powershell
git add README.md server/README.md server/tests/test_llm_only_screening_e2e.py docs/design/prototypes/ats-low-fi-option-2/scripts/ux08-browser-audit.cjs
git commit -m "test: verify LLM-only screening workflow"
```

- [ ] **Step 8: Prepare production release without deploying yet**

Record the migration head, image digest, complete gate output, current production release, current `aurora-web` container ID, current three-domain smoke, and database backup identifier. Production deployment starts only after this evidence is reviewed and the shared-Nginx release-protection plan is green.
