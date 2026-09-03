export const ADMIN_SESSION_COOKIE = "ntue_admin_session";

export function normalizeSecret(value: string | undefined | null) {
  const raw = String(value || "").trim();
  if ((raw.startsWith('"') && raw.endsWith('"')) || (raw.startsWith("'") && raw.endsWith("'"))) {
    return raw.slice(1, -1).trim();
  }
  return raw;
}

async function sha256Hex(value: string) {
  const bytes = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest)).map(b => b.toString(16).padStart(2, "0")).join("");
}

export async function getExpectedSessionToken() {
  const password = normalizeSecret(process.env.ADMIN_PASSWORD);
  if (!password) return "";
  return sha256Hex(`ntue-opinion-monitor:${password}:session-v1`);
}

export async function isValidSession(token?: string | null) {
  if (!token) return false;
  const expected = await getExpectedSessionToken();
  return Boolean(expected) && token === expected;
}
