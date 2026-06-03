from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from src.bigquery_client import QueryBundle


@dataclass(frozen=True)
class MetricChange:
    absolute: float
    rate: float | None


@dataclass(frozen=True)
class MetricsPackage:
    report_date: date
    total_gross_sales: float
    total_net_sales: float
    order_count: int
    average_order_value: float
    previous_day_change: dict[str, MetricChange]
    previous_week_change: dict[str, MetricChange]
    hourly_sales: list[dict[str, Any]]
    category_sales: list[dict[str, Any]]
    top_products: list[dict[str, Any]]
    store_sales: list[dict[str, Any]]
    pos_type_sales: list[dict[str, Any]]
    anomalies: list[str]
    source_row_count: int

    def to_prompt_payload(self) -> dict[str, Any]:
        return {
            "report_date": self.report_date.isoformat(),
            "kpis": {
                "total_gross_sales": round(self.total_gross_sales, 2),
                "total_net_sales": round(self.total_net_sales, 2),
                "order_count": self.order_count,
                "average_order_value": round(self.average_order_value, 2),
            },
            "previous_day_change": _serialize_changes(self.previous_day_change),
            "previous_week_change": _serialize_changes(self.previous_week_change),
            "hourly_sales": self.hourly_sales,
            "category_sales": self.category_sales[:10],
            "top_products": self.top_products,
            "store_sales": self.store_sales,
            "pos_type_sales": self.pos_type_sales,
            "anomalies": self.anomalies,
        }

    def to_email_points(self) -> list[str]:
        points = [
            f"순매출 {self.total_net_sales:,.0f}원 / 주문 {self.order_count:,}건 / 객단가 {self.average_order_value:,.0f}원",
            _format_change_line("전일 대비 순매출", self.previous_day_change["total_net_sales"]),
            _format_change_line("전주 동일 요일 대비 순매출", self.previous_week_change["total_net_sales"]),
        ]
        points.extend(self.anomalies[:2])
        return points[:5]


def build_metrics(report_date: date, bundle: QueryBundle, top_n_products: int) -> MetricsPackage:
    current = _prepare_dataframe(bundle.current_day)
    previous_day = _prepare_dataframe(bundle.previous_day)
    previous_week = _prepare_dataframe(bundle.previous_week_same_weekday)

    total_gross_sales = current["gross_sales"].sum()
    total_net_sales = current["net_sales"].sum()
    order_count = current["order_id"].nunique()
    average_order_value = total_net_sales / order_count if order_count else 0.0

    current_summary = {
        "total_gross_sales": total_gross_sales,
        "total_net_sales": total_net_sales,
        "order_count": float(order_count),
        "average_order_value": average_order_value,
    }
    previous_day_summary = _summary(previous_day)
    previous_week_summary = _summary(previous_week)

    hourly_sales = (
        current[current["sale_hour"].notna()]
        .groupby("sale_hour", dropna=False)["net_sales"]
        .sum()
        .reset_index()
        .sort_values("sale_hour")
        .rename(columns={"sale_hour": "hour", "net_sales": "sales"})
        .to_dict(orient="records")
    )
    category_sales = _group_sales(current, "category_name")
    top_products = _group_sales(current, "product_name", limit=top_n_products)
    store_sales = _group_sales(current, "store_name")
    pos_type_sales = _group_sales(current, "pos_type")
    anomalies = _detect_anomalies(hourly_sales, category_sales, top_products, pos_type_sales)

    return MetricsPackage(
        report_date=report_date,
        total_gross_sales=total_gross_sales,
        total_net_sales=total_net_sales,
        order_count=order_count,
        average_order_value=average_order_value,
        previous_day_change=_compute_changes(current_summary, previous_day_summary),
        previous_week_change=_compute_changes(current_summary, previous_week_summary),
        hourly_sales=hourly_sales,
        category_sales=category_sales,
        top_products=top_products,
        store_sales=store_sales,
        pos_type_sales=pos_type_sales,
        anomalies=anomalies,
        source_row_count=len(current.index),
    )


def _prepare_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    if dataframe.empty:
        return pd.DataFrame(
            columns=[
                "sale_date",
                "sale_hour",
                "row_key",
                "order_id",
                "category_name",
                "product_name",
                "store_name",
                "gross_sales",
                "net_sales",
                "discount_amount",
                "supply_amount",
                "vat_amount",
                "pos_type",
                "quantity",
            ]
        )

    normalized = dataframe.copy()
    numeric_columns = ["gross_sales", "net_sales", "quantity"]
    for column in numeric_columns:
        if column in normalized.columns:
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce").fillna(0.0)
    normalized["sale_hour"] = pd.to_numeric(normalized["sale_hour"], errors="coerce")
    normalized["order_id"] = normalized["order_id"].fillna("").astype(str)
    return normalized


def _summary(dataframe: pd.DataFrame) -> dict[str, float]:
    order_count = dataframe["order_id"].nunique()
    total_net_sales = dataframe["net_sales"].sum()
    return {
        "total_gross_sales": dataframe["gross_sales"].sum(),
        "total_net_sales": total_net_sales,
        "order_count": float(order_count),
        "average_order_value": total_net_sales / order_count if order_count else 0.0,
    }


def _compute_changes(current: dict[str, float], baseline: dict[str, float]) -> dict[str, MetricChange]:
    changes: dict[str, MetricChange] = {}
    for key, current_value in current.items():
        baseline_value = baseline.get(key, 0.0)
        absolute = current_value - baseline_value
        rate = (absolute / baseline_value) if baseline_value else None
        changes[key] = MetricChange(absolute=absolute, rate=rate)
    return changes


def _group_sales(dataframe: pd.DataFrame, column: str, limit: int | None = None) -> list[dict[str, Any]]:
    grouped = (
        dataframe.groupby(column, dropna=False)["net_sales"]
        .sum()
        .reset_index()
        .rename(columns={column: "name", "net_sales": "sales"})
        .sort_values("sales", ascending=False)
    )
    if limit:
        grouped = grouped.head(limit)
    return grouped.to_dict(orient="records")


def _detect_anomalies(
    hourly_sales: list[dict[str, Any]],
    category_sales: list[dict[str, Any]],
    top_products: list[dict[str, Any]],
    pos_type_sales: list[dict[str, Any]],
) -> list[str]:
    messages: list[str] = []

    if hourly_sales:
        peak_hour = max(hourly_sales, key=lambda item: item["sales"])
        messages.append(
            f"최고 매출 시간대는 {int(peak_hour['hour']):02d}시이며 순매출은 {peak_hour['sales']:,.0f}원입니다."
        )
    else:
        messages.append("현재 데이터마트에는 시간 컬럼이 없어 시간대별 매출 분석은 제공되지 않습니다.")

    if category_sales:
        lead_category = category_sales[0]
        messages.append(
            f"카테고리 매출 1위는 {lead_category['name']}이며 순매출은 {lead_category['sales']:,.0f}원입니다."
        )

    if top_products:
        lead_product = top_products[0]
        messages.append(
            f"상품 매출 1위는 {lead_product['name']}이며 순매출은 {lead_product['sales']:,.0f}원입니다."
        )

    if pos_type_sales:
        lead_pos_type = pos_type_sales[0]
        messages.append(
            f"POS 유형 기준 1위는 {lead_pos_type['name']}이며 순매출은 {lead_pos_type['sales']:,.0f}원입니다."
        )

    return messages


def _serialize_changes(changes: dict[str, MetricChange]) -> dict[str, dict[str, float | None]]:
    return {
        key: {"absolute": round(value.absolute, 2), "rate": round(value.rate, 4) if value.rate is not None else None}
        for key, value in changes.items()
    }


def _format_change_line(label: str, change: MetricChange) -> str:
    if change.rate is None:
        return f"{label}: 비교 데이터 없음"
    sign = "+" if change.absolute >= 0 else ""
    return f"{label}: {sign}{change.absolute:,.0f}원 ({sign}{change.rate * 100:.1f}%)"
