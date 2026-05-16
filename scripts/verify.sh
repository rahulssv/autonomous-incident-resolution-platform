#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python}"
RUFF_BIN="${RUFF_BIN:-ruff}"

if [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
fi

if [[ -x ".venv/bin/ruff" ]]; then
  RUFF_BIN=".venv/bin/ruff"
fi

export PYTHONPATH="${PWD}/src:${PYTHONPATH:-}"

"${PYTHON_BIN}" -m compileall -q src tests
"${RUFF_BIN}" check src tests
"${PYTHON_BIN}" -m pytest
