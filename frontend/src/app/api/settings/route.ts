import { NextRequest, NextResponse } from "next/server";
import { ADMIN_SESSION_COOKIE, isValidSession } from "../../../lib/auth";

const REPO = "aitest-ai/ntue-news-bulletin";
const PATH = "frontend/public/data/settings.json";

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
    const recipients = Array.isArray(body?.recipients)
      ? body.recipients.map((x: unknown) => String(x).trim()).filter(Boolean)
      : [];
    const schedules = Array.isArray(body?.schedules)
      ? body.schedules.map((x: unknown) => String(x).trim()).filter((x: string) => /^([01]\d|2[0-3]):[0-5]\d$/.test(x))
      : [];

    const settings = {
      email_enabled: Boolean(body?.email_enabled),
      recipients,
      schedules: Array.from(new Set(schedules)).sort(),
      timezone: "Asia/Taipei",
      report_days: Math.min(Math.max(Number(body?.report_days || 1), 1), 30),
      include_latest_items: Math.min(Math.max(Number(body?.include_latest_items || 20), 5), 100),
      subject_prefix: String(body?.subject_prefix || "【國北教大輿情快報】").slice(0, 80),
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
        message: "config: update bulletin delivery settings",
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
