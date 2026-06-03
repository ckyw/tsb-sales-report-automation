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
        order_id_expression = (
            f"CAST({settings.order_id_column} AS STRING)"
            if settings.order_id_column
            else f"CAST({settings.row_key_column} AS STRING)"
        )
        sale_hour_expression = (
            f"SAFE_CAST({settings.sale_hour_column} AS INT64)"
            if settings.sale_hour_column
            else "NULL"
        )
        quantity_expression = (
            f"SAFE_CAST({settings.quantity_column} AS FLOAT64)"
            if settings.quantity_column
            else "NULL"
        )
        discount_expression = (
            f"SAFE_CAST({settings.discount_amount_column} AS FLOAT64)"
            if settings.discount_amount_column
            else "0"
        )
        supply_expression = (
            f"SAFE_CAST({settings.supply_amount_column} AS FLOAT64)"
            if settings.supply_amount_column
            else "0"
        )
        vat_expression = (
            f"SAFE_CAST({settings.vat_amount_column} AS FLOAT64)"
            if settings.vat_amount_column
            else "0"
        )
        pos_type_expression = (
            f"COALESCE(CAST({settings.pos_type_column} AS STRING), 'Unknown POS')"
            if settings.pos_type_column
            else "'Unknown POS'"
        )

        # NOTE: This query is aligned to the provided daily POS mart schema.
        # If there is no explicit order_id or hour column, row_key is used as a fallback ID
        # and hourly analysis remains unavailable until the mart exposes a time dimension.
        query = f"""
        SELECT
          {settings.date_column} AS sale_date,
          {sale_hour_expression} AS sale_hour,
          CAST({settings.row_key_column} AS STRING) AS row_key,
          {order_id_expression} AS order_id,
          COALESCE(CAST({settings.category_column} AS STRING), "Uncategorized") AS category_name,
          COALESCE(CAST({settings.product_column} AS STRING), "Unknown Product") AS product_name,
          COALESCE(CAST({settings.store_column} AS STRING), "Unknown Store") AS store_name,
          SAFE_CAST({settings.gross_sales_column} AS FLOAT64) AS gross_sales,
          SAFE_CAST({settings.net_sales_column} AS FLOAT64) AS net_sales,
          {discount_expression} AS discount_amount,
          {supply_expression} AS supply_amount,
          {vat_expression} AS vat_amount,
          {pos_type_expression} AS pos_type,
          {quantity_expression} AS quantity
        FROM {settings.table_fqn}
        WHERE {settings.date_column} = @target_date
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("target_date", "DATE", target_date.isoformat())
            ]
        )
        dataframe = self.client.query(query, job_config=job_config).result().to_dataframe()
        LOGGER.info("Fetched %s rows for %s", len(dataframe.index), target_date.isoformat())
        return dataframe
