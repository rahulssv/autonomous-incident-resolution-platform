#!/usr/bin/env bash
set -euo pipefail

export PYTHONPATH="${PYTHONPATH:-}:src"
exec uvicorn airp.main:app --host 0.0.0.0 --port "${PORT:-8080}" --reload

