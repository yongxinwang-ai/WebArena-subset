#!/usr/bin/env bash
set -euo pipefail

: "${TASK_ID:?TASK_ID is required}"
: "${TASK_GOAL:?TASK_GOAL is required}"
: "${START_URL:?START_URL is required}"
: "${OUTPUT_DIR:?OUTPUT_DIR is required}"
: "${MODEL:?MODEL is required}"
: "${BASE_URL:?BASE_URL is required}"
: "${API_KEY:?API_KEY is required}"

RUNNER="${OPENCLAW_BROWSER_USE_RUNNER:-/mnt/weka/home/yongxin.wang/workspace/Data/Online-Mind2Web/scripts/run_openclaw_online_mind2web.mjs}"
OPENCLAW_ROOT="${OPENCLAW_ROOT:-/mnt/weka/home/yongxin.wang/workspace/Data/openclaw-browser-use}"
TASK_JSON="${OUTPUT_DIR}/openclaw_browser_use_task.json"
RAW_OUTPUT_DIR="${OUTPUT_DIR}/openclaw_browser_use_raw"
MAX_STEPS="${MAX_STEPS:-50}"
MAX_COMPLETION_TOKENS="${MAX_COMPLETION_TOKENS:-${MAX_TOKENS:-32768}}"
TEMPERATURE="${TEMPERATURE:-0}"
BROWSER_USE_MODE="${BROWSER_USE_MODE:-local}"
HEADLESS="${HEADLESS:-true}"

mkdir -p "${OUTPUT_DIR}" "${RAW_OUTPUT_DIR}"

export OPENAI_MODEL="${MODEL}"
export OPENAI_BASE_URL="${BASE_URL}"
export OPENAI_API_KEY="${API_KEY}"
export BROWSER_USE_LLM_MODEL="${MODEL}"
export BROWSER_USE_LLM_BASE_URL="${BASE_URL}"
export BROWSER_USE_LLM_API_KEY="${API_KEY}"
export BROWSER_USE_MAX_COMPLETION_TOKENS="${MAX_COMPLETION_TOKENS}"
export BROWSER_USE_LLM_TEMPERATURE="${TEMPERATURE}"
export BROWSER_USE_LLM_TIMEOUT="${BROWSER_USE_LLM_TIMEOUT:-180}"
export BROWSER_USE_MAX_STEPS="${MAX_STEPS}"
export BROWSER_USE_HEADLESS="${HEADLESS}"

python3 - "${TASK_JSON}" <<'PY'
import json
import os
import sys

task = {
    "task_id": os.environ["TASK_ID"],
    "start_url": os.environ["START_URL"],
    "website": os.environ["START_URL"],
    "task": os.environ["TASK_GOAL"],
    "confirmed_task": os.environ["TASK_GOAL"],
    "source": "webarena-domain50",
    "bucket": os.environ.get("BUCKET"),
    "sites": os.environ.get("SITES", "").split(),
}

with open(sys.argv[1], "w", encoding="utf-8") as f:
    json.dump([task], f, ensure_ascii=False, indent=2)
    f.write("\n")
PY

cmd=(
  node --import tsx "${RUNNER}"
  --openclaw-root "${OPENCLAW_ROOT}"
  --tasks-json "${TASK_JSON}"
  --output-dir "${RAW_OUTPUT_DIR}"
  --model "${MODEL}"
  --base-url "${BASE_URL}"
  --api-key "${API_KEY}"
  --max-steps "${MAX_STEPS}"
  --max-completion-tokens "${MAX_COMPLETION_TOKENS}"
  --temperature "${TEMPERATURE}"
  --browser-use-mode "${BROWSER_USE_MODE}"
  --force-browser-use
)

if [[ "${HEADLESS}" == "true" ]]; then
  cmd+=(--headless)
else
  cmd+=(--no-headless)
fi

(
  cd "${OPENCLAW_ROOT}"
  "${cmd[@]}"
)

RESULT_PATH="${RAW_OUTPUT_DIR}/${TASK_ID}/result.json"
if [[ -s "${RESULT_PATH}" ]]; then
  cp "${RESULT_PATH}" "${OUTPUT_DIR}/openclaw_browser_use_result.json"
fi
