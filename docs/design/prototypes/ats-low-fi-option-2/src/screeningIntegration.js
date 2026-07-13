import { normalizeScreeningTask } from "./screeningController.js";

const SAFE_METADATA_KEYS = ["position", "source", "note", "llmEnabled", "creator", "createdAt"];
const LEGAL_SOURCES = new Set(["BOSS 直聘", "猎聘", "智联招聘", "员工内推", "人才库重新激活", "其他合法来源", "本地上传"]);

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function codedError(code, message) {
  const error = new Error(message);
  error.code = code;
  return error;
}

function isAbort(error, signal) {
  return signal?.aborted || error?.name === "AbortError";
}

function safeMetadata(value) {
  const metadata = {};
  for (const key of SAFE_METADATA_KEYS) metadata[key] = value[key];
  return metadata;
}

function isValidMetadata(value) {
  return typeof value.position === "string"
    && value.position.length > 0
    && LEGAL_SOURCES.has(value.source)
    && typeof value.note === "string"
    && typeof value.llmEnabled === "boolean"
    && typeof value.creator === "string"
    && typeof value.createdAt === "string";
}

export function serializeRecentScreeningTask(task) {
  if (!isRecord(task) || task.serverBacked !== true || typeof task.id !== "string" || !task.id || typeof task.jobId !== "string" || !task.jobId || !isValidMetadata(task)) {
    return "";
  }
  return JSON.stringify({ id: task.id, jobId: task.jobId, serverBacked: true, ...safeMetadata(task) });
}

export function parseRecentScreeningTask(raw) {
  try {
    const value = JSON.parse(raw);
    const allowedKeys = new Set(["id", "jobId", "serverBacked", ...SAFE_METADATA_KEYS]);
    if (!isRecord(value) || Object.keys(value).some((key) => !allowedKeys.has(key))) return null;
    if (value.serverBacked !== true || typeof value.id !== "string" || !value.id || typeof value.jobId !== "string" || !value.jobId || !isValidMetadata(value)) return null;
    return { id: value.id, jobId: value.jobId, serverBacked: true, ...safeMetadata(value) };
  } catch {
    return null;
  }
}

export function mergeServerTaskMetadata(snapshot, metadata) {
  return { ...snapshot, ...safeMetadata(metadata), serverBacked: true };
}

export function createScreeningWorkflow(controller) {
  let submitting = false;

  async function submit({ jobId, files, metadata, signal, onProgress = () => {} }) {
    if (submitting) throw codedError("SUBMISSION_IN_PROGRESS", "screening submission already in progress");
    submitting = true;
    try {
      const run = await controller.createRun(jobId, { signal });
      if (signal?.aborted) return null;
      if (!run?.id) throw codedError("INVALID_RUN", "screening run was not created");

      const selectedFiles = Array.from(files ?? []);
      let succeeded = 0;
      let failedCount = 0;
      onProgress({ completed: 0, total: selectedFiles.length });
      for (let index = 0; index < selectedFiles.length; index += 1) {
        try {
          await controller.uploadFiles(run.id, [selectedFiles[index]], { signal });
          succeeded += 1;
        } catch (error) {
          if (isAbort(error, signal)) return null;
          failedCount += 1;
        }
        onProgress({ completed: index + 1, total: selectedFiles.length });
      }

      if (signal?.aborted) return null;
      if (succeeded === 0) throw codedError("ALL_UPLOADS_FAILED", "all screening uploads failed");
      await controller.startRun(run.id, { signal });
      if (signal?.aborted) return null;
      const [currentRun, items] = await Promise.all([
        controller.getRun(run.id, { signal }),
        controller.getItems(run.id, { signal }),
      ]);
      if (signal?.aborted) return null;
      return {
        failedCount,
        task: mergeServerTaskMetadata(normalizeScreeningTask(currentRun, items), metadata),
      };
    } catch (error) {
      if (isAbort(error, signal)) return null;
      throw error;
    } finally {
      submitting = false;
    }
  }

  return { submit, isSubmitting: () => submitting };
}

export function pollServerTask({ task, controller, signal, onTaskChange, onError = () => {} }) {
  if (!task?.serverBacked) return { done: Promise.resolve(null), retry: async () => null };
  const metadata = safeMetadata(task);
  const start = () => controller.pollRun(task.id, {
    signal,
    onSnapshot: (snapshot) => onTaskChange(mergeServerTaskMetadata(snapshot, metadata)),
  }).catch((error) => {
    if (!isAbort(error, signal)) onError(error);
    return null;
  });
  let done = start();

  return {
    done,
    async retry(itemId) {
      if (signal?.aborted) return null;
      try {
        await controller.retryItem(itemId, { signal });
        if (signal?.aborted) return null;
        done = start();
        return true;
      } catch (error) {
        if (!isAbort(error, signal)) onError(error);
        return null;
      }
    },
  };
}
