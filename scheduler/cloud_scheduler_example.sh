#!/usr/bin/env bash

# NOTE: 실제 운영 시 아래 값들을 환경에 맞게 수정하세요.
PROJECT_ID="your-gcp-project-id"
REGION="asia-northeast3"
JOB_NAME="tsb-sales-report"
SCHEDULER_NAME="tsb-sales-report-daily"

# 1) Cloud Run Job 생성 예시
gcloud run jobs create "${JOB_NAME}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --image "asia-northeast3-docker.pkg.dev/${PROJECT_ID}/reporting/tsb-sales-report:latest" \
  --set-env-vars "TIMEZONE=Asia/Seoul" \
  --set-secrets "OPENAI_API_KEY=OPENAI_API_KEY:latest"

# 2) Cloud Scheduler에서 매일 10:00 Asia/Seoul 실행
gcloud scheduler jobs create http "${SCHEDULER_NAME}" \
  --project "${PROJECT_ID}" \
  --location "${REGION}" \
  --schedule "0 10 * * *" \
  --time-zone "Asia/Seoul" \
  --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${JOB_NAME}:run" \
  --http-method POST \
  --oauth-service-account-email "scheduler-invoker@${PROJECT_ID}.iam.gserviceaccount.com"
