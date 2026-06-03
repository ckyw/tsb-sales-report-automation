from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from dotenv import load_dotenv


@dataclass(frozen=True)
class BigQuerySettings:
    project_id: str
    dataset: str
    table: str
    date_column: str
    gross_sales_column: str
    net_sales_column: str
    order_id_column: str
    category_column: str
    product_column: str
    store_column: str
    quantity_column: str | None

    @property
    def table_fqn(self) -> str:
        return f"`{self.project_id}.{self.dataset}.{self.table}`"


@dataclass(frozen=True)
class OpenAISettings:
    api_key: str | None
    model: str
    timeout_seconds: int


@dataclass(frozen=True)
class EmailSettings:
    sender: str
    subject_prefix: str
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_use_tls: bool
    recipients: list[str]
    dry_run_recipients: list[str]


@dataclass(frozen=True)
class AppConfig:
    app_env: str
    timezone: str
    dry_run: bool
    log_level: str
    report_top_n_products: int
    output_dir: Path
    log_dir: Path
    bigquery: BigQuerySettings
    openai: OpenAISettings
    email: EmailSettings

    @property
    def tzinfo(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


def load_config() -> AppConfig:
    load_dotenv()

    output_dir = Path(os.getenv("OUTPUT_DIR", "output"))
    log_dir = Path(os.getenv("LOG_DIR", "logs"))

    recipients = _load_recipients()
    dry_run_recipients = _split_csv(os.getenv("DRY_RUN_RECIPIENTS", ""))

    return AppConfig(
        app_env=os.getenv("APP_ENV", "local"),
        timezone=os.getenv("TIMEZONE", "Asia/Seoul"),
        dry_run=_parse_bool(os.getenv("DRY_RUN", "true")),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        report_top_n_products=int(os.getenv("REPORT_TOP_N_PRODUCTS", "10")),
        output_dir=output_dir,
        log_dir=log_dir,
        bigquery=BigQuerySettings(
            project_id=_required("BQ_PROJECT_ID"),
            dataset=_required("BQ_DATASET"),
            table=_required("BQ_TABLE"),
            date_column=_required("BQ_DATE_COLUMN"),
            gross_sales_column=_required("BQ_GROSS_SALES_COLUMN"),
            net_sales_column=_required("BQ_NET_SALES_COLUMN"),
            order_id_column=_required("BQ_ORDER_ID_COLUMN"),
            category_column=_required("BQ_CATEGORY_COLUMN"),
            product_column=_required("BQ_PRODUCT_COLUMN"),
            store_column=os.getenv("BQ_STORE_COLUMN", "store_name"),
            quantity_column=os.getenv("BQ_QUANTITY_COLUMN") or None,
        ),
        openai=OpenAISettings(
            api_key=os.getenv("OPENAI_API_KEY"),
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            timeout_seconds=int(os.getenv("OPENAI_TIMEOUT_SECONDS", "45")),
        ),
        email=EmailSettings(
            sender=_required("EMAIL_FROM"),
            subject_prefix=os.getenv("EMAIL_SUBJECT_PREFIX", "[탭샵바]"),
            smtp_host=_required("SMTP_HOST"),
            smtp_port=int(os.getenv("SMTP_PORT", "587")),
            smtp_username=_required("SMTP_USERNAME"),
            smtp_password=_required("SMTP_PASSWORD"),
            smtp_use_tls=_parse_bool(os.getenv("SMTP_USE_TLS", "true")),
            recipients=recipients,
            dry_run_recipients=dry_run_recipients,
        ),
    )


def _load_recipients() -> list[str]:
    recipients_file = os.getenv("RECIPIENTS_FILE", "").strip()
    recipients_json = os.getenv("RECIPIENTS_JSON", "").strip()

    if recipients_file:
        return _load_recipients_from_file(Path(recipients_file))
    if recipients_json:
        data = json.loads(recipients_json)
        return _normalize_emails(data)

    recipients = _split_csv(os.getenv("EMAIL_TO", ""))
    if not recipients:
        raise ValueError("At least one recipient is required via EMAIL_TO, RECIPIENTS_FILE, or RECIPIENTS_JSON.")
    return recipients


def _load_recipients_from_file(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"Recipients file not found: {path}")

    if path.suffix.lower() == ".json":
        return _normalize_emails(json.loads(path.read_text(encoding="utf-8")))

    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            emails = [row.get("email", "").strip() for row in reader if row.get("email", "").strip()]
        return _normalize_emails(emails)

    raise ValueError("Recipients file must be CSV or JSON.")


def _normalize_emails(data: Any) -> list[str]:
    if isinstance(data, list):
        emails = [str(item).strip() for item in data if str(item).strip()]
    else:
        raise ValueError("Recipient data must be a list of email addresses.")
    if not emails:
        raise ValueError("Recipient list is empty.")
    return emails


def _split_csv(raw_value: str) -> list[str]:
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}
