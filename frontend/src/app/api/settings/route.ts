import { NextRequest, NextResponse } from "next/server";
import { ADMIN_SESSION_COOKIE, isValidSession } from "../../../lib/auth";

const REPO = "aitest-ai/ntue-news-bulletin";
const PATH = "frontend/public/data/settings.json";
const TIME_RE = /^([01]\d|2[0-3]):[0-5]\d$/;

function cleanEmails(value: unknown) {
  if (!Array.isArray(value)) return [];
  return Array.from(new Set(value.map((x) => String(x).trim()).filter(Boolean))).slice(0, 100);
}

function cleanProfiles(value: unknown) {
  if (!Array.isArray(value)) return [];
  return value.slice(0, 30).map((raw: any, index: number) => {
    const id = String(raw?.id || `profile-${Date.now()}-${index}`).replace(/[^a-zA-Z0-9_-]/g, "").slice(0, 80) || `profile-${index + 1}`;
    const time = TIME_RE.test(String(raw?.time || "")) ? String(raw.time) : "08:00";
    return {
      id,
      name: String(raw?.name || `推送任務 ${index + 1}`).trim().slice(0, 80),
      enabled: Boolean(raw?.enabled),
      time,
      report_days: 1,
      include_latest_items: 100,
      recipients: cleanEmails(raw?.recipients),
      subject_prefix: String(raw?.subject_prefix || "【國北教大輿情快報】").slice(0, 80),
      sender_name: String(raw?.sender_name || "").trim().slice(0, 80),
      sender_email: String(raw?.sender_email || "").trim().slice(0, 160),
      exclude_holidays: Boolean(raw?.exclude_holidays),
      channel: "email",
    };
  });
}

export async function POST(req: NextRequest) {
  const token = req.cookies.get(ADMIN_SESSION_COOKIE)?.value;
  if (!(await isValidSession(token))) {
    return NextResponse.json({ error: "登入已逾時，請重新登入" }, { status: 401 });
  }

  const githubToken = process.env.GITHUB_PAT || process.env.GITHUB_TOKEN;
  if (!githubToken) {
    return NextResponse.json({ error: "尚未設定 GITHUB_PAT，無法儲存排程設定" }, { status: 503 });
  }

  try {
    const body = await req.json();
    const profiles = cleanProfiles(body?.delivery_profiles);

    const settings = {
      timezone: "Asia/Taipei",
      delivery_profiles: profiles,
      email_enabled: profiles.some((p) => p.enabled),
      recipients: Array.from(new Set(profiles.flatMap((p) => p.recipients))),
      schedules: Array.from(new Set(profiles.filter((p) => p.enabled).map((p) => p.time))).sort(),
      report_days: 1,
      include_latest_items: 100,
      subject_prefix: profiles[0]?.subject_prefix || "【國北教大輿情快報】",
    };

    const headers = {
      Authorization: `Bearer ${githubToken}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "Content-Type": "application/json",
    };

    const current = await fetch(`https://api.github.com/repos/${REPO}/contents/${PATH}`, { headers, cache: "no-store" });
    if (!current.ok) {
      return NextResponse.json({ error: `讀取設定檔失敗（GitHub ${current.status}）` }, { status: 502 });
    }
    const currentJson = await current.json();

    const save = await fetch(`https://api.github.com/repos/${REPO}/contents/${PATH}`, {
      method: "PUT",
      headers,
      body: JSON.stringify({
        message: "config: update delivery profiles",
        content: Buffer.from(JSON.stringify(settings, null, 2) + "\n", "utf8").toString("base64"),
        sha: currentJson.sha,
        branch: "master",
      }),
    });

    if (!save.ok) {
      const detail = await save.text();
      console.error("GitHub settings save failed", save.status, detail.slice(0, 800));
      return NextResponse.json({ error: `儲存設定失敗（GitHub ${save.status}）` }, { status: 502 });
    }

    return NextResponse.json({ success: true, settings });
  } catch (error: any) {
    return NextResponse.json({ error: error?.message || "儲存設定失敗" }, { status: 500 });
  }
}
