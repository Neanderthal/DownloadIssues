/**
 * Pull orchestration: fetch chunks via JS API → decrypt via local server.
 *
 * Flow:
 *   1. JS fetches issue metadata + hex chunks from GitHub/GitFlic
 *   2. POST /api/decrypt → server decrypts and extracts
 */

import { GitHubAPI } from "./github-api.js";
import { GitFlicAPI } from "./gitflic-api.js";
import {
  parseMetadata,
  findMetadataInComments,
  computeMD5,
  isDataTransferIssue,
} from "./metadata.js";

const SERVER = "http://127.0.0.1:9741/api";

/**
 * List data-transfer issues from a git platform.
 *
 * @param {object} opts
 * @param {string} opts.provider - "github" or "gitflic"
 * @param {string} opts.token - API token
 * @param {string} opts.repo - "owner/repo"
 * @returns {object[]} normalized issue list
 */
export async function listIssues(opts) {
  const { provider, token, repo } = opts;
  const api = createAPI(provider, token);
  const issues = await api.fetchOpenIssues(repo);
  return issues.filter(isDataTransferIssue);
}

/**
 * Pull (download + decrypt) a single issue.
 *
 * @param {object} opts
 * @param {number} opts.issueNumber
 * @param {string} opts.provider
 * @param {string} opts.token
 * @param {string} opts.repo
 * @param {string} [opts.outputDir]
 * @param {boolean} [opts.force=false]
 * @param {function} [opts.onProgress]
 */
export async function pull(opts) {
  const {
    issueNumber,
    provider,
    token,
    repo,
    outputDir,
    force = false,
    onProgress = () => {},
  } = opts;

  const api = createAPI(provider, token);

  // Step 1: Get metadata
  onProgress({ stage: "fetching_metadata", issue: issueNumber });

  let metadata = null;
  try {
    metadata = await _getMetadata(api, repo, issueNumber);
  } catch (e) {
    onProgress({ stage: "warning", message: `Metadata error: ${e.message}` });
  }

  if (metadata) {
    onProgress({
      stage: "metadata",
      filename: metadata.filename || "?",
      totalParts: metadata.total_parts || "?",
      archiveMd5: metadata.archive_md5 || "?",
    });
  } else {
    onProgress({ stage: "metadata", filename: null, message: "No metadata (legacy)" });
  }

  // Step 2: Fetch + verify chunks via JS
  onProgress({ stage: "fetching_chunks" });

  const { chunks: rawChunks, body } = await api.fetchChunks(repo, issueNumber);
  let chunks;
  let verified = false;

  if (metadata && metadata.parts) {
    const result = matchChunksByMD5(rawChunks, metadata.parts);
    chunks = result.chunks;
    verified = result.verified;

    if (!verified && !force) {
      onProgress({
        stage: "error",
        message: `Missing ${result.missing.length} chunk(s): ${result.missing.join(", ")}`,
      });
      throw new Error("MD5 verification failed — use force to proceed");
    }
  } else {
    // Deduplicate
    const seen = new Set();
    chunks = [];
    for (const chunk of rawChunks) {
      if (!seen.has(chunk)) {
        seen.add(chunk);
        chunks.push(chunk);
      }
    }
  }

  if (!chunks.length) {
    onProgress({ stage: "error", message: "No hex data found" });
    throw new Error("No hex data found in this issue");
  }

  const totalChars = chunks.reduce((s, c) => s + c.length, 0);
  onProgress({ stage: "chunks_fetched", count: chunks.length, totalChars, verified });

  // Step 3: Decrypt via local server
  onProgress({ stage: "decrypting" });

  const filename = metadata?.filename || `issue_${issueNumber}`;
  const decResp = await fetch(`${SERVER}/decrypt`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      hex_chunks: chunks,
      output_dir: outputDir,
      filename,
    }),
  });

  if (!decResp.ok) {
    const err = await decResp.json();
    throw new Error(err.error || `Decrypt failed: ${decResp.status}`);
  }

  const decData = await decResp.json();

  onProgress({
    stage: "done",
    outputPath: decData.output_path,
    filename: decData.filename,
    chunks: chunks.length,
  });

  return decData;
}

/**
 * Get metadata from an issue (provider-aware).
 */
async function _getMetadata(api, repo, issueNumber) {
  if (api.chunksInComments) {
    // GitFlic: metadata is in the issue body
    const { body } = await api.fetchChunks(repo, issueNumber);
    if (body) return parseMetadata(body);
    return null;
  } else {
    // GitHub: metadata is in the first comment
    const comments = await api.getIssueComments(repo, issueNumber);
    return findMetadataInComments(comments);
  }
}

/**
 * Match raw chunks to metadata parts by MD5.
 */
function matchChunksByMD5(rawChunks, parts) {
  const md5ToChunk = {};
  for (const chunk of rawChunks) {
    const md5 = computeMD5(chunk);
    if (!(md5 in md5ToChunk)) md5ToChunk[md5] = chunk;
  }

  const chunks = [];
  const missing = [];

  for (const part of parts) {
    const expectedMd5 = part.md5 || "";
    if (expectedMd5 in md5ToChunk) {
      chunks.push(md5ToChunk[expectedMd5]);
    } else {
      missing.push(part.suffix || "?");
    }
  }

  return { chunks, missing, verified: missing.length === 0 };
}

function createAPI(provider, token) {
  if (provider === "gitflic") return new GitFlicAPI(token);
  return new GitHubAPI(token);
}
