/**
 * GitHub REST + GraphQL API client for data transfer operations.
 *
 * Mirrors lib/github_api.py — chunks live in edit history, metadata in comments.
 */

const GITHUB_API = "https://api.github.com";
const GRAPHQL_API = "https://api.github.com/graphql";

export class GitHubAPI {
  constructor(token) {
    this.token = token;
    this.chunksInComments = false;
  }

  _headers() {
    const h = {
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
    };
    if (this.token) h.Authorization = `Bearer ${this.token}`;
    return h;
  }

  async fetchOpenIssues(repo, labels) {
    const issues = [];
    let page = 1;
    while (true) {
      const params = new URLSearchParams({ state: "open", page, per_page: 100 });
      if (labels) params.set("labels", labels);

      const resp = await fetch(`${GITHUB_API}/repos/${repo}/issues?${params}`, {
        headers: this._headers(),
      });
      if (!resp.ok) break;
      const batch = await resp.json();
      if (!batch.length) break;
      issues.push(...batch.filter((i) => !i.pull_request));
      if (batch.length < 100) break;
      page++;
    }
    return issues;
  }

  async createIssue(repo, title, body, labels) {
    const payload = { title, body };
    if (labels) payload.labels = labels;
    const resp = await fetch(`${GITHUB_API}/repos/${repo}/issues`, {
      method: "POST",
      headers: { ...this._headers(), "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!resp.ok) throw new Error(`Create issue failed: ${resp.status}`);
    return resp.json();
  }

  async updateIssueBody(repo, issueNumber, body) {
    const resp = await fetch(`${GITHUB_API}/repos/${repo}/issues/${issueNumber}`, {
      method: "PATCH",
      headers: { ...this._headers(), "Content-Type": "application/json" },
      body: JSON.stringify({ body }),
    });
    if (!resp.ok) throw new Error(`Update issue failed: ${resp.status}`);
    return resp.json();
  }

  async addIssueComment(repo, issueNumber, body) {
    const resp = await fetch(
      `${GITHUB_API}/repos/${repo}/issues/${issueNumber}/comments`,
      {
        method: "POST",
        headers: { ...this._headers(), "Content-Type": "application/json" },
        body: JSON.stringify({ body }),
      }
    );
    if (!resp.ok) throw new Error(`Add comment failed: ${resp.status}`);
    return resp.json();
  }

  async getIssueComments(repo, issueNumber) {
    const resp = await fetch(
      `${GITHUB_API}/repos/${repo}/issues/${issueNumber}/comments`,
      { headers: this._headers() }
    );
    if (!resp.ok) throw new Error(`Get comments failed: ${resp.status}`);
    return resp.json();
  }

  async addIssueLabels(repo, issueNumber, labels) {
    const resp = await fetch(
      `${GITHUB_API}/repos/${repo}/issues/${issueNumber}/labels`,
      {
        method: "POST",
        headers: { ...this._headers(), "Content-Type": "application/json" },
        body: JSON.stringify({ labels }),
      }
    );
    if (!resp.ok) throw new Error(`Add labels failed: ${resp.status}`);
  }

  async closeIssue(repo, issueNumber) {
    const resp = await fetch(`${GITHUB_API}/repos/${repo}/issues/${issueNumber}`, {
      method: "PATCH",
      headers: { ...this._headers(), "Content-Type": "application/json" },
      body: JSON.stringify({ state: "closed" }),
    });
    if (!resp.ok) throw new Error(`Close issue failed: ${resp.status}`);
    return resp.json();
  }

  /**
   * Fetch hex chunks from issue edit history via GraphQL.
   * Returns { chunks: string[], body: string }
   */
  async fetchChunks(repo, issueNumber) {
    const [owner, name] = repo.split("/");
    const query = `
      query ($owner: String!, $name: String!, $number: Int!, $after: String) {
        repository(owner: $owner, name: $name) {
          issue(number: $number) {
            body
            userContentEdits(first: 50, after: $after) {
              totalCount
              pageInfo { hasNextPage endCursor }
              nodes { diff }
            }
          }
        }
      }
    `;

    const allEdits = [];
    let issueBody = null;
    let after = null;

    while (true) {
      const resp = await fetch(GRAPHQL_API, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${this.token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          query,
          variables: { owner, name, number: issueNumber, after },
        }),
      });
      const result = await resp.json();
      const issue = result?.data?.repository?.issue;
      if (!issue) break;

      if (issueBody === null) issueBody = issue.body || "";
      const edits = issue.userContentEdits || {};
      allEdits.push(...(edits.nodes || []));

      if (edits.pageInfo?.hasNextPage) {
        after = edits.pageInfo.endCursor;
      } else {
        break;
      }
    }

    const chunks = [];
    for (const edit of allEdits) {
      if (edit.diff) {
        const hex = cleanHexData(edit.diff);
        if (hex) chunks.push(hex);
      }
    }
    if (issueBody) {
      const bodyHex = cleanHexData(issueBody);
      if (bodyHex) chunks.push(bodyHex);
    }

    return { chunks, body: issueBody };
  }
}

/**
 * Strip markdown/non-hex characters from text.
 * Mirrors lib/crypto.py clean_hex_data().
 */
export function cleanHexData(text) {
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
