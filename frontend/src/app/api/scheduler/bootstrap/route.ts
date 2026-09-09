import { NextRequest, NextResponse } from "next/server";
import { start } from "workflow/api";
import { profileDeliveryWakeWorkflow } from "@/workflows/profile-delivery-wake";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const REPOSITORY = "aitest-ai/ntue-news-bulletin";
const SETTINGS_PATH = "frontend/public/data/settings.json";
const TIME_RE = /^(?:[01]\d|2[0-3]):[0-5]\d$/;
const PREWAKE_MINUTES = 18;

type Profile = {
  id?: string;
  enabled?: boolean;
  time?: string;
  recipients?: unknown[];
};

function taipeiDateString(now = new Date()) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Taipei",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const value = (type: string) => parts.find((part) => part.type === type)?.value || "";
  return `${value("year")}-${value("month")}-${value("day")}`;
}

function wakeAtIso(localDate: string, slot: string) {
  const target = new Date(`${localDate}T${slot}:00+08:00`);
  return new Date(target.getTime() - PREWAKE_MINUTES * 60_000).toISOString();
}

async function readSettingsFromGitHub() {
  const token = process.env.GITHUB_PAT || process.env.GITHUB_TOKEN;
  if (!token) throw new Error("GITHUB_PAT is unavailable to scheduler bootstrap");

  const response = await fetch(
    `https://api.github.com/repos/${REPOSITORY}/contents/${SETTINGS_PATH}?ref=master`,
    {
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "NTUE-Vercel-Durable-Scheduler/1.0",
      },
      cache: "no-store",
    },
  );
  if (!response.ok) {
    throw new Error(`Unable to read scheduler settings from GitHub (${response.status})`);
  }
  const payload = await response.json();
  const text = Buffer.from(String(payload.content || ""), "base64").toString("utf8");
  return JSON.parse(text) as { delivery_profiles?: Profile[] };
}

export async function GET(req: NextRequest) {
  // Vercel Cron identifies itself with this UA. The route only starts idempotent
  // wake workflows; actual email deduplication remains in GitHub delivery state.
  const userAgent = req.headers.get("user-agent") || "";
  if (!userAgent.includes("vercel-cron/1.0")) {
    return NextResponse.json({ error: "scheduler bootstrap only" }, { status: 403 });
  }

  try {
    const settings = await readSettingsFromGitHub();
    const localDate = taipeiDateString();
    const profiles = Array.isArray(settings.delivery_profiles) ? settings.delivery_profiles : [];
    const runs: Array<{ profileId: string; slot: string; runId: string; wakeAt: string }> = [];

    for (const raw of profiles) {
      const profileId = String(raw?.id || "").trim();
      const slot = String(raw?.time || "").trim();
      const recipients = Array.isArray(raw?.recipients) ? raw.recipients.filter(Boolean) : [];
      if (!profileId || raw?.enabled !== true || !TIME_RE.test(slot) || recipients.length === 0) continue;

      const wakeAt = wakeAtIso(localDate, slot);
      const run = await start(profileDeliveryWakeWorkflow, [profileId, slot, localDate, wakeAt]);
      runs.push({ profileId, slot, runId: run.runId, wakeAt });
    }

    console.log(`[scheduler-bootstrap] date=${localDate} durable_wakes=${runs.length}`);
    return NextResponse.json({ success: true, localDate, runs });
  } catch (error: any) {
    console.error("[scheduler-bootstrap] failed", error);
    return NextResponse.json({ error: error?.message || "scheduler bootstrap failed" }, { status: 500 });
  }
}
