# WebArena Domain50 Eval

Reusable BrowserGym/WebArena evaluation package for a 50-task, domain-balanced text-only subset.

The AWS WebArena node is kept as the current deployment:

```text
http://18.117.39.199
```

## Contents

- `configs/domain50_tasks.txt`: 50 WebArena task ids.
- `configs/domain50_tasks_expanded.jsonl`: expanded task metadata for external harnesses.
- `configs/domain50_meta.json`: selection policy and per-task domain metadata.
- `configs/webarena_env_aws.sh`: WebArena service URLs for the current AWS node.
- `configs/harnesses.example.json`: BrowserGym/OpenClaw/browser-use adapter examples.
- `harness/run_webarena_text_eval.py`: OpenAI-compatible text-only BrowserGym agent harness.
- `slurm/run_webarena_parallel_array.sbatch`: Slurm array wrapper.
- `scripts/submit_eval.sh`: team-facing submit command.
- `scripts/summarize_results.py`: aggregate success rate and domain-level results.
- `scripts/export_domain50_tasks.py`: export WebArena task goals/start URLs into JSONL.
- `scripts/run_external_harness.py`: run the same 50 tasks through external harness commands.
- `docs/harness_adapters.md`: notes for OpenClaw, OpenClaw+browser-use, and Browser Use Cloud adapters.
- `results/gpt_5_4_headless_20260502_summary.json`: baseline summary from the initial `gpt-5.4` run.

## Subset

The subset uses WebArena `test` split and covers:

- `shopping_admin`: 8 tasks
- `shopping`: 8 tasks
- `gitlab`: 8 tasks
- `map`: 8 tasks
- `reddit`: 8 tasks
- `wikipedia_or_cross_site`: 10 tasks

Selection prioritizes tasks from the prior URL-fixed `glm-5` run without infra/runtime errors, then fills missing coverage from official WebArena metadata.

## Run

Use an OpenAI-compatible chat-completions endpoint. Do not commit API keys.

```bash
cd /mnt/weka/home/yongxin.wang/workspace/Data/webarena-domain50-eval
source configs/env.example
export API_KEY="..."
export WEBARENA_EVAL_API_KEY="${API_KEY}"

MODEL="gpt-5.4" \
BASE_URL="https://api.openai-next.com/v1" \
API_KEY="${API_KEY}" \
WEBARENA_EVAL_MODEL="gpt-5.4" \
WEBARENA_EVAL_BASE_URL="https://api.openai-next.com/v1" \
WEBARENA_EVAL_API_KEY="${API_KEY}" \
scripts/submit_eval.sh
```

Defaults:

- `MAX_STEPS=50`
- `MAX_TOKENS=1024`
- `TASKS_PER_SHARD=5`
- `ARRAY_CONCURRENCY=1`
- `HEADLESS=true`
- `WEBARENA_BASE_URL=http://18.117.39.199`

Keep `ARRAY_CONCURRENCY=1` unless you deploy independent WebArena state, because tasks share the same AWS site databases.

## Other Harnesses

BrowserGym is the authoritative path for official WebArena reward. External harnesses can still run the same 50 tasks by consuming `configs/domain50_tasks_expanded.jsonl`.

```bash
scripts/export_domain50_tasks.py

scripts/run_external_harness.py \
  --output-root runs/openclaw_pure_gpt54 \
  --harness-name openclaw_pure \
  --command 'cd "$OPENCLAW_REPO" && ${OPENCLAW_CMD:-openclaw} run --task "$TASK_GOAL" --start-url "$START_URL" --output "$OUTPUT_DIR"'
```

External harness outputs are normalized into per-task `result.json`, but `reward` is `null` by default because many WebArena tasks require official page-state, URL, or programmatic HTML evaluators. See `docs/harness_adapters.md`.

## Monitor

```bash
scripts/status.sh <job_id> <run_path>
```

Example:

```bash
scripts/status.sh 1595795 runs/gpt-5.4_20260502_163300
```

Or aggregate a completed/current run directly:

```bash
scripts/summarize_results.py <run_path> --write
```

## Baseline

Initial `gpt-5.4` headless run on this subset:

```text
success: 20 / 50
success_rate: 40.0%
```

Per-bucket success counts:

```text
gitlab: 4 / 8
map: 4 / 8
reddit: 6 / 8
shopping: 3 / 8
shopping_admin: 2 / 8
wikipedia_or_cross_site: 1 / 10
```

## Notes

- WebArena fuzzy evaluators use `WEBARENA_EVAL_MODEL`, `WEBARENA_EVAL_BASE_URL`, and `WEBARENA_EVAL_API_KEY`.
- The harness accepts plain BrowserGym actions such as `click("12")`, `fill("45", "text")`, and `send_msg_to_user("answer")`.
- The harness also includes recovery for common malformed tool-call outputs and fail-fast for repeated identical action errors.
