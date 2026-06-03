from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd
from google.cloud import bigquery

from src.config import BigQuerySettings


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class QueryBundle:
    current_day: pd.DataFrame
    previous_day: pd.DataFrame
    previous_week_same_weekday: pd.DataFrame


class BigQuerySalesClient:
    def __init__(self, settings: BigQuerySettings) -> None:
        self.settings = settings
        self.client = bigquery.Client(project=settings.project_id)

    def fetch_sales_data(self, report_date: date) -> QueryBundle:
        LOGGER.info("Fetching BigQuery sales data for report_date=%s", report_date.isoformat())
        return QueryBundle(
            current_day=self._run_daily_query(report_date),
            previous_day=self._run_daily_query(report_date - timedelta(days=1)),
            previous_week_same_weekday=self._run_daily_query(report_date - timedelta(days=7)),
        )

    def _run_daily_query(self, target_date: date) -> pd.DataFrame:
        settings = self.settings
        quantity_expression = (
            f"SAFE_CAST({settings.quantity_column} AS FLOAT64)"
            if settings.quantity_column
            else "NULL"
        )

        # NOTE: Replace or extend this query if your POS datamart requires joins or pre-aggregation.
        query = f"""
        SELECT
          DATE({settings.date_column}, "Asia/Seoul") AS sale_date,
          EXTRACT(HOUR FROM DATETIME({settings.date_column}, "Asia/Seoul")) AS sale_hour,
          CAST({settings.order_id_column} AS STRING) AS order_id,
          COALESCE(CAST({settings.category_column} AS STRING), "Uncategorized") AS category_name,
          COALESCE(CAST({settings.product_column} AS STRING), "Unknown Product") AS product_name,
          COALESCE(CAST({settings.store_column} AS STRING), "Unknown Store") AS store_name,
          SAFE_CAST({settings.gross_sales_column} AS FLOAT64) AS gross_sales,
          SAFE_CAST({settings.net_sales_column} AS FLOAT64) AS net_sales,
          {quantity_expression} AS quantity
        FROM {settings.table_fqn}
        WHERE DATE({settings.date_column}, "Asia/Seoul") = @target_date
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("target_date", "DATE", target_date.isoformat())
            ]
        )
        dataframe = self.client.query(query, job_config=job_config).result().to_dataframe()
        LOGGER.info("Fetched %s rows for %s", len(dataframe.index), target_date.isoformat())
        return dataframe
