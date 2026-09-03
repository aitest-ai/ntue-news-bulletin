import { NextRequest, NextResponse } from "next/server";
import nodemailer from "nodemailer";
import { ADMIN_SESSION_COOKIE, isValidSession } from "../../../lib/auth";

export async function POST(req: NextRequest) {
  const session = req.cookies.get(ADMIN_SESSION_COOKIE)?.value;
  if (!(await isValidSession(session))) {
    return NextResponse.json({ error: "登入已逾時，請重新登入" }, { status: 401 });
  }

  try {
    const body = await req.json();
    const to = Array.isArray(body?.to) ? body.to : [body?.to].filter(Boolean);
    const subject = String(body?.subject || "國北教大輿情通知");
    const html = String(body?.html || "");
    const text = String(body?.text || "");

    const smtpHost = process.env.SMTP_HOST || "smtp.gmail.com";
    const smtpPort = Number(process.env.SMTP_PORT || 587);
    const smtpUsername = process.env.SMTP_USERNAME || "";
    const smtpPassword = process.env.SMTP_PASSWORD || "";

    if (!smtpUsername || !smtpPassword || to.length === 0) {
      return NextResponse.json({ error: "SMTP 尚未設定或沒有收件者" }, { status: 503 });
    }

    const transporter = nodemailer.createTransport({
      host: smtpHost,
      port: smtpPort,
      secure: smtpPort === 465,
      auth: { user: smtpUsername, pass: smtpPassword },
    });

    const info = await transporter.sendMail({
      from: `國北教大輿情監測 <${smtpUsername}>`,
      to,
      subject,
      text,
      html,
    });

    return NextResponse.json({ success: true, messageId: info.messageId });
  } catch (err: any) {
    console.error("SMTP send error", err);
    return NextResponse.json({ error: err?.message || "寄信失敗" }, { status: 500 });
  }
}
