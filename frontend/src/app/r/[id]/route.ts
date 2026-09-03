import { createHash } from "crypto";
import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";

function shortId(url: string) {
  return createHash("sha1").update(url).digest("hex").slice(0, 8);
}

export async function GET(request: NextRequest, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  const origin = request.nextUrl.origin;

  try {
    const response = await fetch(`${origin}/data/news.json`, { cache: "no-store" });
    if (!response.ok) throw new Error(`news.json ${response.status}`);
    const feed = await response.json();
    const items = Array.isArray(feed?.items) ? feed.items : [];
    const match = items.find((item: { url?: string }) => {
      const url = typeof item?.url === "string" ? item.url : "";
      return url && shortId(url) === id;
    });

    if (match?.url) return NextResponse.redirect(match.url, 302);
  } catch (error) {
    console.error("short-link redirect failed", error);
  }

  return NextResponse.redirect(`${origin}/`, 302);
}
