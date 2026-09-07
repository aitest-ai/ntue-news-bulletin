#!/usr/bin/env python3
import base64
import html
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import send_scheduled_digest as digest  # noqa: E402

_rendered_pdf_bytes = None


def _workflow_headers():
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "x-github-run-id": os.getenv("GITHUB_RUN_ID", "").strip(),
        "x-github-sha": os.getenv("GITHUB_SHA", "").strip(),
        "x-github-workflow-token": os.getenv("GITHUB_WORKFLOW_TOKEN", "").strip(),
        "User-Agent": "NTUE-GitHub-Actions-Scheduled-Report/7.0",
    }


def _get_browser_session(base_url):
    endpoint = f"{base_url}/api/ai-report/scheduled"
    payload = json.dumps({"session_only": True}).encode("utf-8")
    last_error = None
    for attempt in range(1, 9):
        try:
            req = urllib.request.Request(endpoint, data=payload, headers=_workflow_headers(), method="POST")
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            token = str(data.get("session_token") or "").strip()
            cookie_name = str(data.get("cookie_name") or "").strip()
            if token and cookie_name:
                print(f"[digest] scheduled browser session granted; attempt={attempt}")
                return cookie_name, token
            last_error = "scheduled session response incomplete"
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            last_error = f"HTTP {exc.code}: {detail[:300]}"
        except Exception as exc:
            last_error = str(exc)
        if attempt < 8:
            print(f"[digest] waiting for scheduled browser-session endpoint deployment; attempt={attempt} error={last_error}")
            time.sleep(15)
    raise RuntimeError(f"cannot obtain scheduled browser session: {last_error}")


def _launch_browser(playwright):
    executable = (
        shutil.which("google-chrome")
        or shutil.which("google-chrome-stable")
        or shutil.which("chromium")
        or shutil.which("chromium-browser")
    )
    if executable:
        print(f"[digest] using system Chromium browser: {executable}")
        return playwright.chromium.launch(headless=True, executable_path=executable, args=["--no-sandbox", "--disable-dev-shm-usage"])
    print("[digest] no system Chromium found; installing Playwright Chromium")
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    return playwright.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])


def generate_via_reports_page(selected, attention, days):
    global _rendered_pdf_bytes
    _rendered_pdf_bytes = None
    base_url = os.getenv("PUBLIC_BASE_URL", "https://ntue-news-bulletin.vercel.app").rstrip("/")
    run_id = os.getenv("GITHUB_RUN_ID", "").strip()
    sha = os.getenv("GITHUB_SHA", "").strip()
    workflow_token = os.getenv("GITHUB_WORKFLOW_TOKEN", "").strip()

    # Scheduled email reports must always use the live /reports design. Never
    # silently downgrade to the old ReportLab fallback.
    if not run_id or not sha or not workflow_token:
        raise RuntimeError("scheduled workflow authentication is incomplete; refusing legacy PDF fallback")
    if not selected:
        raise RuntimeError("no report data available; refusing legacy PDF fallback")

    try:
        from playwright.sync_api import sync_playwright

        cookie_name, session_token = _get_browser_session(base_url)
        feed_payload = json.dumps(
            {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "items": selected,
            },
            ensure_ascii=False,
        )

        with sync_playwright() as p:
            browser = _launch_browser(p)
            context = browser.new_context(viewport={"width": 1280, "height": 960}, locale="zh-TW")
            context.add_cookies(
                [
                    {
                        "name": cookie_name,
                        "value": session_token,
                        "url": base_url,
                        "httpOnly": True,
                        "secure": base_url.startswith("https://"),
                        "sameSite": "Lax",
                    }
                ]
            )

            def serve_current_feed(route):
                route.fulfill(status=200, content_type="application/json; charset=utf-8", body=feed_payload)

            context.route("**/data/news.json*", serve_current_feed)
            page = context.new_page()
            page.goto(f"{base_url}/reports", wait_until="networkidle", timeout=60000)
            if "/login" in page.url:
                raise RuntimeError("scheduled browser session was redirected to login")

            page.locator("select").select_option(str(days))
            with page.expect_response(
                lambda response: response.url.rstrip("/").endswith("/api/ai-report") and response.request.method == "POST",
                timeout=75000,
            ) as response_info:
                page.get_by_role("button", name="產生輿情報告").click()
            response = response_info.value
            if not response.ok:
                raise RuntimeError(f"website AI report HTTP {response.status}: {response.text()[:800]}")
            data = response.json()
            full_report = data.get("report")
            if not isinstance(full_report, dict):
                raise RuntimeError("website AI report returned no report object")

            page.wait_for_selector("article.paper", state="visible", timeout=30000)
            page.evaluate("() => document.fonts ? document.fonts.ready : Promise.resolve()")
            page.emulate_media(media="print")
            _rendered_pdf_bytes = page.pdf(
                format="A4",
                print_background=True,
                prefer_css_page_size=True,
            )
            browser.close()

        if not _rendered_pdf_bytes or len(_rendered_pdf_bytes) < 50000:
            raise RuntimeError(f"browser-rendered PDF is unexpectedly small ({len(_rendered_pdf_bytes or b'')}B)")

        topics = [str(x.get("topic") or "").strip() for x in full_report.get("topics", []) if str(x.get("topic") or "").strip()]
        recommendations = []
        for item in full_report.get("recommended_actions", []):
            unit = str(item.get("unit") or "").strip()
            action = str(item.get("action") or "").strip()
            if action:
                recommendations.append(f"{unit}：{action}" if unit else action)
        watchlist = []
        for item in full_report.get("notable_items", []):
            title = str(item.get("title") or "").strip()
            source = str(item.get("source") or "").strip()
            reason = str(item.get("reason") or "").strip()
            if title:
                label = f"{title}（{source}）" if source else title
                watchlist.append(f"{label}：{reason}" if reason else label)

        immediate_prefix = "建議立即處理" if full_report.get("immediate_action") else "目前不需立即處理"
        mapped = {
            "overall": str(full_report.get("summary") or full_report.get("executive_title") or ""),
            "immediate_action": f"{immediate_prefix}：{full_report.get('immediate_action_reason') or ''}",
            "themes": topics or ["本期無明顯集中議題"],
            "risk_assessment": f"{full_report.get('signal') or ''}｜綜合風險：{full_report.get('overall_risk') or '無法判定'}。{full_report.get('conclusion') or ''}",
            "recommendations": recommendations or ["維持例行監測"],
            "watchlist": watchlist[:5],
        }
        print(
            f"[digest] report rendered through live /reports page; run={run_id}; "
            f"pdf={len(_rendered_pdf_bytes)}B ai_generated=True"
        )
        return mapped, True
    except Exception as exc:
        _rendered_pdf_bytes = None
        print(f"[digest] live /reports rendering failed; delivery will NOT fall back to legacy PDF: {exc}")
        raise RuntimeError(f"live /reports rendering required but failed: {exc}") from exc


def create_pdf_from_reports_page(path, report, meta, attention, ai_generated):
    target = Path(path)
    if not _rendered_pdf_bytes:
        raise RuntimeError("browser-rendered /reports PDF missing; refusing legacy PDF generation")
    target.write_bytes(_rendered_pdf_bytes)
    print(f"[digest] wrote browser-rendered /reports PDF: {target} ({target.stat().st_size}B)")


def _body_to_html(body_fields):
    rows = []
    for label, value in body_fields.items():
        safe_label = html.escape(str(label))
        safe_value = html.escape(str(value)).replace("\n", "<br>")
        rows.append(
            f'<tr><td style="padding:10px 12px;background:#f4f7fa;font-weight:700;vertical-align:top;width:150px">{safe_label}</td>'
            f'<td style="padding:10px 12px;vertical-align:top">{safe_value}</td></tr>'
        )
    return (
        '<div style="font-family:Arial,\'Noto Sans TC\',sans-serif;color:#222;line-height:1.65">'
        '<h2 style="color:#17365d;margin:0 0 16px">國立臺北教育大學輿情快報</h2>'
        '<table style="border-collapse:collapse;width:100%;max-width:760px;border:1px solid #d9e1e8">'
        + "".join(rows)
        + '</table><p style="color:#666;font-size:12px;margin-top:16px">完整分析請見本信 PDF 附件；附件版面與系統「AI 輿情報告」列印版一致。</p></div>'
    )


def submit_via_brevo(recipient, subject, body_fields, source_url, pdf_path):
    api_key = os.getenv("BREVO_API_KEY", "").strip()
    sender_email = os.getenv("BREVO_SENDER_EMAIL", "").strip()
    sender_name = os.getenv("BREVO_SENDER_NAME", "國北教大輿情監測").strip() or "國北教大輿情監測"
    if not api_key:
        print("[digest] BREVO_API_KEY missing; cannot send PDF bulletin")
        return False
    if not sender_email:
        print("[digest] BREVO_SENDER_EMAIL missing; verify a sender in Brevo and set this secret")
        return False

    pdf = Path(pdf_path)
    if not pdf.exists() or pdf.stat().st_size < 50000:
        print(f"[digest] refusing to send invalid/small PDF attachment: {pdf} size={pdf.stat().st_size if pdf.exists() else 0}B")
        return False

    attachment_b64 = base64.b64encode(pdf.read_bytes()).decode("ascii")
    text_content = "\n\n".join(f"{k}\n{v}" for k, v in body_fields.items())
    payload = json.dumps(
        {
            "sender": {"name": sender_name, "email": sender_email},
            "to": [{"email": recipient}],
            "subject": subject,
            "htmlContent": _body_to_html(body_fields),
            "textContent": text_content,
            "attachment": [{"content": attachment_b64, "name": pdf.name}],
            "headers": {"X-NTUE-Report-Source": source_url},
        },
        ensure_ascii=False,
    ).encode("utf-8")

    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=payload,
        headers={
            "api-key": api_key,
            "accept": "application/json",
            "content-type": "application/json",
            "User-Agent": "NTUE-Opinion-Monitor/7.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            status = resp.status
        data = json.loads(body) if body else {}
        message_id = data.get("messageId")
        success = 200 <= status < 300 and bool(message_id)
        print(
            f"[digest] Brevo HTTP {status}; messageId={message_id or 'missing'}; "
            f"attachment={pdf.stat().st_size}B recipient={recipient}"
        )
        return success
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        print(f"[digest] Brevo HTTP {exc.code}: {detail[:800]}")
        return False
    except Exception as exc:
        print(f"[digest] Brevo send failed: {exc}")
        return False


digest.generate_ai_report = generate_via_reports_page
digest.create_pdf = create_pdf_from_reports_page
digest.submit_to_formsubmit = submit_via_brevo

if __name__ == "__main__":
    digest.main()
