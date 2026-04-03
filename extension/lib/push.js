/**
 * Push orchestration: encrypt via local server → upload chunks via JS API.
 *
 * Flow:
 *   1. POST /api/encrypt → get hex chunks + metadata
 *   2. JS creates issue + uploads chunks directly to GitHub/GitFlic
 */

import { GitHubAPI } from "./github-api.js";
import { GitFlicAPI } from "./gitflic-api.js";

const SERVER = "http://127.0.0.1:9741/api";
const TRANSFER_LABEL = "data-transfer";

/**
 * Push a file/folder to a git platform.
 *
 * @param {object} opts
 * @param {string} [opts.inputPath] - Local file/folder path (server encrypts)
 * @param {object} [opts.preEncrypted] - Already encrypted data from /api/encrypt-upload
 * @param {string} opts.provider - "github" or "gitflic"
 * @param {string} opts.token - API token for the provider
 * @param {string} opts.repo - "owner/repo" or "owner/project"
 * @param {string} [opts.gpgKey] - GPG key ID (default from server config)
 * @param {number} [opts.delay=2000] - ms between chunk uploads
 * @param {function} [opts.onProgress] - callback({ stage, ...data })
 */
export async function push(opts) {
  const {
    inputPath,
    preEncrypted,
    provider,
    token,
    repo,
    gpgKey,
    delay = 2000,
    onProgress = () => {},
  } = opts;

  let chunks, metadata, filename, timestamp;

  if (preEncrypted) {
    // Already encrypted by /api/encrypt-upload
    chunks = preEncrypted.chunks;
    metadata = preEncrypted.metadata;
    filename = preEncrypted.filename;
    timestamp = preEncrypted.timestamp;
  } else {
    // Encrypt via local server (path-based)
    onProgress({ stage: "encrypting", detail: `tar + gpg + hex` });

    const encResp = await fetch(`${SERVER}/encrypt`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ input_path: inputPath, gpg_key: gpgKey }),
    });

    if (!encResp.ok) {
      const err = await encResp.json();
      throw new Error(err.error || `Encrypt failed: ${encResp.status}`);
    }

    const encData = await encResp.json();
    chunks = encData.chunks;
    metadata = encData.metadata;
    filename = encData.filename;
    timestamp = encData.timestamp;
  }

  onProgress({
    stage: "encrypted",
    chunks: chunks.length,
    totalChars: chunks.reduce((s, c) => s + c.length, 0),
  });

  // Upload via JS API
  const api = createAPI(provider, token);
  const title = `[DT] ${filename} ${timestamp}`;

  if (api.chunksInComments) {
    return await _pushGitFlic(api, repo, title, chunks, metadata, delay, onProgress);
  } else {
    return await _pushGitHub(api, repo, title, chunks, metadata, delay, onProgress);
  }
}

async function _pushGitHub(api, repo, title, chunks, metadataBody, delay, onProgress) {
  onProgress({ stage: "creating_issue", title });

  const issue = await api.createIssue(repo, title, chunks[0], [TRANSFER_LABEL]);
  const issueNumber = issue.number;
  const issueUrl = issue.html_url || "";

  onProgress({ stage: "issue_created", issueNumber, url: issueUrl });
  onProgress({ stage: "uploading", chunk: 0, total: chunks.length, chars: chunks[0].length });

  for (let i = 1; i < chunks.length; i++) {
    if (delay > 0) await sleep(delay);
    onProgress({ stage: "uploading", chunk: i, total: chunks.length, chars: chunks[i].length });
    await api.updateIssueBody(repo, issueNumber, chunks[i]);
  }

  onProgress({ stage: "posting_metadata" });
  await api.addIssueComment(repo, issueNumber, metadataBody);

  try {
    await api.addIssueLabels(repo, issueNumber, ["complete"]);
  } catch {}

  onProgress({ stage: "done", issueNumber, url: issueUrl, chunks: chunks.length });
  return { issueNumber, url: issueUrl };
}

async function _pushGitFlic(api, repo, title, chunks, metadataBody, delay, onProgress) {
  onProgress({ stage: "creating_issue", title });

  const issue = await api.createIssue(repo, title, metadataBody);
  const issueNumber = issue.number;
  const issueUrl = issue.html_url || "";

  onProgress({ stage: "issue_created", issueNumber, url: issueUrl });

  for (let i = 0; i < chunks.length; i++) {
    onProgress({ stage: "uploading", chunk: i, total: chunks.length, chars: chunks[i].length });
    await api.addIssueComment(repo, issueNumber, chunks[i]);
    if (delay > 0 && i < chunks.length - 1) await sleep(delay);
  }

  onProgress({ stage: "done", issueNumber, url: issueUrl, chunks: chunks.length });
  return { issueNumber, url: issueUrl };
}

function createAPI(provider, token) {
  if (provider === "gitflic") return new GitFlicAPI(token);
  return new GitHubAPI(token);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
