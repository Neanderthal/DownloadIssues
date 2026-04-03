/**
 * Metadata parsing and MD5 utilities.
 * Mirrors lib/metadata.py and lib/integrity.py
 */

const TITLE_PREFIX = "[DT]";
const TRANSFER_LABEL = "data-transfer";

/**
 * Parse metadata JSON from a comment/issue body.
 */
export function parseMetadata(text) {
  const trimmed = (text || "").trim();

  // Plain JSON (new format)
  if (trimmed.startsWith("{")) {
    try {
      const data = JSON.parse(trimmed);
      if (data && typeof data === "object" && data.parts) return data;
    } catch {}
  }

  // Legacy DT-METADATA wrapper
  const match = trimmed.match(/<!--\s*DT-METADATA\s*([\s\S]*?)\s*DT-METADATA\s*-->/);
  if (match) {
    try {
      return JSON.parse(match[1]);
    } catch {}
  }

  return null;
}

/**
 * Find metadata in an array of comment objects.
 */
export function findMetadataInComments(comments) {
  if (!comments || !comments.length) return null;

  // Check first comment (expected location)
  const first = parseMetadata(comments[0].body || "");
  if (first) return first;

  // Scan remaining
  for (let i = 1; i < comments.length; i++) {
    const meta = parseMetadata(comments[i].body || "");
    if (meta) return meta;
  }

  return null;
}

/**
 * Compute MD5 of a string (ASCII-encoded).
 * Uses SubtleCrypto — returns hex string.
 *
 * Note: MD5 is not in SubtleCrypto spec. We use a pure JS implementation.
 */
export function computeMD5(str) {
  return md5(str);
}

/**
 * Check if an issue is a data-transfer issue.
 */
export function isDataTransferIssue(issue) {
  const title = issue.title || "";
  const labels = (issue.labels || []).map((l) => l.name || l);
  return title.startsWith(TITLE_PREFIX) || labels.includes(TRANSFER_LABEL);
}

// -- MD5 implementation (Joseph Myers, public domain) --
// Proven correct, widely used in JS projects.

function md5(string) {
  const bytes = new TextEncoder().encode(string);
  return md5bytes(bytes);
}

function md5bytes(bytes) {
  const n = bytes.length;
  let state = [0x67452301, 0xefcdab89, 0x98badcfe, 0x10325476];

  // Pre-processing: pad to 64-byte blocks
  const bitLen = n * 8;
  const padLen = (n % 64 < 56) ? 56 - (n % 64) : 120 - (n % 64);
  const padded = new Uint8Array(n + padLen + 8);
  padded.set(bytes);
  padded[n] = 0x80;
  // Length in bits as little-endian 64-bit
  const dv = new DataView(padded.buffer);
  dv.setUint32(padded.length - 8, bitLen >>> 0, true);
  dv.setUint32(padded.length - 4, 0, true);

  // Process each 64-byte block
  for (let offset = 0; offset < padded.length; offset += 64) {
    const w = new Uint32Array(16);
    for (let j = 0; j < 16; j++) {
      w[j] = dv.getUint32(offset + j * 4, true);
    }

    let [a, b, c, d] = state;

    // Round 1
    for (let i = 0; i < 16; i++) {
      const f = (b & c) | (~b & d);
      const g = i;
      const tmp = d; d = c; c = b;
      b = (b + rotl((a + f + K[i] + w[g]) >>> 0, S1[i & 3])) >>> 0;
      a = tmp;
    }
    // Round 2
    for (let i = 16; i < 32; i++) {
      const f = (d & b) | (~d & c);
      const g = (5 * (i - 16) + 1) % 16;
      const tmp = d; d = c; c = b;
      b = (b + rotl((a + f + K[i] + w[g]) >>> 0, S2[(i - 16) & 3])) >>> 0;
      a = tmp;
    }
    // Round 3
    for (let i = 32; i < 48; i++) {
      const f = b ^ c ^ d;
      const g = (3 * (i - 32) + 5) % 16;
      const tmp = d; d = c; c = b;
      b = (b + rotl((a + f + K[i] + w[g]) >>> 0, S3[(i - 32) & 3])) >>> 0;
      a = tmp;
    }
    // Round 4
    for (let i = 48; i < 64; i++) {
      const f = c ^ (b | ~d);
      const g = (7 * (i - 48)) % 16;
      const tmp = d; d = c; c = b;
      b = (b + rotl((a + f + K[i] + w[g]) >>> 0, S4[(i - 48) & 3])) >>> 0;
      a = tmp;
    }

    state[0] = (state[0] + a) >>> 0;
    state[1] = (state[1] + b) >>> 0;
    state[2] = (state[2] + c) >>> 0;
    state[3] = (state[3] + d) >>> 0;
  }

  // Convert to hex (little-endian)
  let hex = "";
  for (const s of state) {
    for (let j = 0; j < 4; j++) {
      hex += ((s >>> (j * 8)) & 0xff).toString(16).padStart(2, "0");
    }
  }
  return hex;
}

function rotl(x, n) {
  return ((x << n) | (x >>> (32 - n))) >>> 0;
}

// Per-round shift amounts
const S1 = [7, 12, 17, 22];
const S2 = [5, 9, 14, 20];
const S3 = [4, 11, 16, 23];
const S4 = [6, 10, 15, 21];

// Pre-computed T table (floor(2^32 * abs(sin(i+1))))
const K = new Uint32Array([
  0xd76aa478,0xe8c7b756,0x242070db,0xc1bdceee,0xf57c0faf,0x4787c62a,0xa8304613,0xfd469501,
  0x698098d8,0x8b44f7af,0xffff5bb1,0x895cd7be,0x6b901122,0xfd987193,0xa679438e,0x49b40821,
  0xf61e2562,0xc040b340,0x265e5a51,0xe9b6c7aa,0xd62f105d,0x02441453,0xd8a1e681,0xe7d3fbc8,
  0x21e1cde6,0xc33707d6,0xf4d50d87,0x455a14ed,0xa9e3e905,0xfcefa3f8,0x676f02d9,0x8d2a4c8a,
  0xfffa3942,0x8771f681,0x6d9d6122,0xfde5380c,0xa4beea44,0x4bdecfa9,0xf6bb4b60,0xbebfbc70,
  0x289b7ec6,0xeaa127fa,0xd4ef3085,0x04881d05,0xd9d4d039,0xe6db99e5,0x1fa27cf8,0xc4ac5665,
  0xf4292244,0x432aff97,0xab9423a7,0xfc93a039,0x655b59c3,0x8f0ccc92,0xffeff47d,0x85845dd1,
  0x6fa87e4f,0xfe2ce6e0,0xa3014314,0x4e0811a1,0xf7537e82,0xbd3af235,0x2ad7d2bb,0xeb86d391,
]);
