#!/bin/bash
# Run a shard of WebArena tasks. For local vLLM servers, pass ENDPOINT_JSON and
# the job waits until the server writes its endpoint metadata.

#SBATCH --job-name=webarena_eval_array
#SBATCH --partition=cpuonly
#SBATCH --qos=cpuonly
#SBATCH --array=0-101%12
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=24:00:00
#SBATCH --output=/mnt/weka/home/yongxin.wang/workspace/Data/logs/webarena_eval_%x_%A_%a.out
#SBATCH --error=/mnt/weka/home/yongxin.wang/workspace/Data/logs/webarena_eval_%x_%A_%a.err

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

ROOT="${ROOT:-${REPO_ROOT}}"
VENV="${VENV:-/mnt/weka/home/yongxin.wang/workspace/Data/.venvs/browsergym_webarena_py310}"
HARNESS="${HARNESS:-${ROOT}/harness/run_webarena_text_eval.py}"
WEBARENA_ENV_FILE="${WEBARENA_ENV_FILE:-${ROOT}/configs/webarena_env_aws.sh}"
RUN_ROOT="${RUN_ROOT:?RUN_ROOT is required}"
RUN_LABEL="${RUN_LABEL:?RUN_LABEL is required}"
TASKS_PER_SHARD="${TASKS_PER_SHARD:-8}"
TOTAL_TASKS="${TOTAL_TASKS:-812}"
TASK_FILE="${TASK_FILE:-}"
MAX_STEPS="${MAX_STEPS:-30}"
MAX_TOKENS="${MAX_TOKENS:-32768}"
REQUEST_TIMEOUT="${REQUEST_TIMEOUT:-180}"
HEADLESS="${HEADLESS:-true}"
TEMPERATURE="${TEMPERATURE:-0}"
USE_AXTREE="${USE_AXTREE:-true}"
USE_HTML="${USE_HTML:-false}"
COERCE_PLAIN_FINAL_ANSWER="${COERCE_PLAIN_FINAL_ANSWER:-false}"
MAX_REPEATED_ACTION_ERRORS="${MAX_REPEATED_ACTION_ERRORS:-0}"
EXTRA_BODY_JSON="${EXTRA_BODY_JSON:-}"
WEBARENA_RESET_LOCK_PATH="${WEBARENA_RESET_LOCK_PATH:-}"
ENDPOINT_WAIT_SECONDS="${ENDPOINT_WAIT_SECONDS:-3600}"

MODEL="${MODEL:-}"
BASE_URL="${BASE_URL:-}"
API_KEY="${API_KEY:-}"

mkdir -p "${RUN_ROOT}/${RUN_LABEL}/shards"

if [[ -n "${ENDPOINT_JSON:-}" ]]; then
  waited=0
  while [[ ! -s "${ENDPOINT_JSON}" ]]; do
    if (( waited >= ENDPOINT_WAIT_SECONDS )); then
      echo "Timed out waiting for endpoint json: ${ENDPOINT_JSON}" >&2
      exit 13
    fi
    sleep 10
    waited=$((waited + 10))
  done
  read -r MODEL BASE_URL API_KEY < <(
    python - "${ENDPOINT_JSON}" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
print(data["model"], data["base_url"], data.get("api_key", ""))
PY
  )
fi

if [[ -z "${MODEL}" || -z "${BASE_URL}" || -z "${API_KEY}" ]]; then
  echo "MODEL, BASE_URL, and API_KEY are required unless ENDPOINT_JSON is set." >&2
  exit 2
fi

START=$((SLURM_ARRAY_TASK_ID * TASKS_PER_SHARD))
END=$((START + TASKS_PER_SHARD - 1))
if [[ -n "${TASK_FILE}" ]]; then
  TOTAL_TASKS=$(wc -l < "${TASK_FILE}")
fi

if (( START >= TOTAL_TASKS )); then
  echo "Shard ${SLURM_ARRAY_TASK_ID} starts after TOTAL_TASKS=${TOTAL_TASKS}; nothing to do."
  exit 0
fi
if (( END >= TOTAL_TASKS )); then
  END=$((TOTAL_TASKS - 1))
fi

if [[ -n "${TASK_FILE}" ]]; then
  TASK_SELECTOR=$(
    sed -n "$((START + 1)),$((END + 1))p" "${TASK_FILE}" \
      | awk 'NF && $1 !~ /^#/ {print $1}' \
      | paste -sd, -
  )
else
  TASK_SELECTOR="${START}-${END}"
fi

if [[ -z "${TASK_SELECTOR}" ]]; then
  echo "Shard ${SLURM_ARRAY_TASK_ID} has no task ids after reading TASK_FILE=${TASK_FILE}; nothing to do."
  exit 0
fi

SHARD_DIR="${RUN_ROOT}/${RUN_LABEL}/shards/shard_${SLURM_ARRAY_TASK_ID}"
mkdir -p "${SHARD_DIR}"

source "${VENV}/bin/activate"
source "${WEBARENA_ENV_FILE}" > "${SHARD_DIR}/webarena_env.log"

export WEBARENA_EVAL_MODEL="${WEBARENA_EVAL_MODEL:-glm-5}"
export WEBARENA_EVAL_BASE_URL="${WEBARENA_EVAL_BASE_URL:-https://api.openai-next.com/v1}"
export WEBARENA_EVAL_API_KEY="${WEBARENA_EVAL_API_KEY:-${API_KEY}}"
export WEBARENA_EVAL_TIMEOUT="${WEBARENA_EVAL_TIMEOUT:-180}"
export OPENAI_API_KEY="${OPENAI_API_KEY:-${WEBARENA_EVAL_API_KEY}}"
export OPENAI_BASE_URL="${OPENAI_BASE_URL:-${WEBARENA_EVAL_BASE_URL}}"

CMD=(
  python "${HARNESS}"
  --output-root "${SHARD_DIR}"
  --task-ids "${TASK_SELECTOR}"
  --model "${MODEL}"
  --base-url "${BASE_URL}"
  --api-key "${API_KEY}"
  --max-steps "${MAX_STEPS}"
  --max-tokens "${MAX_TOKENS}"
  --request-timeout "${REQUEST_TIMEOUT}"
  --temperature "${TEMPERATURE}"
  --headless "${HEADLESS}"
  --use-axtree "${USE_AXTREE}"
  --use-html "${USE_HTML}"
)

if [[ -n "${EXTRA_BODY_JSON}" ]]; then
  CMD+=(--extra-body-json "${EXTRA_BODY_JSON}")
fi
if [[ -n "${WEBARENA_RESET_LOCK_PATH}" ]]; then
  CMD+=(--reset-lock-path "${WEBARENA_RESET_LOCK_PATH}")
fi
if [[ "${COERCE_PLAIN_FINAL_ANSWER}" == "true" ]]; then
  CMD+=(--coerce-plain-final-answer)
fi
if [[ "${MAX_REPEATED_ACTION_ERRORS}" != "0" ]]; then
  CMD+=(--max-repeated-action-errors "${MAX_REPEATED_ACTION_ERRORS}")
fi

echo "run_label=${RUN_LABEL} shard=${SLURM_ARRAY_TASK_ID} tasks=${TASK_SELECTOR} model=${MODEL} base_url=${BASE_URL}"
if [[ "${HEADLESS}" == "false" ]]; then
  xvfb-run -a -s "-screen 0 1920x1080x24" "${CMD[@]}"
else
  "${CMD[@]}"
fi
