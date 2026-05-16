#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python}"
if [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
fi

export PYTHONPATH="${PWD}/src:${PYTHONPATH:-}"
exec "${PYTHON_BIN}" -m airp.workers.temporal_worker
