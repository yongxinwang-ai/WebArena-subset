# Harness Adapters

This repo has one authoritative harness today:

- `browsergym_text`: runs inside BrowserGym and receives WebArena official reward.

Other harnesses can be run on the same 50 tasks if they consume `configs/domain50_tasks_expanded.jsonl`.
That file contains:

- `task_id`
- `task_name`
- `bucket`
- `sites`
- `start_url`
- `goal`
- `eval_types`

## Reward Caveat

WebArena reward is not just a final-answer judge for every task. Many tasks use page state, URL match, or programmatic HTML evaluators.
Therefore an external browser harness such as OpenClaw or browser-use cannot automatically get official WebArena reward unless it is integrated with BrowserGym/WebArena or exports enough state for a custom evaluator.

For non-BrowserGym harnesses, use this repo to:

- run the same task subset,
- collect trajectories and outputs,
- normalize per-task `result.json`,
- optionally run a separate judge over the final answer/trajectory.

## Export Expanded Tasks

```bash
cd /mnt/weka/home/yongxin.wang/workspace/Data/webarena-domain50-eval
/mnt/weka/home/yongxin.wang/workspace/Data/.venvs/browsergym_webarena_py310/bin/python \
  scripts/export_domain50_tasks.py
```

## Generic External Harness Runner

The generic runner executes a shell command once per task. It sets:

- `TASK_ID`
- `TASK_NAME`
- `TASK_GOAL`
- `START_URL`
- `SITES`
- `BUCKET`
- `OUTPUT_DIR`
- `WEBARENA_BASE_URL`

Example dry adapter:

```bash
scripts/run_external_harness.py \
  --output-root runs/example_external \
  --harness-name example \
  --command 'printf "%s\n%s\n" "$TASK_GOAL" "$START_URL" > "$OUTPUT_DIR/final_answer.txt"'
```

OpenClaw template:

```bash
export OPENCLAW_REPO=/mnt/weka/home/yongxin.wang/workspace/Data/openclaw-openclaw-only
export MODEL=gpt-5.4
export BASE_URL=https://api.openai-next.com/v1
export API_KEY=...

scripts/run_external_harness.py \
  --output-root runs/openclaw_pure_gpt54 \
  --harness-name openclaw_pure \
  --command 'cd "$OPENCLAW_REPO" && ${OPENCLAW_CMD:-openclaw} run --task "$TASK_GOAL" --start-url "$START_URL" --output "$OUTPUT_DIR"'
```

OpenClaw + browser-use template:

```bash
export OPENCLAW_BROWSER_USE_REPO=/mnt/weka/home/yongxin.wang/workspace/Data/openclaw-browser-use
export MODEL=gpt-5.4
export BASE_URL=https://api.openai-next.com/v1
export API_KEY=...

scripts/run_external_harness.py \
  --output-root runs/openclaw_browser_use_gpt54 \
  --harness-name openclaw_browser_use \
  --command 'cd "$OPENCLAW_BROWSER_USE_REPO" && ${OPENCLAW_CMD:-openclaw} run --task "$TASK_GOAL" --start-url "$START_URL" --output "$OUTPUT_DIR"'
```

Browser-use Cloud template:

```bash
export BROWSER_USE_API_KEY=...
export BROWSER_USE_CLOUD_SCRIPT=/path/to/your/browser_use_cloud_runner.py

scripts/run_external_harness.py \
  --output-root runs/browser_use_cloud_gpt54 \
  --harness-name browser_use_cloud \
  --command 'python "$BROWSER_USE_CLOUD_SCRIPT" --task "$TASK_GOAL" --start-url "$START_URL" --output-dir "$OUTPUT_DIR"'
```
