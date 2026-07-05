import { NextRequest, NextResponse } from "next/server";
import nodemailer from "nodemailer";

// Shared secret key to protect this endpoint from public abuse.
// We use the system's default admin password as the secret key.
const SHARED_SECRET = "ntue1234";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { 
      secret, 
      smtp_host, 
      smtp_port, 
      smtp_username, 
      smtp_password, 
      to, 
      subject, 
      html, 
      text 
    } = body;

    // Validate request auth
    if (secret !== SHARED_SECRET) {
      return NextResponse.json({ error: "Unauthorized access key" }, { status: 401 });
    }

    if (!smtp_username || !smtp_password || !to) {
      return NextResponse.json({ error: "Missing required SMTP configurations or recipient email" }, { status: 400 });
    }

    console.log(`[Relay] Attempting to send email to ${to} via SMTP ${smtp_host}:${smtp_port} using user ${smtp_username}...`);

    // Create nodemailer transporter
    const transporter = nodemailer.createTransport({
      host: smtp_host || "smtp.gmail.com",
      port: Number(smtp_port) || 587,
      secure: Number(smtp_port) === 465, // true for 465, false for 587
      auth: {
        user: smtp_username,
        pass: smtp_password,
      },
      tls: {
        rejectUnauthorized: false
      }
    });

    // Send mail
    const info = await transporter.sendMail({
      from: `國北教大新聞公佈欄 <${smtp_username}>`,
      to,
      subject,
      text,
      html,
    });

    console.log(`[Relay] Email successfully sent: ${info.messageId}`);
    return NextResponse.json({ success: true, messageId: info.messageId });
  } catch (err: any) {
    console.error("[Relay] SMTP send error:", err);
    return NextResponse.json({ 
      success: false, 
      error: err.message || "Failed to send email" 
    }, { status: 500 });
  }
}
