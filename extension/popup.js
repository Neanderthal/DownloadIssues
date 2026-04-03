import { push as jsPush } from "./lib/push.js";
import { pull as jsPull, listIssues as jsListIssues } from "./lib/pull.js";

const API = "http://127.0.0.1:9741/api";

// -- DOM refs --
const statusEl = document.getElementById("status");
const pushPathDisplay = document.getElementById("push-path-display");
const pushProvider = document.getElementById("push-provider");
const btnPush = document.getElementById("btn-push");
const pushProgress = document.getElementById("push-progress");
const pushFill = document.getElementById("push-fill");
const pushText = document.getElementById("push-text");
const pushResult = document.getElementById("push-result");

const filePicker = document.getElementById("file-picker");
const folderPicker = document.getElementById("folder-picker");

const issuesList = document.getElementById("issues-list");
const pullPath = document.getElementById("pull-path");
const btnPull = document.getElementById("btn-pull");
const pullProgress = document.getElementById("pull-progress");
const pullFill = document.getElementById("pull-fill");
const pullText = document.getElementById("pull-text");
const pullResult = document.getElementById("pull-result");

const settingsMode = document.getElementById("settings-mode");
const hybridSettings = document.getElementById("hybrid-settings");
const settingsResult = document.getElementById("settings-result");

let selectedIssue = null;
let selectedFiles = null; // FileList from browser picker
let selectedName = null;  // display name
let config = { mode: "hybrid" };

// -- Init --

document.addEventListener("DOMContentLoaded", async () => {
  await loadSettings();
  await checkServer();

  // Tabs
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));
      tab.classList.add("active");
      document.getElementById(`tab-${tab.dataset.tab}`).classList.add("active");
    });
  });

  // File pickers (browser-native)
  document.getElementById("btn-browse-file").addEventListener("click", () => filePicker.click());
  document.getElementById("btn-browse-folder").addEventListener("click", () => folderPicker.click());

  filePicker.addEventListener("change", () => {
    if (filePicker.files.length) {
      selectedFiles = filePicker.files;
      selectedName = filePicker.files[0].name;
      pushPathDisplay.textContent = selectedName;
      pushPathDisplay.classList.add("has-file");
      updatePushBtn();
    }
  });

  folderPicker.addEventListener("change", () => {
    if (folderPicker.files.length) {
      selectedFiles = folderPicker.files;
      // webkitRelativePath gives "folder/file.txt" — extract folder name
      const rel = folderPicker.files[0].webkitRelativePath || "";
      selectedName = rel.split("/")[0] || "folder";
      pushPathDisplay.textContent = `${selectedName}/ (${folderPicker.files.length} files)`;
      pushPathDisplay.classList.add("has-file");
      updatePushBtn();
    }
  });

  // Push / Pull
  btnPush.addEventListener("click", startPush);
  document.getElementById("btn-refresh").addEventListener("click", loadIssues);
  btnPull.addEventListener("click", startPull);

  // Settings
  settingsMode.addEventListener("change", () => {
    hybridSettings.classList.toggle("hidden", settingsMode.value === "server");
  });
  document.getElementById("btn-save-settings").addEventListener("click", saveSettings);
});

// -- Settings --

async function loadSettings() {
  const stored = await chrome.storage.local.get([
    "mode", "github_token", "github_repo", "gitflic_token", "gitflic_project",
  ]);
  config = {
    mode: stored.mode || "hybrid",
    github_token: stored.github_token || "",
    github_repo: stored.github_repo || "",
    gitflic_token: stored.gitflic_token || "",
    gitflic_project: stored.gitflic_project || "",
  };

  settingsMode.value = config.mode;
  document.getElementById("settings-github-token").value = config.github_token;
  document.getElementById("settings-github-repo").value = config.github_repo;
  document.getElementById("settings-gitflic-token").value = config.gitflic_token;
  document.getElementById("settings-gitflic-project").value = config.gitflic_project;
  hybridSettings.classList.toggle("hidden", config.mode === "server");
}

function normalizeRepo(val) {
  // "owner / Repo" → "owner/repo"
  return val.trim().split("/").map((s) => s.trim().toLowerCase()).join("/");
}

async function saveSettings() {
  config = {
    mode: settingsMode.value,
    github_token: document.getElementById("settings-github-token").value.trim(),
    github_repo: normalizeRepo(document.getElementById("settings-github-repo").value),
    gitflic_token: document.getElementById("settings-gitflic-token").value.trim(),
    gitflic_project: normalizeRepo(document.getElementById("settings-gitflic-project").value),
  };

  await chrome.storage.local.set(config);
  settingsResult.className = "result success";
  settingsResult.textContent = "Settings saved";
  settingsResult.classList.remove("hidden");
  setTimeout(() => settingsResult.classList.add("hidden"), 2000);
}

function getProviderConfig(provider) {
  if (provider === "gitflic") {
    return { token: config.gitflic_token, repo: config.gitflic_project };
  }
  return { token: config.github_token, repo: config.github_repo };
}

// -- Server check --

async function checkServer() {
  try {
    const r = await fetch(`${API}/health`, { signal: AbortSignal.timeout(3000) });
    if (r.ok) {
      const data = await r.json();
      statusEl.textContent = data.provider;
      statusEl.className = "status online";
      pushProvider.value = data.provider;

      // Pre-fill settings from server config if empty
      if (!config.github_repo || !config.gitflic_project) {
        const cfgResp = await fetch(`${API}/config`);
        const cfg = await cfgResp.json();
        if (!config.github_repo && cfg.github_repo) {
          config.github_repo = cfg.github_repo;
          document.getElementById("settings-github-repo").value = cfg.github_repo;
        }
        if (!config.gitflic_project && cfg.gitflic_project) {
          config.gitflic_project = cfg.gitflic_project;
          document.getElementById("settings-gitflic-project").value = cfg.gitflic_project;
        }
      }
      return true;
    }
  } catch {}
  statusEl.textContent = "offline";
  statusEl.className = "status offline";
  return false;
}

// -- Push --

function updatePushBtn() {
  btnPush.disabled = !selectedFiles;
}

async function startPush() {
  if (!selectedFiles) return;

  btnPush.disabled = true;
  pushResult.classList.add("hidden");
  pushProgress.classList.remove("hidden");
  pushFill.style.width = "0%";
  pushText.textContent = "Encrypting...";

  const provider = pushProvider.value;

  try {
    // Step 1: Upload file to server for encryption
    pushFill.style.width = "5%";
    pushText.textContent = "Uploading to server for encryption...";

    const formData = new FormData();
    for (let i = 0; i < selectedFiles.length; i++) {
      const f = selectedFiles[i];
      // Use webkitRelativePath for folder uploads, plain name for single file
      const path = f.webkitRelativePath || f.name;
      formData.append("files", f, path);
    }

    const encResp = await fetch(`${API}/encrypt-upload`, {
      method: "POST",
      body: formData,
    });

    if (!encResp.ok) {
      const err = await encResp.json();
      throw new Error(err.error || `Encrypt failed: ${encResp.status}`);
    }

    const encData = await encResp.json();
    const { chunks, metadata, filename, timestamp } = encData;

    pushFill.style.width = "20%";
    pushText.textContent = `Encrypted: ${chunks.length} chunk(s), ${encData.total_hex_chars} hex chars`;

    // Step 2: Upload chunks to provider via JS API
    if (config.mode === "hybrid") {
      const { token, repo } = getProviderConfig(provider);
      if (!token || !repo) {
        throw new Error(`Configure ${provider} token and repo in Settings first`);
      }

      await jsPush({
        // Pass pre-encrypted data instead of inputPath
        preEncrypted: { chunks, metadata, filename, timestamp, encData },
        provider,
        token,
        repo,
        onProgress: handlePushProgress,
      });
    } else {
      // Server mode: use SSE push (needs a local path, not available here)
      // Fall back to hybrid upload with server tokens
      throw new Error("Server mode requires file path. Use Hybrid mode with browser file picker.");
    }
  } catch (e) {
    pushResult.className = "result error";
    pushResult.textContent = e.message;
    pushResult.classList.remove("hidden");
  }

  btnPush.disabled = false;
}

function handlePushProgress(data) {
  const handlers = {
    encrypting: () => {
      pushText.textContent = `Encrypting: ${data.detail || "..."}`;
      pushFill.style.width = "10%";
    },
    encrypted: () => {
      pushText.textContent = `Encrypted: ${data.chunks} chunks`;
      pushFill.style.width = "20%";
    },
    creating_issue: () => {
      pushText.textContent = `Creating issue: ${data.title}`;
      pushFill.style.width = "25%";
    },
    issue_created: () => {
      pushText.textContent = `Issue #${data.issueNumber} created`;
      pushFill.style.width = "30%";
    },
    uploading: () => {
      const pct = 30 + (data.chunk / data.total) * 65;
      pushFill.style.width = `${pct}%`;
      pushText.textContent = `Uploading chunk ${data.chunk + 1}/${data.total}`;
    },
    posting_metadata: () => {
      pushText.textContent = "Posting metadata...";
      pushFill.style.width = "95%";
    },
    done: () => {
      pushFill.style.width = "100%";
      pushText.textContent = "Done!";
      pushResult.className = "result success";
      pushResult.innerHTML = `Issue <strong>#${data.issueNumber}</strong> — ${data.chunks} chunks`;
      if (data.url) {
        pushResult.innerHTML += `<br><a href="${data.url}" target="_blank" style="color:#89b4fa">${data.url}</a>`;
      }
      pushResult.classList.remove("hidden");
    },
    error: () => {
      throw new Error(data.message);
    },
  };
  const fn = handlers[data.stage];
  if (fn) fn();
}

// -- Issues --

async function loadIssues() {
  issuesList.innerHTML = '<div class="placeholder">Loading...</div>';
  selectedIssue = null;
  updatePullBtn();

  const provider = pushProvider.value;

  try {
    let issues;

    if (config.mode === "hybrid") {
      const { token, repo } = getProviderConfig(provider);
      if (!token || !repo) {
        issuesList.innerHTML = `<div class="placeholder">Configure ${provider} in Settings</div>`;
        return;
      }
      const all = await jsListIssues({ provider, token, repo });
      issues = all.map((i) => ({
        number: i.number,
        title: i.title || "",
        labels: (i.labels || []).map((l) => l.name || l),
        updated_at: i.updated_at || "",
      }));
    } else {
      const r = await fetch(`${API}/issues?provider=${provider}`);
      const data = await r.json();
      if (data.error) {
        issuesList.innerHTML = `<div class="placeholder">${data.error}</div>`;
        return;
      }
      issues = data.issues || [];
    }

    if (!issues.length) {
      issuesList.innerHTML = '<div class="placeholder">No data-transfer issues found</div>';
      return;
    }

    issuesList.innerHTML = "";
    for (const issue of issues) {
      const el = document.createElement("div");
      el.className = "issue-item";
      el.dataset.number = issue.number;

      const labels = issue.labels.length ? ` [${issue.labels.join(", ")}]` : "";
      el.innerHTML = `
        <div>
          <span class="issue-number">#${issue.number}</span>
          <span class="issue-title">${escapeHtml(issue.title)}</span>
        </div>
        <div class="issue-meta">${(issue.updated_at || "").slice(0, 10)}${labels}</div>
      `;

      el.addEventListener("click", () => {
        document.querySelectorAll(".issue-item.selected").forEach((s) => s.classList.remove("selected"));
        el.classList.add("selected");
        selectedIssue = issue.number;
        updatePullBtn();
      });

      issuesList.appendChild(el);
    }
  } catch (e) {
    issuesList.innerHTML = `<div class="placeholder">Error: ${e.message}</div>`;
  }
}

// -- Pull --

function updatePullBtn() {
  btnPull.disabled = !selectedIssue;
}

async function startPull() {
  if (!selectedIssue) return;

  btnPull.disabled = true;
  pullResult.classList.add("hidden");
  pullProgress.classList.remove("hidden");
  pullFill.style.width = "0%";
  pullText.textContent = "Starting...";

  const provider = pushProvider.value;

  try {
    if (config.mode === "hybrid") {
      await pullHybrid(selectedIssue, provider);
    } else {
      await pullServer(selectedIssue, provider);
    }
  } catch (e) {
    pullResult.className = "result error";
    pullResult.textContent = e.message;
    pullResult.classList.remove("hidden");
  }

  btnPull.disabled = false;
}

async function pullHybrid(issueNumber, provider) {
  const { token, repo } = getProviderConfig(provider);
  if (!token || !repo) {
    throw new Error(`Configure ${provider} token and repo in Settings first`);
  }

  await jsPull({
    issueNumber,
    provider,
    token,
    repo,
    outputDir: pullPath.value || undefined,
    onProgress: handlePullProgress,
  });
}

async function pullServer(issueNumber, provider) {
  const body = { issue_number: issueNumber, provider };
  if (pullPath.value) body.output_dir = pullPath.value;

  const response = await fetch(`${API}/pull`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  await readSSE(response, pullSSEHandlers());
}

function handlePullProgress(data) {
  const handlers = {
    fetching_metadata: () => {
      pullText.textContent = "Fetching metadata...";
      pullFill.style.width = "10%";
    },
    metadata: () => {
      pullText.textContent = data.filename
        ? `Found: ${data.filename} (${data.totalParts} parts)`
        : (data.message || "No metadata");
      pullFill.style.width = "20%";
    },
    fetching_chunks: () => {
      pullText.textContent = "Fetching chunks...";
      pullFill.style.width = "30%";
    },
    chunks_fetched: () => {
      const v = data.verified ? "verified" : "unverified";
      pullText.textContent = `${data.count} chunks (${data.totalChars} chars) — ${v}`;
      pullFill.style.width = "60%";
    },
    decrypting: () => {
      pullText.textContent = "Decrypting...";
      pullFill.style.width = "75%";
    },
    done: () => {
      pullFill.style.width = "100%";
      pullText.textContent = "Done!";
      pullResult.className = "result success";
      pullResult.textContent = `Extracted to: ${data.outputPath}`;
      pullResult.classList.remove("hidden");
    },
    warning: () => {
      pullText.textContent = `Warning: ${data.message}`;
    },
    error: () => {
      throw new Error(data.message);
    },
  };
  const fn = handlers[data.stage];
  if (fn) fn();
}

function pullSSEHandlers() {
  return {
    fetching_metadata: () => { pullText.textContent = "Fetching metadata..."; pullFill.style.width = "10%"; },
    metadata: (d) => {
      pullText.textContent = d.filename ? `Found: ${d.filename} (${d.total_parts} parts)` : (d.message || "No metadata");
      pullFill.style.width = "20%";
    },
    fetching_chunks: () => { pullText.textContent = "Fetching chunks..."; pullFill.style.width = "30%"; },
    chunks_fetched: (d) => {
      pullText.textContent = `${d.count} chunks — ${d.verified ? "verified" : "unverified"}`;
      pullFill.style.width = "60%";
    },
    decrypting: () => { pullText.textContent = "Decrypting..."; pullFill.style.width = "75%"; },
    done: (d) => {
      pullFill.style.width = "100%";
      pullText.textContent = "Done!";
      pullResult.className = "result success";
      pullResult.textContent = `Extracted to: ${d.output_path}`;
      pullResult.classList.remove("hidden");
    },
    warning: (d) => { pullText.textContent = `Warning: ${d.message}`; },
    error: (d) => {
      pullText.textContent = "Failed";
      pullResult.className = "result error";
      pullResult.textContent = d.message;
      pullResult.classList.remove("hidden");
    },
  };
}

// -- SSE reader (for server mode) --

async function readSSE(response, handlers) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop();

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        try {
          const data = JSON.parse(line.slice(6));
          const handler = handlers[data.stage];
          if (handler) handler(data);
        } catch {}
      }
    }
  }
}

// -- Util --

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}
