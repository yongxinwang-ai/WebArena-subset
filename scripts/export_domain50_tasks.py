#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.resources
import json
import os
from pathlib import Path
from typing import Any


URL_KEYS = {
    "__GITLAB__": "gitlab",
    "__REDDIT__": "reddit",
    "__SHOPPING__": "shopping",
    "__SHOPPING_ADMIN__": "shopping_admin",
    "__WIKIPEDIA__": "wikipedia",
    "__MAP__": "map",
}


def webarena_urls(base_url: str) -> dict[str, str]:
    return {
        "shopping": os.environ.get("WA_SHOPPING", f"{base_url}:8082/"),
        "shopping_admin": os.environ.get("WA_SHOPPING_ADMIN", f"{base_url}:8083/admin"),
        "reddit": os.environ.get("WA_REDDIT", f"{base_url}:8080"),
        "gitlab": os.environ.get("WA_GITLAB", f"{base_url}:9001"),
        "wikipedia": os.environ.get(
            "WA_WIKIPEDIA",
            f"{base_url}:8081/wikipedia_en_all_maxi_2022-05/A/User:The_other_Kiwix_guy/Landing",
        ),
        "map": os.environ.get("WA_MAP", f"{base_url}:443"),
        "homepage": os.environ.get("WA_HOMEPAGE", f"{base_url}:80"),
    }


def load_webarena_configs(base_url: str) -> dict[int, dict[str, Any]]:
    import webarena

    raw = importlib.resources.files(webarena).joinpath("test.raw.json").read_text()
    urls = webarena_urls(base_url)
    for pattern, url_key in URL_KEYS.items():
        raw = raw.replace(pattern, urls[url_key])
    return {int(item["task_id"]): item for item in json.loads(raw)}


def load_task_ids(path: Path) -> list[int]:
    task_ids: list[int] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        task_ids.append(int(line.split()[0]))
    return task_ids


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", type=Path, default=repo_root / "configs/domain50_tasks.txt")
    parser.add_argument("--meta", type=Path, default=repo_root / "configs/domain50_meta.json")
    parser.add_argument("--output", type=Path, default=repo_root / "configs/domain50_tasks_expanded.jsonl")
    parser.add_argument("--webarena-base-url", default=os.environ.get("WEBARENA_BASE_URL", "http://18.117.39.199"))
    args = parser.parse_args()

    task_ids = load_task_ids(args.tasks)
    task_meta = {
        int(item["task_id"]): item
        for item in json.loads(args.meta.read_text(encoding="utf-8")).get("tasks", [])
    }
    configs = load_webarena_configs(args.webarena_base_url)

    rows: list[dict[str, Any]] = []
    for task_id in task_ids:
        config = configs[task_id]
        meta = task_meta.get(task_id, {})
        rows.append(
            {
                "task_id": task_id,
                "task_name": f"webarena.{task_id}",
                "bucket": meta.get("bucket", "unknown"),
                "sites": config.get("sites", []),
                "start_url": config.get("start_url", ""),
                "goal": config.get("intent", ""),
                "eval_types": meta.get("eval_types", ""),
                "depends_on": meta.get("depends_on", ""),
                "webarena_base_url": args.webarena_base_url,
            }
        )

    args.output.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    print(f"Wrote {len(rows)} tasks to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
