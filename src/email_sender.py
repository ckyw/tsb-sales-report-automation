from __future__ import annotations

import logging
import smtplib
import time
from email.message import EmailMessage
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.config import AppConfig
from src.report_metrics import MetricsPackage


LOGGER = logging.getLogger(__name__)


class EmailSender:
    def __init__(self, config: AppConfig, template_dir: Path) -> None:
        self.config = config
        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape(["html"]),
        )

    def send_daily_report(
        self,
        report_date: str,
        metrics: MetricsPackage,
        ai_summary: str,
        pdf_path: Path,
    ) -> dict[str, object]:
        recipients = self._resolve_recipients()
        subject = f"{self.config.email.subject_prefix} {report_date} 일간 매출 리포트"
        highlights = metrics.to_email_points()
        html_body = self.env.get_template("email_summary.html").render(
            report_date=report_date,
            metrics=metrics,
            highlights=highlights,
            ai_summary=ai_summary,
            dry_run=self.config.dry_run,
        )

        if self.config.dry_run and not recipients:
            LOGGER.info("DRY_RUN enabled and DRY_RUN_RECIPIENTS empty. Skipping outbound email.")
            return {"success_count": 0, "failure_count": 0, "failed_recipients": []}

        success_count = 0
        failed_recipients: list[str] = []
        for recipient in recipients:
            try:
                self._send_one(subject, html_body, recipient, pdf_path)
                success_count += 1
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("Failed to send email to %s: %s", recipient, exc)
                failed_recipients.append(recipient)

        return {
            "success_count": success_count,
            "failure_count": len(failed_recipients),
            "failed_recipients": failed_recipients,
        }

    def _resolve_recipients(self) -> list[str]:
        if self.config.dry_run:
            return self.config.email.dry_run_recipients
        return self.config.email.recipients

    def _send_one(self, subject: str, html_body: str, recipient: str, pdf_path: Path) -> None:
        message = EmailMessage()
        message["From"] = self.config.email.sender
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content("HTML email client에서 확인해주세요.")
        message.add_alternative(html_body, subtype="html")
        message.add_attachment(
            pdf_path.read_bytes(),
            maintype="application",
            subtype="pdf",
            filename=pdf_path.name,
        )

        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                with smtplib.SMTP(self.config.email.smtp_host, self.config.email.smtp_port, timeout=30) as smtp:
                    if self.config.email.smtp_use_tls:
                        smtp.starttls()
                    smtp.login(self.config.email.smtp_username, self.config.email.smtp_password)
                    smtp.send_message(message)
                LOGGER.info("Sent email to %s on attempt %s", recipient, attempt)
                return
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                LOGGER.warning("SMTP attempt %s failed for %s: %s", attempt, recipient, exc)
                time.sleep(attempt)

        raise RuntimeError(f"Email send failed for {recipient}") from last_error
