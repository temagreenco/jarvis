#!/usr/bin/env bash
set -euo pipefail

MINIO_ROOT_USER="${MINIO_ROOT_USER:-minioadmin}"
MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:-minioadmin}"
MINIO_BUCKET="${MINIO_BUCKET:-jarvis}"

MC_HOST_LOCAL="http://${MINIO_ROOT_USER}:${MINIO_ROOT_PASSWORD}@minio:9000"
docker compose run --rm -e MC_HOST_local="$MC_HOST_LOCAL" minio-mc mb -p "local/${MINIO_BUCKET}" || true
docker compose run --rm -e MC_HOST_local="$MC_HOST_LOCAL" minio-mc ls local
