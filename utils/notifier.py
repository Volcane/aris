"""
ARIS — Notification System

Sends email digests and Slack webhook messages when significant
regulatory activity is detected.

Configuration (config/keys.env):
    NOTIFY_EMAIL=recipient@company.com
    SMTP_HOST=smtp.gmail.com
    SMTP_PORT=587
    SMTP_USER=sender@gmail.com
    SMTP_PASSWORD=app-password

    SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...

    NOTIFY_ON_CRITICAL=true     # notify when critical changes detected
    NOTIFY_ON_HIGH=true         # notify when high-severity changes detected
    NOTIFY_ON_DIGEST=true       # send daily digest after scheduled runs
    NOTIFY_DEADLINE_DAYS=14     # alert when deadline within N days
"""

from __future__ import annotations

import json
import os
import smtplib
import urllib.request
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.cache import get_logger

log = get_logger("aris.notifier")

# ── Config ────────────────────────────────────────────────────────────────────

def _get(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()

def _bool(key: str, default: bool = True) -> bool:
    val = _get(key, "true" if default else "false").lower()
    return val in ("1", "true", "yes", "on")


def is_configured() -> bool:
    """Return True if at least one notification channel is configured."""
    return bool(_get("NOTIFY_EMAIL") or _get("SLACK_WEBHOOK_URL"))


def get_config() -> Dict[str, Any]:
    """Return the current notification configuration (safe to expose to UI)."""
    return {
        "email_configured":   bool(_get("NOTIFY_EMAIL")),
        "slack_configured":   bool(_get("SLACK_WEBHOOK_URL")),
        "notify_critical":    _bool("NOTIFY_ON_CRITICAL", True),
        "notify_high":        _bool("NOTIFY_ON_HIGH", True),
        "notify_digest":      _bool("NOTIFY_ON_DIGEST", True),
        "deadline_days":      int(_get("NOTIFY_DEADLINE_DAYS", "14")),
        "recipient_email":    _get("NOTIFY_EMAIL"),
        "slack_webhook_set":  bool(_get("SLACK_WEBHOOK_URL")),
        "smtp_host":          _get("SMTP_HOST"),
        "smtp_user":          _get("SMTP_USER"),
    }


# ── Email ─────────────────────────────────────────────────────────────────────

def send_email(subject: str, body_text: str, body_html: Optional[str] = None) -> bool:
    """Send an email notification. Returns True on success."""
    recipient = _get("NOTIFY_EMAIL")
    smtp_host = _get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(_get("SMTP_PORT", "587"))
    smtp_user = _get("SMTP_USER")
    smtp_pass = _get("SMTP_PASSWORD")

    if not all([recipient, smtp_host, smtp_user, smtp_pass]):
        log.debug("Email not configured — skipping")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"ARIS <{smtp_user}>"
        msg["To"]      = recipient

        msg.attach(MIMEText(body_text, "plain"))
        if body_html:
            msg.attach(MIMEText(body_html, "html"))

        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as s:
            s.starttls()
            s.login(smtp_user, smtp_pass)
            s.sendmail(smtp_user, recipient, msg.as_string())

        log.info("Email sent to %s: %s", recipient, subject)
        return True
    except Exception as e:
        log.error("Email send failed: %s", e)
        return False


# ── Slack ─────────────────────────────────────────────────────────────────────

def send_slack(text: str, blocks: Optional[list] = None) -> bool:
    """Send a Slack webhook message. Returns True on success."""
    webhook_url = _get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        log.debug("Slack not configured — skipping")
        return False

    try:
        payload = {"text": text}
        if blocks:
            payload["blocks"] = blocks

        data = json.dumps(payload).encode("utf-8")
        req  = urllib.request.Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = resp.read().decode()

        if result == "ok":
            log.info("Slack message sent")
            return True
        else:
            log.warning("Slack returned: %s", result)
            return False
    except Exception as e:
        log.error("Slack send failed: %s", e)
        return False


# ── Message builders ──────────────────────────────────────────────────────────

def _build_digest(run_result: Dict[str, Any]) -> tuple[str, str, str]:
    """Build subject, plain text, and Slack text for a run digest."""
    date_str   = datetime.utcnow().strftime("%A, %B %-d %Y")
    fetched    = run_result.get("fetched", 0)
    summarized = run_result.get("summarized", 0)
    skipped    = run_result.get("skipped", 0)
    diffs      = run_result.get("version_diffs", 0) + run_result.get("addenda_found", 0)
    urgency    = run_result.get("urgency_dist", {})
    critical   = urgency.get("Critical", 0)
    high       = urgency.get("High", 0)
    total_db   = run_result.get("total_documents", 0)

    subject = f"ARIS Digest — {date_str}"
    if critical > 0:
        subject = f"⚠ ARIS: {critical} critical finding{'s' if critical > 1 else ''} — {date_str}"

    lines = [
        f"ARIS Regulatory Digest — {date_str}",
        "─" * 50,
    ]

    if critical > 0:
        lines.append(f"⚠  {critical} critical-urgency document{'s' if critical > 1 else ''} detected")
    if high > 0:
        lines.append(f"↑  {high} high-urgency document{'s' if high > 1 else ''}")
    if diffs > 0:
        lines.append(f"Δ  {diffs} regulatory change{'s' if diffs > 1 else ''} detected")

    lines += [
        "",
        f"Fetched:     {fetched} new documents",
        f"Summarised:  {summarized}",
    ]
    if skipped > 0:
        lines.append(f"Skipped:     {skipped} (pre-filter)")

    lines += [
        "",
        f"Total in DB: {total_db} documents",
        "─" * 50,
        "View at: http://localhost:8000",
        "",
        "Sent by ARIS — configure notifications in Settings",
    ]

    text = "\n".join(lines)

    # Slack blocks version
    slack_text = f"*ARIS Digest — {date_str}*\n"
    if critical > 0:
        slack_text += f":warning: *{critical} critical finding{'s' if critical > 1 else ''}*\n"
    slack_text += f"Fetched {fetched} docs · Summarised {summarized}"
    if diffs > 0:
        slack_text += f" · {diffs} change{'s' if diffs > 1 else ''} detected"
    slack_text += f"\n<http://localhost:8000|Open ARIS>"

    return subject, text, slack_text


def _build_critical_alert(change_summary: str, severity: str) -> tuple[str, str, str]:
    """Build alert for a single critical/high change."""
    date_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    emoji    = "🚨" if severity == "Critical" else "⚠️"
    subject  = f"{emoji} ARIS: {severity} regulatory change detected"
    text     = (
        f"{emoji} {severity} Regulatory Change\n"
        f"{'─' * 50}\n"
        f"{change_summary}\n\n"
        f"Detected: {date_str}\n"
        f"View changes: http://localhost:8000/changes\n"
    )
    slack = f"{emoji} *{severity} regulatory change*\n{change_summary}\n<http://localhost:8000/changes|Review in ARIS>"
    return subject, text, slack


# ── Public API ────────────────────────────────────────────────────────────────

def send_digest_if_warranted(run_result: Dict[str, Any]) -> None:
    """
    Called after a scheduled run completes. Sends a notification if:
    - There are critical/high findings (always notify)
    - A digest is enabled and something notable happened
    """
    if not is_configured():
        return

    fetched    = run_result.get("fetched", 0)
    summarized = run_result.get("summarized", 0)
    urgency    = run_result.get("urgency_dist", {})
    critical   = urgency.get("Critical", 0)
    high       = urgency.get("High", 0)

    # Always notify on critical regardless of digest setting
    if critical > 0 and _bool("NOTIFY_ON_CRITICAL", True):
        subject, text, slack_text = _build_digest(run_result)
        subject = f"🚨 ARIS: {critical} critical finding{'s' if critical > 1 else ''} detected"
        send_email(subject, text)
        send_slack(slack_text)
        return

    # Notify on high if configured
    if high > 0 and _bool("NOTIFY_ON_HIGH", True):
        subject, text, slack_text = _build_digest(run_result)
        send_email(subject, text)
        send_slack(slack_text)
        return

    # Daily digest — send if anything was fetched
    if _bool("NOTIFY_ON_DIGEST", True) and (fetched > 0 or summarized > 0):
        subject, text, slack_text = _build_digest(run_result)
        send_email(subject, text)
        send_slack(slack_text)


def send_test_notification() -> Dict[str, bool]:
    """Send a test message to all configured channels. Returns results."""
    results = {}
    subject  = "ARIS — Test Notification"
    text     = "This is a test notification from ARIS. Your notification settings are working correctly."
    slack_text = ":white_check_mark: *ARIS test notification* — your Slack integration is working."

    results["email"] = send_email(subject, text)
    results["slack"] = send_slack(slack_text)
    return results
