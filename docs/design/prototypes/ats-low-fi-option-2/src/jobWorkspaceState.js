const EMPTY_FILTERS = Object.freeze({
  q: "",
  status: "全部",
  departmentId: "",
  ownerId: "",
});

const EMPTY_STATUS_COUNTS = Object.freeze({
  草稿: 0,
  招聘中: 0,
  已暂停: 0,
  已关闭: 0,
  已归档: 0,
});

export function createInitialJobWorkspaceState() {
  return {
    status: "idle",
    records: [],
    nextCursor: null,
    departments: [],
    owners: [],
    statusCounts: { ...EMPTY_STATUS_COUNTS },
    filters: { ...EMPTY_FILTERS },
    error: "",
    requestId: 0,
  };
}

export function startJobRequest(state, requestId, filters) {
  return {
    ...state,
    status: "loading",
    filters: { ...EMPTY_FILTERS, ...filters },
    error: "",
    requestId,
  };
}

export function succeedJobRequest(state, requestId, page) {
  if (state.requestId !== requestId) return state;
  return {
    ...state,
    status: "ready",
    records: page.records,
    nextCursor: page.nextCursor,
    departments: page.departments,
    owners: page.owners,
    statusCounts: page.statusCounts,
    error: "",
  };
}

export function appendJobPage(state, requestId, page) {
  if (state.requestId !== requestId) return state;
  const existingIds = new Set(state.records.map((record) => record.id));
  return {
    ...state,
    status: "ready",
    records: [...state.records, ...page.records.filter((record) => !existingIds.has(record.id))],
    nextCursor: page.nextCursor,
    departments: page.departments,
    owners: page.owners,
    statusCounts: page.statusCounts,
    error: "",
  };
}

export function failJobRequest(state, requestId, error) {
  if (state.requestId !== requestId) return state;
  return {
    ...state,
    status: "error",
    error: error instanceof Error ? error.message : String(error || ""),
  };
}

export function upsertJobMutation(state, record) {
  const existingIndex = state.records.findIndex((item) => item.id === record.id);
  if (existingIndex < 0) return { ...state, records: [record, ...state.records] };
  return {
    ...state,
    records: state.records.map((item, index) => index === existingIndex ? record : item),
  };
}
