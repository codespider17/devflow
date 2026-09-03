#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE_DIR="${1:-.}"
IMAGE_REFERENCE="${2:-}"
REPORT_DIR="${3:-reports/trivy}"
TRIVY_CACHE_DIR="${TRIVY_CACHE_DIR:-/var/jenkins_home/.cache/trivy}"
HELM_VALUES_FILE="${SOURCE_DIR}/ci/trivy/helm-values.yaml"

test -d "$SOURCE_DIR" || {
  echo "STOP: source directory does not exist: $SOURCE_DIR"
  exit 1
}
test -n "$IMAGE_REFERENCE" || {
  echo 'STOP: image reference is required'
  exit 1
}
test -f "$HELM_VALUES_FILE" || {
  echo "STOP: Helm scan values do not exist: $HELM_VALUES_FILE"
  exit 1
}

install -d "$REPORT_DIR"

echo 'TRIVY_GATE: scanning source secrets'
trivy filesystem \
  --cache-dir "$TRIVY_CACHE_DIR" \
  --scanners secret \
  --severity UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL \
  --exit-code 1 \
  --skip-dirs .git \
  --skip-dirs .venv \
  --skip-dirs .pytest_cache \
  --format json \
  --output "${REPORT_DIR}/filesystem-secrets.json" \
  --timeout 10m \
  "$SOURCE_DIR"

echo 'TRIVY_GATE: scanning HIGH and CRITICAL IaC misconfigurations'
trivy filesystem \
  --cache-dir "$TRIVY_CACHE_DIR" \
  --scanners misconfig \
  --severity HIGH,CRITICAL \
  --exit-code 1 \
  --helm-values "$HELM_VALUES_FILE" \
  --skip-dirs .git \
  --skip-dirs .venv \
  --skip-dirs .pytest_cache \
  --format json \
  --output "${REPORT_DIR}/filesystem-misconfigurations.json" \
  --timeout 10m \
  "$SOURCE_DIR"

echo 'TRIVY_REPORT: recording source dependency vulnerabilities'
trivy filesystem \
  --cache-dir "$TRIVY_CACHE_DIR" \
  --scanners vuln \
  --severity HIGH,CRITICAL \
  --ignore-unfixed \
  --exit-code 0 \
  --skip-dirs .git \
  --skip-dirs .venv \
  --skip-dirs .pytest_cache \
  --format json \
  --output "${REPORT_DIR}/filesystem-vulnerabilities.json" \
  --timeout 10m \
  "$SOURCE_DIR"

echo 'TRIVY_REPORT: recording HIGH and CRITICAL image vulnerabilities'
trivy image \
  --cache-dir "$TRIVY_CACHE_DIR" \
  --image-src docker \
  --scanners vuln \
  --severity HIGH,CRITICAL \
  --ignore-unfixed \
  --exit-code 0 \
  --format json \
  --output "${REPORT_DIR}/image-vulnerabilities.json" \
  --timeout 10m \
  "$IMAGE_REFERENCE"

echo 'TRIVY_GATE: blocking fixed CRITICAL image vulnerabilities'
trivy image \
  --cache-dir "$TRIVY_CACHE_DIR" \
  --image-src docker \
  --scanners vuln \
  --severity CRITICAL \
  --ignore-unfixed \
  --exit-code 1 \
  --format json \
  --output "${REPORT_DIR}/image-critical-gate.json" \
  --timeout 10m \
  "$IMAGE_REFERENCE"

echo 'PASS: Trivy Secret、IaC和CRITICAL镜像漏洞质量门禁通过'
