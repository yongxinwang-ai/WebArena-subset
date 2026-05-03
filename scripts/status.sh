#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

JOB_ID="${1:-}"
RUN_PATH="${2:-}"

if [[ -n "${JOB_ID}" ]]; then
  squeue -j "${JOB_ID}" -o '%.18i %.9P %.40j %.8T %.10M %.9l %.20R' || true
fi

if [[ -n "${RUN_PATH}" ]]; then
  "${REPO_ROOT}/scripts/summarize_results.py" "${RUN_PATH}"
fi

