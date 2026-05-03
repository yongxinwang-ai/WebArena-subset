#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def load_bucket_map(meta_path: Path) -> dict[int, dict[str, Any]]:
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    return {int(item["task_id"]): item for item in meta.get("tasks", [])}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        item = json.loads(line)
        item["_result_path"] = str(path)
        records.append(item)
    return records


def find_result_files(path: Path) -> list[Path]:
    if path.name.startswith("webarena.") and (path / "result.json").exists():
        return [path / "result.json"]
    return sorted(path.glob("**/webarena.*/result.json"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_path", type=Path, help="Run root or run label directory.")
    parser.add_argument(
        "--meta",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "configs/domain50_meta.json",
    )
    parser.add_argument("--write", action="store_true", help="Write aggregate JSON/JSONL files.")
    args = parser.parse_args()

    task_meta = load_bucket_map(args.meta)
    results: list[dict[str, Any]] = []
    jsonl_inputs: list[Path] = []
    if args.run_path.is_file() and args.run_path.suffix == ".jsonl":
        jsonl_inputs = [args.run_path]
    elif args.run_path.is_dir():
        jsonl_inputs = sorted(args.run_path.glob("*_results.jsonl"))

    if jsonl_inputs:
        for path in jsonl_inputs:
            try:
                results.extend(load_jsonl(path))
            except Exception as exc:
                results.append(
                    {"status": "parse_error", "error": f"{type(exc).__name__}: {exc}", "_result_path": str(path)}
                )
    else:
        for path in find_result_files(args.run_path):
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                item = {"status": "parse_error", "error": f"{type(exc).__name__}: {exc}"}
            item["_result_path"] = str(path)
            results.append(item)

    for item in results:
        task_id = int(item.get("task_id", -1))
        item["_bucket"] = task_meta.get(task_id, {}).get("bucket", "unknown")
        item["_sites"] = task_meta.get(task_id, {}).get("sites", "unknown")

    status_counts = Counter(item.get("status", "unknown") for item in results)
    bucket_counts: dict[str, Counter[str]] = defaultdict(Counter)
    site_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for item in results:
        status = item.get("status", "unknown")
        bucket_counts[item["_bucket"]][status] += 1
        for site in str(item["_sites"]).split():
            site_counts[site][status] += 1

    total = len(results)
    success = status_counts.get("success", 0)
    summary = {
        "run_path": str(args.run_path),
        "total": total,
        "success": success,
        "success_rate": success / total if total else 0.0,
        "status_counts": dict(status_counts.most_common()),
        "bucket_counts": {key: dict(value.most_common()) for key, value in sorted(bucket_counts.items())},
        "site_counts": {key: dict(value.most_common()) for key, value in sorted(site_counts.items())},
    }

    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.write:
        out_dir = args.run_path
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "all_results.jsonl").write_text(
            "".join(
                json.dumps(item, ensure_ascii=False) + "\n"
                for item in sorted(results, key=lambda value: int(value.get("task_id", -1)))
            ),
            encoding="utf-8",
        )
        (out_dir / "aggregate_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
