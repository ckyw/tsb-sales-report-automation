from __future__ import annotations

import logging
from pathlib import Path

import matplotlib.pyplot as plt
from jinja2 import Environment, FileSystemLoader, select_autoescape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from src.report_metrics import MetricsPackage


LOGGER = logging.getLogger(__name__)


class PDFReportGenerator:
    def __init__(self, template_dir: Path) -> None:
        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape(["html"]),
        )

    def generate(self, report_date: str, metrics: MetricsPackage, ai_summary: str, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = output_dir / f"daily_sales_report_{report_date}.pdf"
        html_snapshot = output_dir / f"daily_sales_report_{report_date}.html"
        chart_path = output_dir / f"hourly_sales_{report_date}.png"

        self._render_html_snapshot(report_date, metrics, ai_summary, html_snapshot)
        self._build_hourly_chart(metrics, chart_path)
        self._build_pdf(report_date, metrics, ai_summary, pdf_path, chart_path)

        LOGGER.info("Generated PDF report at %s", pdf_path)
        return pdf_path

    def _render_html_snapshot(
        self,
        report_date: str,
        metrics: MetricsPackage,
        ai_summary: str,
        html_snapshot: Path,
    ) -> None:
        template = self.env.get_template("report_template.html")
        html = template.render(report_date=report_date, metrics=metrics, ai_summary=ai_summary)
        html_snapshot.write_text(html, encoding="utf-8")

    def _build_hourly_chart(self, metrics: MetricsPackage, chart_path: Path) -> None:
        hours = [str(item["hour"]).zfill(2) for item in metrics.hourly_sales]
        sales = [item["sales"] for item in metrics.hourly_sales]

        plt.figure(figsize=(8, 3))
        plt.plot(hours, sales, marker="o", color="#0F766E", linewidth=2)
        plt.title("Hourly Net Sales")
        plt.xlabel("Hour")
        plt.ylabel("Sales")
        plt.grid(alpha=0.2)
        plt.tight_layout()
        plt.savefig(chart_path, dpi=150)
        plt.close()

    def _build_pdf(
        self,
        report_date: str,
        metrics: MetricsPackage,
        ai_summary: str,
        pdf_path: Path,
        chart_path: Path,
    ) -> None:
        styles = getSampleStyleSheet()
        title_style = styles["Title"]
        body_style = styles["BodyText"]
        body_style.leading = 16
        section_style = ParagraphStyle("Section", parent=styles["Heading2"], textColor=colors.HexColor("#0F172A"))

        doc = SimpleDocTemplate(str(pdf_path), pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm)
        story = [
            Paragraph("탭샵바 일간 매출 리포트", title_style),
            Paragraph(f"보고 기준일: {report_date}", body_style),
            Spacer(1, 8),
            Paragraph("핵심 KPI", section_style),
            self._kpi_table(metrics),
            Spacer(1, 8),
            Paragraph("시간대별 순매출", section_style),
            Image(str(chart_path), width=170 * mm, height=65 * mm),
            Spacer(1, 8),
            Paragraph("카테고리 매출 TOP 5", section_style),
            self._sales_table(metrics.category_sales[:5], header=("카테고리", "순매출")),
            Spacer(1, 8),
            Paragraph("상품 매출 TOP 10", section_style),
            self._sales_table(metrics.top_products[:10], header=("상품", "순매출")),
            Spacer(1, 8),
            Paragraph("AI 요약 및 운영 액션", section_style),
        ]

        for line in ai_summary.splitlines():
            if line.strip():
                story.append(Paragraph(line.strip().replace("\n", "<br/>"), body_style))
                story.append(Spacer(1, 4))

        doc.build(story)

    def _kpi_table(self, metrics: MetricsPackage) -> Table:
        rows = [
            ["총매출", f"{metrics.total_gross_sales:,.0f}원"],
            ["순매출", f"{metrics.total_net_sales:,.0f}원"],
            ["주문 수", f"{metrics.order_count:,}건"],
            ["객단가", f"{metrics.average_order_value:,.0f}원"],
        ]
        table = Table(rows, colWidths=[55 * mm, 50 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                    ("PADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        return table

    def _sales_table(self, rows: list[dict[str, object]], header: tuple[str, str]) -> Table:
        table_rows = [list(header)] + [[str(row["name"]), f"{float(row['sales']):,.0f}원"] for row in rows]
        table = Table(table_rows, colWidths=[100 * mm, 40 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                    ("PADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        return table
