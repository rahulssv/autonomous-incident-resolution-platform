#!/usr/bin/env bash
set -euo pipefail

RUN_ID="$(date -u +%Y%m%d%H%M%S)-$$"
TEMPORAL_CONTAINER="airp-e2e-temporal-worker-${RUN_ID}"
ALERT_CONTAINER="airp-e2e-alert-consumer-${RUN_ID}"
E2E_CONSUMER_GROUP="${AIRP_E2E_CONSUMER_GROUP:-airp-e2e-alert-consumer-${RUN_ID}}"
CORE_SERVICES=(postgres redis temporal kubernetes-mcp github-mcp)

cleanup() {
  local status=$1
  if [[ "${status}" -ne 0 ]]; then
    echo "[airp-e2e] E2E failed. Recent worker logs:"
    docker logs --tail "${AIRP_E2E_LOG_TAIL:-120}" "${TEMPORAL_CONTAINER}" 2>/dev/null || true
    docker logs --tail "${AIRP_E2E_LOG_TAIL:-120}" "${ALERT_CONTAINER}" 2>/dev/null || true
  fi
  docker rm -f "${TEMPORAL_CONTAINER}" "${ALERT_CONTAINER}" >/dev/null 2>&1 || true
}

on_exit() {
  cleanup "$?"
}

on_signal() {
  trap - EXIT
  cleanup 130
  exit 130
}

trap on_exit EXIT
trap on_signal INT TERM

wait_container_running() {
  local container_name=$1
  local timeout_seconds=${AIRP_E2E_WORKER_START_TIMEOUT_SECONDS:-30}
  local deadline=$((SECONDS + timeout_seconds))
  local state

  while ((SECONDS < deadline)); do
    state="$(docker inspect -f '{{.State.Status}}' "${container_name}" 2>/dev/null || true)"
    if [[ "${state}" == "running" ]]; then
      return 0
    fi
    if [[ "${state}" == "exited" || "${state}" == "dead" ]]; then
      echo "[airp-e2e] ${container_name} exited during startup"
      return 1
    fi
    sleep 1
  done

  echo "[airp-e2e] ${container_name} did not reach running state within ${timeout_seconds}s"
  return 1
}

if [[ "${AIRP_E2E_BUILD:-1}" == "1" ]]; then
  echo "[airp-e2e] Building API and local MCP images"
  docker-compose build api kubernetes-mcp github-mcp
  echo "[airp-e2e] Recreating local MCP containers from rebuilt images"
  docker-compose up -d --force-recreate --no-deps kubernetes-mcp github-mcp
fi

echo "[airp-e2e] Starting live dependencies"
docker-compose up -d "${CORE_SERVICES[@]}"

if [[ "${AIRP_E2E_MIGRATE:-1}" == "1" ]]; then
  echo "[airp-e2e] Running database migrations"
  docker-compose run --rm --no-deps api alembic upgrade head
fi

echo "[airp-e2e] Starting API"
docker-compose up -d api

echo "[airp-e2e] Starting temporary Temporal worker: ${TEMPORAL_CONTAINER}"
docker-compose run -d --name "${TEMPORAL_CONTAINER}" --no-deps api \
  python -m airp.workers.temporal_worker >/dev/null
wait_container_running "${TEMPORAL_CONTAINER}"

echo "[airp-e2e] Starting temporary Kafka alert consumer: ${ALERT_CONTAINER}"
docker-compose run -d --name "${ALERT_CONTAINER}" --no-deps \
  -e AIRP_KAFKA_ALERT_CONSUMER_GROUP="${E2E_CONSUMER_GROUP}" \
  -e AIRP_KAFKA_AUTO_OFFSET_RESET=latest \
  api \
  python -m airp.workers.alert_consumer >/dev/null
wait_container_running "${ALERT_CONTAINER}"

sleep "${AIRP_E2E_WORKER_WARMUP_SECONDS:-5}"

echo "[airp-e2e] Running Kafka/Event Hubs E2E probe"
docker-compose run --rm --no-deps \
  -e AIRP_E2E_API_URL="${AIRP_E2E_API_URL:-http://api:8080}" \
  -e AIRP_E2E_TIMEOUT_SECONDS="${AIRP_E2E_TIMEOUT_SECONDS:-600}" \
  -e AIRP_E2E_POLL_INTERVAL_SECONDS="${AIRP_E2E_POLL_INTERVAL_SECONDS:-5}" \
  -e AIRP_E2E_READINESS_TIMEOUT_SECONDS="${AIRP_E2E_READINESS_TIMEOUT_SECONDS:-60}" \
  -e AIRP_E2E_CLOSE_TIMEOUT_SECONDS="${AIRP_E2E_CLOSE_TIMEOUT_SECONDS:-60}" \
  -e AIRP_E2E_CLOSE_WORKFLOW="${AIRP_E2E_CLOSE_WORKFLOW:-true}" \
  -e AIRP_E2E_REQUIRE_EVIDENCE="${AIRP_E2E_REQUIRE_EVIDENCE:-}" \
  -e AIRP_E2E_SKIP_READINESS="${AIRP_E2E_SKIP_READINESS:-}" \
  api python -m airp.dev.e2e_kafka_test "$@"

echo "[airp-e2e] E2E completed"
