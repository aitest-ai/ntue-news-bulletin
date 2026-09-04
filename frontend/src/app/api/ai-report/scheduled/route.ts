import { NextRequest, NextResponse } from "next/server";
import { ADMIN_SESSION_COOKIE, getExpectedSessionToken } from "../../../../lib/auth";

export const runtime = "nodejs";
export const maxDuration = 60;

const REPO = "aitest-ai/ntue-news-bulletin";
const MODEL = "gemini-2.5-flash";

type FeedItem = {
  title?: string;
  source?: string;
  publisher?: string;
  publish_time?: string | null;
  risk_score?: number;
};

async function verifyGithubRun(token: string, runId: string, sha: string) {
  if (!token || !runId || !/^[0-9]+$/.test(runId) || !/^[0-9a-f]{40}$/i.test(sha)) return false;
  const response = await fetch(`https://api.github.com/repos/${REPO}/actions/runs/${encodeURIComponent(runId)}`, {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    cache: "no-store",
  });
  if (!response.ok) {
    console.error("scheduled workflow verification HTTP", response.status);
    return false;
  }
  const run = await response.json();
  return Boolean(
    String(run?.id) === runId &&
    run?.head_sha === sha &&
    run?.head_branch === "master" &&
    run?.repository?.full_name === REPO &&
    ["push", "schedule", "workflow_dispatch"].includes(run?.event)
  );
}

export async function POST(req: NextRequest) {
  try {
    const token = req.headers.get("x-github-workflow-token") || "";
    const runId = req.headers.get("x-github-run-id") || "";
    const sha = req.headers.get("x-github-sha") || "";
    if (!(await verifyGithubRun(token, runId, sha))) {
      return NextResponse.json({ error: "GitHub workflow verification failed" }, { status: 403 });
    }

    const body = await req.json();
    if (body?.session_only === true) {
      const sessionToken = await getExpectedSessionToken();
      if (!sessionToken) return NextResponse.json({ error: "ADMIN_PASSWORD 尚未設定" }, { status: 503 });
      return NextResponse.json({
        session_token: sessionToken,
        cookie_name: ADMIN_SESSION_COOKIE,
        generated_at: new Date().toISOString(),
      });
    }

    const apiKey = (process.env.GEMINI_API_KEY || "").trim();
    if (!apiKey) return NextResponse.json({ error: "GEMINI_API_KEY 尚未設定" }, { status: 503 });

    const days = Math.min(Math.max(Number(body?.days || 7), 1), 30);
    const items: FeedItem[] = Array.isArray(body?.items) ? body.items.slice(0, 120) : [];
    if (!items.length) return NextResponse.json({ error: "沒有可分析資料" }, { status: 400 });

    const prompt = `你是國立臺北教育大學校級輿情分析助理。以下資料已先通過與國北教大相關性的篩選。請產生主管用繁體中文輿情報告。\n\n原則：\n1. 不得因單一負面字詞就推論危機。\n2. 沒有需要注意的事件，就明確寫「本期無需特別關注」，不要硬湊風險。\n3. 不得杜撰人物、事件、內容或因果。\n4. 請將資料聚合成議題，不要逐則流水帳。\n5. watchlist 最多 5 項，沒有則空陣列。\n\n期間：最近 ${days} 天\n資料：${JSON.stringify(items)}`;

    const schema = {
      type: "object",
      properties: {
        overall: { type: "string" },
        immediate_action: { type: "string" },
        themes: { type: "array", items: { type: "string" }, minItems: 1, maxItems: 6 },
        risk_assessment: { type: "string" },
        recommendations: { type: "array", items: { type: "string" }, minItems: 1, maxItems: 6 },
        watchlist: { type: "array", items: { type: "string" }, maxItems: 5 },
      },
      required: ["overall", "immediate_action", "themes", "risk_assessment", "recommendations", "watchlist"],
    };

    const response = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:generateContent`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-goog-api-key": apiKey },
      body: JSON.stringify({
        contents: [{ role: "user", parts: [{ text: prompt }] }],
        generationConfig: {
          responseMimeType: "application/json",
          responseJsonSchema: schema,
          temperature: 0.15,
          maxOutputTokens: 1800,
          thinkingConfig: { thinkingBudget: 512 },
        },
      }),
    });

    if (!response.ok) {
      const detail = await response.text();
      console.error("scheduled Gemini API error", response.status, detail.slice(0, 800));
      return NextResponse.json({ error: `Gemini API 呼叫失敗（${response.status}）` }, { status: 502 });
    }

    const data = await response.json();
    const text = data?.candidates?.[0]?.content?.parts?.map((p: any) => p?.text || "").join("") || "";
    if (!text) return NextResponse.json({ error: "Gemini 未回傳可用分析" }, { status: 502 });
    const report = JSON.parse(text);
    return NextResponse.json({ report, meta: { model: MODEL, generated_at: new Date().toISOString() } });
  } catch (error: any) {
    console.error("scheduled AI report failed", error);
    return NextResponse.json({ error: error?.message || "產生排程報告失敗" }, { status: 500 });
  }
}
