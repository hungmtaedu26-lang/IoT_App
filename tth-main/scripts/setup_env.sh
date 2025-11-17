#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="${1:-venv}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PATH="${PROJECT_ROOT}/${ENV_NAME}"

if [ ! -d "${VENV_PATH}" ]; then
  echo "[setup] Creating virtual environment at ${VENV_PATH}"
  python -m venv "${VENV_PATH}"
fi

source "${VENV_PATH}/bin/activate"

python -m ensurepip --upgrade
pip install --upgrade pip
pip install -r "${PROJECT_ROOT}/requirements.txt"

echo "[setup] Virtual environment ready. Activate with:"
echo "    source ${VENV_PATH}/bin/activate"
