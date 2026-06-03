from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

from src.ai_summary import AISummaryGenerator
from src.bigquery_client import BigQuerySalesClient
from src.config import load_config
from src.email_sender import EmailSender
from src.pdf_generator import PDFReportGenerator
from src.report_metrics import build_metrics


def configure_logging(log_dir: Path, log_level: str) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "daily_report.log"

    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def resolve_report_date(tzinfo) -> datetime.date:
    now = datetime.now(tzinfo)
    return (now - timedelta(days=1)).date()


def main() -> None:
    config = load_config()
    configure_logging(config.log_dir, config.log_level)
    logger = logging.getLogger(__name__)

    started_at = datetime.now(config.tzinfo)
    report_date = resolve_report_date(config.tzinfo)
    logger.info("Workflow started at %s", started_at.isoformat())
    logger.info("Resolved report_date=%s", report_date.isoformat())

    try:
        bq_client = BigQuerySalesClient(config.bigquery)
        data_bundle = bq_client.fetch_sales_data(report_date)

        if data_bundle.current_day.empty:
            raise ValueError(f"No sales data found for report_date={report_date.isoformat()}")

        metrics = build_metrics(report_date, data_bundle, config.report_top_n_products)
        logger.info("Source row count=%s", metrics.source_row_count)

        ai_generator = AISummaryGenerator(config, Path("prompts/daily_sales_report.md"))
        ai_summary = ai_generator.generate(metrics)

        pdf_generator = PDFReportGenerator(Path("templates"))
        pdf_path = pdf_generator.generate(report_date.isoformat(), metrics, ai_summary, config.output_dir)
        logger.info("PDF path=%s", pdf_path)

        email_sender = EmailSender(config, Path("templates"))
        email_result = email_sender.send_daily_report(report_date.isoformat(), metrics, ai_summary, pdf_path)
        logger.info(
            "Email delivery complete success=%s failure=%s failed_recipients=%s",
            email_result["success_count"],
            email_result["failure_count"],
            email_result["failed_recipients"],
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Workflow failed: %s", exc)
        raise
    finally:
        ended_at = datetime.now(config.tzinfo)
        logger.info("Workflow finished at %s", ended_at.isoformat())


if __name__ == "__main__":
    main()
