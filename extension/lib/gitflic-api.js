/**
 * GitFlic REST API client for data transfer operations.
 *
 * Mirrors lib/gitflic_api.py — chunks in comments, metadata in issue body.
 */

const GITFLIC_API = "https://api.gitflic.ru";

export class GitFlicAPI {
  constructor(token) {
    this.token = token;
    this.chunksInComments = true;
  }

  _headers() {
    const h = { "Content-Type": "application/json" };
    if (this.token) h.Authorization = `token ${this.token}`;
    return h;
  }

  _base(repo) {
    const [owner, project] = repo.split("/", 2);
    return `${GITFLIC_API}/project/${owner}/${project}`;
  }

  _normalizeIssue(issue) {
    const labelsRaw = issue.labels || [];
    const labels = labelsRaw.map((l) => ({
      name: l.value || l.name || "",
    }));

    return {
      number: issue.localId || issue.id,
      title: issue.title || "",
      body: issue.description || "",
      labels,
      updated_at: issue.updatedAt || "",
      created_at: issue.createdAt || "",
    };
  }

  async fetchOpenIssues(repo) {
    const base = this._base(repo);
    const issues = [];
    let page = 0;

    while (true) {
      const params = new URLSearchParams({ page, size: 50 });
      let resp;
      try {
        resp = await fetch(`${base}/issue?${params}`, {
          headers: this._headers(),
        });
      } catch (e) {
        console.error("Error fetching issues:", e);
        return issues;
      }
      if (!resp.ok) return issues;

      const data = await resp.json();
      let batch;

      if (Array.isArray(data)) {
        batch = data;
      } else if (data._embedded) {
        batch =
          data._embedded.issueModelList ||
          data._embedded.issueList ||
          data._embedded.issues ||
          data._embedded.items ||
          [];
      } else {
        break;
      }

      if (!batch.length) break;

      for (const issue of batch) {
        const status = issue.status || {};
        const statusId = typeof status === "object" ? status.id || "" : status;
        if (statusId === "OPEN" || statusId === "IN_PROGRESS") {
          issues.push(this._normalizeIssue(issue));
        }
      }

      if (data.page) {
        if (page + 1 >= (data.page.totalPages || 1)) break;
      } else if (batch.length < 50) {
        break;
      }

      page++;
    }

    return issues;
  }

  async createIssue(repo, title, body) {
    const base = this._base(repo);
    const resp = await fetch(`${base}/issue`, {
      method: "POST",
      headers: this._headers(),
      body: JSON.stringify({
        title,
        description: body,
        status: { id: "OPEN" },
        assignedUsers: [],
      }),
    });
    if (!resp.ok) throw new Error(`Create issue failed: ${resp.status}`);
    const raw = await resp.json();
    const result = this._normalizeIssue(raw);

    const [owner, project] = repo.split("/", 2);
    result.html_url = `https://gitflic.ru/project/${owner}/${project}/issue/${result.number}`;
    return result;
  }

  async updateIssueBody(repo, issueNumber, body) {
    const base = this._base(repo);
    const resp = await fetch(`${base}/issue/${issueNumber}/edit`, {
      method: "PUT",
      headers: this._headers(),
      body: JSON.stringify({ description: body }),
    });
    if (!resp.ok) throw new Error(`Update issue failed: ${resp.status}`);
    return this._normalizeIssue(await resp.json());
  }

  async addIssueComment(repo, issueNumber, body) {
    const base = this._base(repo);
    const resp = await fetch(`${base}/issue-discussion/${issueNumber}/create`, {
      method: "POST",
      headers: this._headers(),
      body: JSON.stringify({ note: body }),
    });
    if (!resp.ok) throw new Error(`Add comment failed: ${resp.status}`);
    const raw = await resp.json();
    return { id: raw.id, body: raw.message || raw.note || "" };
  }

  async getIssueComments(repo, issueNumber) {
    const base = this._base(repo);
    const comments = [];
    let page = 0;

    while (true) {
      const params = new URLSearchParams({ page, size: 50 });
      let resp;
      try {
        resp = await fetch(`${base}/issue-discussion/${issueNumber}?${params}`, {
          headers: this._headers(),
        });
      } catch (e) {
        console.error("Error fetching comments:", e);
        return comments;
      }
      if (!resp.ok) return comments;

      const data = await resp.json();
      let batch;

      if (Array.isArray(data)) {
        batch = data;
      } else if (data._embedded) {
        batch =
          data._embedded.IssueDiscussionList ||
          data._embedded.issueDiscussionList ||
          data._embedded.discussions ||
          data._embedded.items ||
          [];
      } else {
        break;
      }

      if (!batch.length) break;

      for (const c of batch) {
        comments.push({
          id: c.id,
          body: c.message || c.note || "",
          created_at: c.createdAt || "",
        });
      }

      if (data.page) {
        if (page + 1 >= (data.page.totalPages || 1)) break;
      } else if (batch.length < 50) {
        break;
      }

      page++;
    }

    return comments;
  }

  async addIssueLabels(_repo, _issueNumber, _labels) {
    // GitFlic has no REST API for labels — silently skip.
  }

  async closeIssue(repo, issueNumber) {
    const base = this._base(repo);
    const resp = await fetch(`${base}/issue/${issueNumber}/edit`, {
      method: "PUT",
      headers: this._headers(),
      body: JSON.stringify({ status: { id: "CLOSED" } }),
    });
    if (!resp.ok) throw new Error(`Close issue failed: ${resp.status}`);
    return this._normalizeIssue(await resp.json());
  }

  /**
   * Fetch hex chunks from issue comments + issue body.
   * Returns { chunks: string[], body: string }
   */
  async fetchChunks(repo, issueNumber) {
    const base = this._base(repo);

    // Get issue body (metadata)
    const issueResp = await fetch(`${base}/issue/${issueNumber}`, {
      headers: this._headers(),
    });
    if (!issueResp.ok) throw new Error(`Fetch issue failed: ${issueResp.status}`);
    const issueData = await issueResp.json();
    const issueBody = issueData.description || "";

    // Get comments (hex chunks)
    const comments = await this.getIssueComments(repo, issueNumber);

    const chunks = [];
    for (const comment of comments) {
      const body = comment.body || "";
      if (body) {
        const hex = cleanHexData(body);
        if (hex) chunks.push(hex);
      }
    }

    return { chunks, body: issueBody };
  }
}

/**
 * Strip markdown/non-hex characters from text.
 */
function cleanHexData(text) {
  const lines = text.split("\n");
  const hexLines = [];

  for (const line of lines) {
    const stripped = line.trim();
    if (!stripped) continue;
    if (/^(#|```|---|\*|<!--|DT-METADATA)/.test(stripped)) continue;
    const cleaned = line.replace(/[^0-9a-fA-F]/g, "");
    if (cleaned) hexLines.push(cleaned);
  }

  return hexLines.join("");
}
