const jdText = document.querySelector("#jdText");
const jdFile = document.querySelector("#jdFile");
const jobSelect = document.querySelector("#jobSelect");
const jobTitle = document.querySelector("#jobTitle");
const saveJobBtn = document.querySelector("#saveJobBtn");
const deleteJobBtn = document.querySelector("#deleteJobBtn");
const resumeFiles = document.querySelector("#resumeFiles");
const dropZone = document.querySelector("#dropZone");
const fileList = document.querySelector("#fileList");
const analyzeBtn = document.querySelector("#analyzeBtn");
const downloadBtn = document.querySelector("#downloadBtn");
const statusText = document.querySelector("#statusText");
const resultList = document.querySelector("#resultList");
const resultCount = document.querySelector("#resultCount");
const sampleBtn = document.querySelector("#sampleBtn");
const settingsBtn = document.querySelector("#settingsBtn");
const settingsDialog = document.querySelector("#settingsDialog");
const closeSettingsBtn = document.querySelector("#closeSettingsBtn");
const cancelSettingsBtn = document.querySelector("#cancelSettingsBtn");
const llmEnabled = document.querySelector("#llmEnabled");
const llmProvider = document.querySelector("#llmProvider");
const llmBaseUrl = document.querySelector("#llmBaseUrl");
const llmModel = document.querySelector("#llmModel");
const llmApiKey = document.querySelector("#llmApiKey");
const saveApiKey = document.querySelector("#saveApiKey");
const saveSettingsBtn = document.querySelector("#saveSettingsBtn");
const testLlmBtn = document.querySelector("#testLlmBtn");
const llmTestStatus = document.querySelector("#llmTestStatus");

const CSV_HEADERS = [
  "文件名",
  "匹配分",
  "推荐结论",
  "必须条件命中数",
  "必须条件总数",
  "缺失必须条件",
  "命中必须条件",
  "命中加分项",
  "识别年限",
  "LLM评分",
  "LLM结论",
  "LLM理由",
  "风险点",
  "面试问题",
  "LLM错误"
];

let currentRows = [];
let savedJobs = [];

window.addEventListener("DOMContentLoaded", loadConfig);

sampleBtn.addEventListener("click", () => {
  jobTitle.value = "AI 工程师";
  jdText.value = [
    "岗位：AI 工程师",
    "必须条件：Python, 机器学习, 深度学习, LLM, 大模型",
    "加分项：PyTorch, TensorFlow, HuggingFace, Transformers, LangChain, LlamaIndex, RAG, Agent, Function Calling, Tool Calling, 向量数据库, Embedding, NLP, 模型微调, LoRA, SFT, RLHF, 模型评测, FastAPI, Docker, Kubernetes, Linux"
  ].join("\n");
  jobSelect.value = "";
});

jobSelect.addEventListener("change", () => {
  const job = savedJobs.find((item) => item.id === jobSelect.value);
  if (!job) {
    jobTitle.value = "";
    deleteJobBtn.disabled = true;
    return;
  }
  jobTitle.value = job.title;
  jdText.value = job.jd_text;
  deleteJobBtn.disabled = false;
});

saveJobBtn.addEventListener("click", saveJob);
deleteJobBtn.addEventListener("click", deleteJob);
saveSettingsBtn.addEventListener("click", saveSettings);
testLlmBtn.addEventListener("click", testLlmConnection);
settingsBtn.addEventListener("click", () => settingsDialog.showModal());
closeSettingsBtn.addEventListener("click", () => settingsDialog.close());
cancelSettingsBtn.addEventListener("click", () => settingsDialog.close());
resumeFiles.addEventListener("change", renderFileList);
llmProvider.addEventListener("change", applyProviderDefaults);

dropZone.addEventListener("dragover", (event) => {
  event.preventDefault();
  dropZone.classList.add("dragover");
});

dropZone.addEventListener("dragleave", () => {
  dropZone.classList.remove("dragover");
});

dropZone.addEventListener("drop", (event) => {
  event.preventDefault();
  dropZone.classList.remove("dragover");
  resumeFiles.files = event.dataTransfer.files;
  renderFileList();
});

analyzeBtn.addEventListener("click", async () => {
  const formData = new FormData();
  formData.append("jd_text", jdText.value);
  if (jdFile.files[0]) {
    formData.append("jd_file", jdFile.files[0]);
  }
  formData.append("llm_enabled", llmEnabled.checked ? "1" : "0");
  formData.append("llm_provider", llmProvider.value);
  formData.append("llm_base_url", llmBaseUrl.value);
  formData.append("llm_model", llmModel.value);
  formData.append("llm_api_key", llmApiKey.value);
  for (const file of resumeFiles.files) {
    formData.append("resumes", file);
  }

  analyzeBtn.disabled = true;
  downloadBtn.disabled = true;
  currentRows = [];
  renderResults([]);
  statusText.textContent = "准备筛选...";

  try {
    const response = await fetch("/api/analyze-stream", {
      method: "POST",
      body: formData
    });
    if (!response.ok) {
      const payload = await response.json();
      throw new Error(payload.error || "筛选失败");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (line.trim()) {
          handleAnalyzeEvent(JSON.parse(line));
        }
      }
    }
    if (buffer.trim()) {
      handleAnalyzeEvent(JSON.parse(buffer));
    }
    downloadBtn.disabled = currentRows.length === 0;
  } catch (error) {
    currentRows = [];
    renderResults([]);
    statusText.textContent = error.message;
  } finally {
    analyzeBtn.disabled = false;
  }
});

downloadBtn.addEventListener("click", () => {
  const csv = toCsv(currentRows);
  const blob = new Blob(["\ufeff", csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "简历筛选结果.csv";
  link.click();
  URL.revokeObjectURL(url);
});

function handleAnalyzeEvent(event) {
  if (event.type === "progress") {
    statusText.textContent = event.message || `正在处理 ${event.current}/${event.total}`;
    return;
  }
  if (event.type === "done") {
    currentRows = event.rows || [];
    renderResults(currentRows);
    statusText.textContent = `筛选完成，共 ${event.count || currentRows.length} 份简历`;
    return;
  }
  if (event.type === "error") {
    throw new Error(event.error || "筛选失败");
  }
}

async function loadConfig() {
  try {
    const response = await fetch("/api/config");
    const config = await response.json();
    applySettings(config.settings || {});
    renderJobs(config.jobs || []);
    statusText.textContent = "配置已加载";
  } catch {
    statusText.textContent = "配置加载失败，可继续临时筛选";
  }
}

function applySettings(settings) {
  llmProvider.value = settings.llm_provider || "openai_compatible";
  llmBaseUrl.value = settings.llm_base_url || "";
  llmModel.value = settings.llm_model || "";
  llmApiKey.value = settings.llm_api_key || "";
  llmEnabled.checked = Boolean(settings.llm_enabled);
  saveApiKey.checked = Boolean(settings.save_api_key);
  applyProviderDefaults();
}

function renderJobs(jobs) {
  savedJobs = jobs;
  const selectedId = jobSelect.value;
  jobSelect.innerHTML = '<option value="">新岗位 / 临时 JD</option>';
  for (const job of savedJobs) {
    const option = document.createElement("option");
    option.value = job.id;
    option.textContent = job.title;
    jobSelect.appendChild(option);
  }
  if (selectedId && savedJobs.some((job) => job.id === selectedId)) {
    jobSelect.value = selectedId;
    deleteJobBtn.disabled = false;
  } else {
    jobSelect.value = "";
    deleteJobBtn.disabled = true;
  }
}

async function saveSettings() {
  statusText.textContent = "正在保存 LLM 设置...";
  try {
    const response = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        llm_provider: llmProvider.value,
        llm_base_url: llmBaseUrl.value,
        llm_model: llmModel.value,
        llm_api_key: llmApiKey.value,
        llm_enabled: llmEnabled.checked,
        save_api_key: saveApiKey.checked
      })
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "保存失败");
    }
    applySettings(payload.settings || {});
    statusText.textContent = "LLM 设置已保存";
    settingsDialog.close();
  } catch (error) {
    statusText.textContent = error.message;
  }
}

async function testLlmConnection() {
  llmTestStatus.textContent = "正在测试连接...";
  testLlmBtn.disabled = true;
  try {
    const response = await fetch("/api/llm-test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        llm_provider: llmProvider.value,
        llm_base_url: llmBaseUrl.value,
        llm_model: llmModel.value,
        llm_api_key: llmApiKey.value
      })
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "连接测试失败");
    }
    llmTestStatus.textContent = payload.message || "连接测试成功";
  } catch (error) {
    llmTestStatus.textContent = error.message;
  } finally {
    testLlmBtn.disabled = false;
  }
}

async function saveJob() {
  statusText.textContent = "正在保存岗位...";
  try {
    const response = await fetch("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id: jobSelect.value,
        title: jobTitle.value,
        jd_text: jdText.value
      })
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "岗位保存失败");
    }
    renderJobs(payload.jobs || []);
    if (payload.job?.id) {
      jobSelect.value = payload.job.id;
      deleteJobBtn.disabled = false;
    }
    statusText.textContent = "岗位已保存";
  } catch (error) {
    statusText.textContent = error.message;
  }
}

async function deleteJob() {
  if (!jobSelect.value) return;
  statusText.textContent = "正在删除岗位...";
  try {
    const response = await fetch(`/api/jobs/${encodeURIComponent(jobSelect.value)}`, {
      method: "DELETE"
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "删除失败");
    }
    jobTitle.value = "";
    jdText.value = "";
    await loadConfig();
    statusText.textContent = payload.deleted ? "岗位已删除" : "岗位不存在";
  } catch (error) {
    statusText.textContent = error.message;
  }
}

function renderFileList() {
  const files = Array.from(resumeFiles.files);
  fileList.innerHTML = "";
  for (const file of files) {
    const item = document.createElement("li");
    item.textContent = `${file.name} (${formatBytes(file.size)})`;
    fileList.appendChild(item);
  }
  statusText.textContent = files.length ? `已选择 ${files.length} 份简历` : "等待上传";
}

function renderResults(rows) {
  resultCount.textContent = `${rows.length} 份简历`;
  resultList.innerHTML = "";
  if (!rows.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "上传简历后，这里会显示排序结果。";
    resultList.appendChild(empty);
    return;
  }

  for (const row of rows) {
    resultList.appendChild(createCandidateCard(row));
  }
}

function createCandidateCard(row) {
  const card = document.createElement("article");
  card.className = "candidate-card";
  const llmError = row["LLM错误"];
  const llmScore = row["LLM评分"];

  card.innerHTML = `
    <div class="candidate-head">
      <div>
        <h3 class="candidate-title">${escapeHtml(row["文件名"] || "未命名简历")}</h3>
        <div class="candidate-verdict">${escapeHtml(row["推荐结论"] || "待判断")}</div>
      </div>
      <div class="score-group">
        ${scorePill("匹配分", row["匹配分"])}
        ${llmScore !== undefined && llmScore !== "" ? scorePill("LLM评分", llmScore) : ""}
      </div>
    </div>
    <div class="candidate-grid">
      ${tagBlock("命中必须条件", row["命中必须条件"], "暂无命中")}
      ${tagBlock("命中加分项", row["命中加分项"], "暂无加分项")}
      ${tagBlock("缺失必须条件", row["缺失必须条件"], "无明显缺失", "warning")}
    </div>
    <div class="candidate-notes">
      ${noteBlock("LLM结论", row["LLM结论"], "未启用或暂无结论")}
      ${noteBlock("LLM理由", row["LLM理由"], "暂无理由")}
      ${noteBlock("风险点", row["风险点"], "暂无明显风险")}
      ${noteBlock("面试问题", row["面试问题"], "暂无建议问题")}
      ${llmError ? noteBlock("LLM错误", llmError, "", "error") : ""}
    </div>
  `;
  return card;
}

function scorePill(label, value) {
  const text = value === undefined || value === null || value === "" ? "-" : String(value);
  return `
    <div class="score-pill">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(text)}</strong>
    </div>
  `;
}

function tagBlock(title, value, emptyText, tone = "") {
  const tags = splitTerms(value);
  const className = tone ? `tag ${tone}` : "tag";
  return `
    <section class="result-block">
      <h4>${escapeHtml(title)}</h4>
      ${
        tags.length
          ? `<div class="tag-list">${tags.map((tag) => `<span class="${className}">${escapeHtml(tag)}</span>`).join("")}</div>`
          : `<p class="muted">${escapeHtml(emptyText)}</p>`
      }
    </section>
  `;
}

function noteBlock(title, value, emptyText, tone = "") {
  const text = String(value || "").trim();
  const className = tone ? `note-block ${tone}` : "note-block";
  return `
    <section class="${className}">
      <h4>${escapeHtml(title)}</h4>
      <p>${escapeHtml(text || emptyText)}</p>
    </section>
  `;
}

function splitTerms(value) {
  return String(value || "")
    .split(/[，,、\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function toCsv(rows) {
  const lines = [CSV_HEADERS.join(",")];
  for (const row of rows) {
    lines.push(CSV_HEADERS.map((header) => csvCell(row[header])).join(","));
  }
  return lines.join("\r\n");
}

function csvCell(value) {
  const text = String(value ?? "");
  return `"${text.replaceAll('"', '""')}"`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function applyProviderDefaults() {
  if (llmProvider.value === "ollama" && !llmBaseUrl.value.trim()) {
    llmBaseUrl.value = "http://127.0.0.1:11434/v1/chat/completions";
  }
  if (llmProvider.value === "openai_compatible" && !llmBaseUrl.value.trim()) {
    llmBaseUrl.value = "https://api.openai.com/v1";
  }
}
