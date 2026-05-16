#!/usr/bin/env bash
set -euo pipefail

export PYTHONPATH="${PWD}/src:${PYTHONPATH:-}"

PYTHON_BIN="${PYTHON_BIN:-python}"
if [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
fi

exec "${PYTHON_BIN}" -m airp.workers.alert_consumer

