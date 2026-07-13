import assert from "node:assert/strict";
import test from "node:test";

const stateModule = await import("./jobWorkspaceState.js").catch(() => ({}));

const {
  appendJobPage,
  createInitialJobWorkspaceState,
  failJobRequest,
  startJobRequest,
  succeedJobRequest,
  upsertJobMutation,
} = stateModule;

const firstPage = {
  records: [{ id: "job-1", name: "平台工程师", version: 1 }],
  nextCursor: "next-1",
  departments: [{ id: "department-1", name: "技术部" }],
  owners: [{ id: "owner-1", name: "招聘经理" }],
  statusCounts: { 草稿: 1, 招聘中: 2, 已暂停: 0, 已关闭: 0, 已归档: 0 },
};

test("stale success and failure responses leave the active request unchanged", () => {
  assert.equal(typeof createInitialJobWorkspaceState, "function");
  const loading = startJobRequest(createInitialJobWorkspaceState(), 2, { q: "平台" });

  const staleSuccess = succeedJobRequest(loading, 1, firstPage);
  const staleFailure = failJobRequest(loading, 1, new Error("旧请求失败"));

  assert.equal(staleSuccess, loading);
  assert.equal(staleFailure, loading);
});

test("append page preserves existing records and deduplicates by job id", () => {
  const ready = succeedJobRequest(
    startJobRequest(createInitialJobWorkspaceState(), 1, {}),
    1,
    firstPage,
  );
  const loadingNextPage = startJobRequest(ready, 2, ready.filters);

  const appended = appendJobPage(loadingNextPage, 2, {
    ...firstPage,
    records: [
      { id: "job-1", name: "重复职位", version: 2 },
      { id: "job-2", name: "前端工程师", version: 1 },
    ],
    nextCursor: null,
  });

  assert.deepEqual(appended.records, [firstPage.records[0], { id: "job-2", name: "前端工程师", version: 1 }]);
  assert.equal(appended.nextCursor, null);
});

test("request failure preserves the previous successful page and metadata", () => {
  const ready = succeedJobRequest(
    startJobRequest(createInitialJobWorkspaceState(), 1, {}),
    1,
    firstPage,
  );
  const loading = startJobRequest(ready, 2, { status: "招聘中" });

  const failed = failJobRequest(loading, 2, new Error("network unavailable"));

  assert.equal(failed.status, "error");
  assert.equal(failed.error, "network unavailable");
  assert.deepEqual(failed.records, firstPage.records);
  assert.deepEqual(failed.departments, firstPage.departments);
  assert.deepEqual(failed.owners, firstPage.owners);
  assert.deepEqual(failed.statusCounts, firstPage.statusCounts);
});

test("mutation upsert replaces an existing job and prepends a newly created job", () => {
  const ready = succeedJobRequest(
    startJobRequest(createInitialJobWorkspaceState(), 1, {}),
    1,
    firstPage,
  );

  const updated = upsertJobMutation(ready, { id: "job-1", name: "高级平台工程师", version: 2 });
  const created = upsertJobMutation(updated, { id: "job-2", name: "数据工程师", version: 1 });

  assert.deepEqual(created.records, [
    { id: "job-2", name: "数据工程师", version: 1 },
    { id: "job-1", name: "高级平台工程师", version: 2 },
  ]);
});
