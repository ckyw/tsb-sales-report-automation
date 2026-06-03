# 탭샵바 일간 매출 리포트 자동화

BigQuery POS 데이터마트에서 전일 매출 데이터를 조회하고, KPI 계산, AI 요약, PDF 생성, 이메일 발송까지 매일 자동 실행하는 Python 기반 워크플로우 초안입니다.

## 권장 아키텍처

운영 배포는 `Cloud Run Job + Cloud Scheduler` 조합을 권장합니다.

- 코드가 상태를 거의 가지지 않아 컨테이너 배포에 잘 맞습니다.
- Secret Manager와 연동하기 쉽습니다.
- `Asia/Seoul` 기준 스케줄 관리가 단순합니다.
- 실패 시 Cloud Logging, 재실행, 알림 연계가 쉽습니다.

로컬 검증이나 빠른 임시 운영이 필요하면 `scheduler/cron.example` 기준으로 cron 실행도 가능합니다.

## 디렉토리 구조

```text
.
├── .env.example
├── README.md
├── config/
│   └── recipients.example.csv
├── requirements.txt
├── logs/
├── output/
├── prompts/
│   └── daily_sales_report.md
├── scheduler/
│   ├── cloud_scheduler_example.sh
│   └── cron.example
├── src/
│   ├── __init__.py
│   ├── ai_summary.py
│   ├── bigquery_client.py
│   ├── config.py
│   ├── email_sender.py
│   ├── main.py
│   ├── pdf_generator.py
│   └── report_metrics.py
└── templates/
    ├── email_summary.html
    └── report_template.html
```

## 실행 흐름

1. `src/main.py` 가 `Asia/Seoul` 기준 전일 날짜를 계산합니다.
2. `src/bigquery_client.py` 가 BigQuery에서 보고일, 전일, 전주 동일 요일 데이터를 조회합니다.
3. `src/report_metrics.py` 가 KPI, 시간대/카테고리/상품/매장 매출, 증감률을 계산합니다.
4. `src/ai_summary.py` 가 집계 데이터만 사용해 OpenAI 요약문을 생성합니다.
5. `src/pdf_generator.py` 가 PDF와 HTML 스냅샷을 생성합니다.
6. `src/email_sender.py` 가 메일 본문 HTML과 PDF 첨부파일을 각 수신자에게 발송합니다.
7. 성공/실패/건수/파일 경로를 `logs/daily_report.log` 에 남깁니다.

## 빠른 시작

### 1. 의존성 설치

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 환경변수 준비

`.env.example` 을 복사해 `.env` 로 만든 뒤 값들을 채웁니다.

```bash
cp .env.example .env
```

운영 전 반드시 수정해야 하는 항목:

- `BQ_*`: 실제 BigQuery 프로젝트, 데이터셋, 테이블, 컬럼명
- `GOOGLE_APPLICATION_CREDENTIALS`: 서비스 계정 키 경로
- `OPENAI_API_KEY`
- `SMTP_*`
- `EMAIL_TO` 또는 `RECIPIENTS_FILE`

## BigQuery 쿼리 커스터마이징

현재 `src/bigquery_client.py` 는 아래 전제를 두고 있습니다.

- POS 데이터마트에 `sale_timestamp`, `gross_sales`, `net_sales`, `order_id` 등 기본 컬럼이 존재
- 한 행이 주문 또는 주문 상세 수준 데이터
- `DATE(timestamp, "Asia/Seoul")` 기준으로 보고일 필터 가능

실제 데이터마트에서 아래 케이스가 있으면 반드시 수정하세요.

- 조인이 필요한 스타 스키마 구조
- 환불/취소 데이터 분리 테이블
- 매장 기준 권한 필터
- 카테고리/상품명이 코드값으로만 저장된 구조
- 시간 컬럼이 UTC 문자열 등 비표준 타입인 구조

## 이메일 수신자 관리

수신자는 코드에 하드코딩하지 않습니다. 다음 우선순위로 로드됩니다.

1. `RECIPIENTS_FILE`
2. `RECIPIENTS_JSON`
3. `EMAIL_TO`

`RECIPIENTS_FILE` 이 CSV 인 경우 `email` 헤더를 사용합니다. 샘플은 [config/recipients.example.csv](/Users/ck/vibecoding/tsb-sales-report-automation/config/recipients.example.csv) 에 있습니다.

예시:

```csv
email
ops1@example.com
ops2@example.com
```

## DRY RUN

테스트 중 실수로 50명에게 메일이 발송되지 않도록 `DRY_RUN=true` 를 기본값으로 둡니다.

- `DRY_RUN=true`: `DRY_RUN_RECIPIENTS` 로만 전송하거나, 값이 비어 있으면 발송을 생략
- `DRY_RUN=false`: 실제 수신자 전체에게 발송

## 로그와 실패 처리

로그에는 다음 정보가 남습니다.

- 실행 시작/종료 시각
- 조회 기준일
- 조회된 데이터 건수
- PDF 생성 경로
- 이메일 성공/실패 수
- 실패 수신자 목록
- 예외 스택트레이스

이메일은 수신자별로 최대 3회 재시도합니다.

## 실행

```bash
python3 -m src.main
```

## 운영 전 체크리스트

- BigQuery 서비스 계정에 `BigQuery Job User`, `BigQuery Data Viewer` 권한 부여
- SMTP 또는 메일 API 발송 한도 확인
- OpenAI API 사용량/타임아웃 정책 확인
- PDF 생성 결과 샘플 검수
- `DRY_RUN=false` 전환 전 테스트 수신자로 검증
- 스케줄러 실행 계정에 Secret 접근 권한 부여

## 향후 확장 아이디어

- 매장별 상세 페이지 추가
- 임계치 기반 알림 슬랙 연동
- 실패 시 재처리 큐 분리
- HTML to PDF 엔진 교체 또는 브랜딩 강화
- pytest 기반 단위 테스트 추가
