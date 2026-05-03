#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any


def load_tasks(path: Path) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            tasks.append(json.loads(line))
    return tasks


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", type=Path, default=repo_root / "configs/domain50_tasks_expanded.jsonl")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--harness-name", required=True)
    parser.add_argument(
        "--command",
        required=True,
        help="Shell command to run per task. The task is provided through env vars such as TASK_GOAL, START_URL, and OUTPUT_DIR.",
    )
    parser.add_argument("--task-ids", default=None, help="Optional comma-separated task ids to run.")
    parser.add_argument("--timeout", type=float, default=1800)
    parser.add_argument("--fail-fast", action="store_true")
    args = parser.parse_args()

    selected_ids = None
    if args.task_ids:
        selected_ids = {int(part.strip()) for part in args.task_ids.split(",") if part.strip()}

    tasks = load_tasks(args.tasks)
    if selected_ids is not None:
        tasks = [task for task in tasks if int(task["task_id"]) in selected_ids]

    args.output_root.mkdir(parents=True, exist_ok=True)
    summary_path = args.output_root / "summary.jsonl"

    for task in tasks:
        task_id = int(task["task_id"])
        task_dir = args.output_root / f"webarena.{task_id}"
        task_dir.mkdir(parents=True, exist_ok=True)
        started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        env = os.environ.copy()
        env.update(
            {
                "TASK_ID": str(task_id),
                "TASK_NAME": str(task.get("task_name", f"webarena.{task_id}")),
                "TASK_GOAL": str(task.get("goal", "")),
                "START_URL": str(task.get("start_url", "")),
                "SITES": " ".join(task.get("sites", [])),
                "BUCKET": str(task.get("bucket", "unknown")),
                "OUTPUT_DIR": str(task_dir),
                "WEBARENA_BASE_URL": str(task.get("webarena_base_url", "")),
            }
        )
        command = args.command
        (task_dir / "task.json").write_text(json.dumps(task, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (task_dir / "command.sh").write_text(command + "\n", encoding="utf-8")

        try:
            completed = subprocess.run(
                command,
                shell=True,
                env=env,
                cwd=str(task_dir),
                text=True,
                capture_output=True,
                timeout=args.timeout,
            )
            status = "success" if completed.returncode == 0 else "error"
            error = None if completed.returncode == 0 else f"command exited with code {completed.returncode}"
            stdout = completed.stdout
            stderr = completed.stderr
            returncode = completed.returncode
        except subprocess.TimeoutExpired as exc:
            status = "error"
            error = f"TimeoutExpired: {exc}"
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            returncode = None

        (task_dir / "stdout.txt").write_text(stdout, encoding="utf-8")
        (task_dir / "stderr.txt").write_text(stderr, encoding="utf-8")
        result = {
            "task_id": task_id,
            "task_name": task.get("task_name", f"webarena.{task_id}"),
            "harness": args.harness_name,
            "status": status,
            "reward": None,
            "needs_judge": True,
            "returncode": returncode,
            "error": error,
            "started_at": started_at,
            "ended_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "bucket": task.get("bucket", "unknown"),
            "sites": task.get("sites", []),
            "start_url": task.get("start_url", ""),
            "goal": task.get("goal", ""),
        }
        (task_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        with summary_path.open("a", encoding="utf-8") as summary:
            summary.write(json.dumps(result, ensure_ascii=False) + "\n")
        print(f"task={task_id} harness={args.harness_name} status={status} error={error}", flush=True)

        if args.fail_fast and status == "error":
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
