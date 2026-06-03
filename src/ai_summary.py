from __future__ import annotations

import json
import logging
from pathlib import Path

from openai import OpenAI

from src.config import AppConfig
from src.report_metrics import MetricsPackage


LOGGER = logging.getLogger(__name__)


class AISummaryGenerator:
    def __init__(self, config: AppConfig, prompt_path: Path) -> None:
        self.config = config
        self.prompt_path = prompt_path

    def generate(self, metrics: MetricsPackage) -> str:
        if self.config.dry_run or not self.config.openai.api_key:
            LOGGER.info("Using fallback summary because DRY_RUN is enabled or OPENAI_API_KEY is missing.")
            return self._fallback_summary(metrics)

        prompt_template = self.prompt_path.read_text(encoding="utf-8")
        payload = json.dumps(metrics.to_prompt_payload(), ensure_ascii=False, indent=2)
        prompt = prompt_template.replace("{{METRICS_PAYLOAD_JSON}}", payload)

        client = OpenAI(api_key=self.config.openai.api_key, timeout=self.config.openai.timeout_seconds)
        response = client.responses.create(
            model=self.config.openai.model,
            input=prompt,
        )
        summary = response.output_text.strip()
        if not summary:
            raise ValueError("OpenAI response was empty.")
        return summary

    def _fallback_summary(self, metrics: MetricsPackage) -> str:
        pd_rate = metrics.previous_day_change["total_net_sales"].rate
        pw_rate = metrics.previous_week_change["total_net_sales"].rate

        pd_text = "비교 데이터 없음" if pd_rate is None else f"{pd_rate * 100:+.1f}%"
        pw_text = "비교 데이터 없음" if pw_rate is None else f"{pw_rate * 100:+.1f}%"
        top_category = metrics.category_sales[0]["name"] if metrics.category_sales else "N/A"
        top_product = metrics.top_products[0]["name"] if metrics.top_products else "N/A"

        return "\n".join(
            [
                "1. Executive Summary",
                f"- 보고일 순매출은 {metrics.total_net_sales:,.0f}원이며 주문 수는 {metrics.order_count:,}건입니다.",
                f"- 전일 대비 순매출 변화는 {pd_text}, 전주 동일 요일 대비 변화는 {pw_text}입니다.",
                "2. 주요 매출 지표",
                f"- 총매출 {metrics.total_gross_sales:,.0f}원 / 순매출 {metrics.total_net_sales:,.0f}원 / 객단가 {metrics.average_order_value:,.0f}원",
                "3. 매출 변화 분석",
                "- 전일 및 전주 동일 요일과의 차이를 함께 확인해 일시적 이벤트와 추세 변화를 구분해야 합니다.",
                "4. 시간대별 분석",
                f"- 피크 시간대 점검이 필요하며, {metrics.anomalies[0] if metrics.anomalies else '시간대 데이터가 없습니다.'}",
                "5. 카테고리 및 상품 분석",
                f"- 카테고리 1위는 {top_category}, 상품 1위는 {top_product}입니다.",
                "6. 특이사항",
                f"- {' / '.join(metrics.anomalies) if metrics.anomalies else '특이사항이 감지되지 않았습니다.'}",
                "7. 운영 액션 제안",
                "- 피크 시간대 인력 운영, 상위 카테고리 재고, 상위 상품 프로모션 유지 여부를 함께 검토하세요.",
            ]
        )
