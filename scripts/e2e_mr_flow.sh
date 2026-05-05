#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
SESSION_ID="${SESSION_ID:-e2e_mr_session_001}"
USER_ID="${USER_ID:-e2e_user_001}"
USER_NAME="${USER_NAME:-E2E测试账号}"

if ! command -v jq >/dev/null 2>&1; then
  echo "[ERROR] jq is required. Please install jq or manually copy snapshot_id from prepare response."
  exit 1
fi

echo "== 1) health ready =="
curl -sS "${BASE_URL}/health/ready" | jq .

echo "== 2) first prepare =="
PREPARE_1_RESPONSE="$(curl -sS -X POST "${BASE_URL}/api/purchase/material-requests/prepare" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"${SESSION_ID}\",\"user_id\":\"${USER_ID}\",\"user_name\":\"${USER_NAME}\",\"text\":\"我明天采购五常大米80斤，供应商采无忧\"}")"
echo "${PREPARE_1_RESPONSE}" | jq .
SNAPSHOT_1="$(echo "${PREPARE_1_RESPONSE}" | jq -r '.snapshot_id')"

echo "snapshot_1=${SNAPSHOT_1}"

echo "== 3) second prepare with previous_snapshot_id =="
PREPARE_2_RESPONSE="$(curl -sS -X POST "${BASE_URL}/api/purchase/material-requests/prepare" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"${SESSION_ID}\",\"user_id\":\"${USER_ID}\",\"user_name\":\"${USER_NAME}\",\"text\":\"仓库改成广州仓\",\"previous_snapshot_id\":\"${SNAPSHOT_1}\"}")"
echo "${PREPARE_2_RESPONSE}" | jq .
SNAPSHOT_2="$(echo "${PREPARE_2_RESPONSE}" | jq -r '.snapshot_id')"

echo "snapshot_2=${SNAPSHOT_2}"

echo "== 4) confirm latest snapshot =="
CONFIRM_RESPONSE="$(curl -sS -X POST "${BASE_URL}/api/purchase/material-requests/confirm" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"${SESSION_ID}\",\"user_id\":\"${USER_ID}\",\"snapshot_id\":\"${SNAPSHOT_2}\",\"confirm_text\":\"确认\"}")"
echo "${CONFIRM_RESPONSE}" | jq .

echo "E2E flow completed."
