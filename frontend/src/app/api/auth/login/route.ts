import { NextRequest, NextResponse } from "next/server";
import { ADMIN_SESSION_COOKIE, getExpectedSessionToken, normalizeSecret } from "../../../../lib/auth";

export const runtime = "nodejs";

export async function POST(req: NextRequest) {
  const configured = normalizeSecret(process.env.ADMIN_PASSWORD);
  if (!configured) return NextResponse.json({ error: "ADMIN_PASSWORD 尚未設定" }, { status: 503 });

  const body = await req.json().catch(() => ({}));
  const supplied = normalizeSecret(String(body?.password || ""));
  if (supplied !== configured) return NextResponse.json({ error: "管理密碼錯誤" }, { status: 401 });

  const token = await getExpectedSessionToken();
  const res = NextResponse.json({ ok: true });
  res.cookies.set(ADMIN_SESSION_COOKIE, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 12,
  });
  return res;
}
