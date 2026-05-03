#!/usr/bin/env python3
import argparse
import contextlib
import fcntl
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import gymnasium as gym
import openai


def str2bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    normalized = value.lower()
    if normalized in {"1", "true", "t", "yes", "y"}:
        return True
    if normalized in {"0", "false", "f", "no", "n"}:
        return False
    raise argparse.ArgumentTypeError(f"Invalid boolean value: {value}")


def parse_json_arg(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    return json.loads(value)


def parse_task_ids(raw: str | None, task_file: Path | None, limit: int | None) -> list[int]:
    task_ids: list[int] = []
    if raw:
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                start, end = part.split("-", 1)
                task_ids.extend(range(int(start), int(end) + 1))
            else:
                task_ids.append(int(part))

    if task_file:
        for line in task_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            task_ids.append(int(line.split()[0]))

    if not task_ids:
        task_ids = list(range(812))
    if limit is not None:
        task_ids = task_ids[:limit]
    return task_ids


ACTION_NAMES = (
    "noop",
    "send_msg_to_user",
    "report_infeasible",
    "click",
    "dblclick",
    "fill",
    "press",
    "scroll",
    "goto",
    "go_back",
    "go_forward",
    "new_tab",
    "tab_focus",
    "tab_close",
    "hover",
    "focus",
    "clear",
    "select_option",
    "drag_and_drop",
    "upload_file",
)


def quote_arg(value: Any) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def first_arg(args: dict[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in args and args[name] is not None:
            return args[name]
    return default


def tool_call_json_to_action(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None

    name: str | None = None
    args: Any = None
    if "name" in payload and ("arguments" in payload or "args" in payload):
        name = str(payload["name"])
        args = payload.get("arguments", payload.get("args"))
    elif "name" in payload:
        name = str(payload["name"])
        args = {key: value for key, value in payload.items() if key not in {"name", "description"}}
    else:
        matching = [(key, value) for key, value in payload.items() if key in ACTION_NAMES]
        if len(matching) == 1:
            name, args = matching[0]

    if not name:
        return None
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {"text": args}
    if args is None:
        args = {}
    if not isinstance(args, dict):
        if name in {"click", "dblclick", "hover", "focus", "clear"}:
            args = {"bid": args}
        elif name in {"tab_focus"}:
            args = {"index": args}
        elif name in {"goto"}:
            args = {"url": args}
        elif name in {"send_msg_to_user", "report_infeasible"}:
            args = {"text": args}
        else:
            args = {"value": args}

    if name in {"noop", "go_back", "go_forward", "new_tab", "tab_close"}:
        return f"{name}()"
    if name in {"send_msg_to_user", "report_infeasible"}:
        text = first_arg(args, "text", "message", "reason", "value", default="")
        return f"{name}({quote_arg(text)})"
    if name == "goto":
        url = first_arg(args, "url", "href", "value")
        return f"goto({quote_arg(url)})" if url is not None else None
    if name == "tab_focus":
        index = first_arg(args, "index", "tab_index", "page_index")
        return f"tab_focus({int(index)})" if index is not None else None
    if name in {"click", "dblclick", "hover", "focus", "clear"}:
        bid = first_arg(args, "bid", "element_id", "id", "index", "value")
        return f"{name}({quote_arg(bid)})" if bid is not None else None
    if name == "fill":
        bid = first_arg(args, "bid", "element_id", "id", "index")
        value = first_arg(args, "value", "text", "content", "input", default="")
        return f"fill({quote_arg(bid)}, {quote_arg(value)})" if bid is not None else None
    if name == "press":
        bid = first_arg(args, "bid", "element_id", "id", "index")
        key = first_arg(args, "key_comb", "key", "value")
        return f"press({quote_arg(bid)}, {quote_arg(key)})" if bid is not None and key is not None else None
    if name == "scroll":
        delta_x = first_arg(args, "delta_x", "x", default=0)
        delta_y = first_arg(args, "delta_y", "y", "amount", default=0)
        direction = str(args.get("direction", "")).lower()
        if direction in {"up", "north"}:
            delta_y = -abs(float(delta_y) or 500)
        elif direction in {"down", "south"}:
            delta_y = abs(float(delta_y) or 500)
        elif direction in {"left", "west"}:
            delta_x = -abs(float(delta_x) or 500)
        elif direction in {"right", "east"}:
            delta_x = abs(float(delta_x) or 500)
        return f"scroll({float(delta_x)}, {float(delta_y)})"
    if name == "select_option":
        bid = first_arg(args, "bid", "element_id", "id", "index")
        options = first_arg(args, "options", "option", "value")
        return f"select_option({quote_arg(bid)}, {json.dumps(options, ensure_ascii=False)})" if bid is not None else None
    if name == "drag_and_drop":
        from_bid = first_arg(args, "from_bid", "source_bid", "source", "from")
        to_bid = first_arg(args, "to_bid", "target_bid", "target", "to")
        return f"drag_and_drop({quote_arg(from_bid)}, {quote_arg(to_bid)})" if from_bid is not None and to_bid is not None else None
    if name == "upload_file":
        bid = first_arg(args, "bid", "element_id", "id", "index")
        file_value = first_arg(args, "file", "path", "value")
        return f"upload_file({quote_arg(bid)}, {json.dumps(file_value, ensure_ascii=False)})" if bid is not None else None
    return None


def find_action_calls(text: str) -> list[str]:
    """Find action calls while respecting quoted strings and nested parentheses."""
    names = "|".join(re.escape(name) for name in sorted(ACTION_NAMES, key=len, reverse=True))
    pattern = re.compile(rf"\b(?:{names})\s*\(")
    calls: list[str] = []
    for match in pattern.finditer(text):
        start = match.start()
        open_paren = match.end() - 1
        depth = 0
        quote: str | None = None
        escape = False
        for index in range(open_paren, len(text)):
            char = text[index]
            if quote:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == quote:
                    quote = None
                continue

            if char in {"'", '"'}:
                quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    calls.append(text[start : index + 1].strip())
                    break
    return calls


def parse_scalar_token(token: str) -> Any:
    try:
        return json.loads(token)
    except json.JSONDecodeError:
        return token.strip().strip('"\'')


def malformed_tool_call_to_action(text: str) -> str | None:
    """Recover common malformed JSON tool calls, e.g. {"name":"click" {"bid":765}."""
    if "send_msg_to_user(" in text:
        answer = text.split("send_msg_to_user(", 1)[1].strip()
        marker = re.search(r'",\s*"success\s*=|",\s*"files_to_display\s*=', answer)
        if marker:
            answer = answer[: marker.start()]
        answer = answer.strip()
        if answer.endswith(")"):
            answer = answer[:-1].rstrip()
        answer = answer.strip().strip('"')
        if answer:
            return f"send_msg_to_user({quote_arg(answer)})"

    name_match = re.search(r'"name"\s*:\s*"([^"]+)"', text)
    if not name_match:
        return None
    name = name_match.group(1)
    if name not in ACTION_NAMES:
        return None

    args: dict[str, Any] = {}
    keys = (
        "bid",
        "element_id",
        "id",
        "index",
        "url",
        "href",
        "text",
        "message",
        "reason",
        "value",
        "content",
        "input",
        "key",
        "key_comb",
        "delta_x",
        "delta_y",
        "x",
        "y",
        "amount",
        "direction",
        "option",
        "options",
        "from_bid",
        "to_bid",
        "source",
        "target",
        "file",
        "path",
    )
    scalar = r'"(?:\\.|[^"\\])*"|-?\d+(?:\.\d+)?|true|false|null'
    for key in keys:
        match = re.search(rf'"{re.escape(key)}"\s*:\s*({scalar})', text)
        if match:
            args[key] = parse_scalar_token(match.group(1))
    return tool_call_json_to_action({"name": name, "arguments": args})


def extract_action(raw_output: str) -> str:
    tool_calls = re.findall(r"<tool_call>\s*(.*?)\s*</tool_call>", raw_output, re.S)
    for candidate in reversed(tool_calls):
        try:
            action = tool_call_json_to_action(json.loads(candidate))
        except json.JSONDecodeError:
            action = malformed_tool_call_to_action(candidate)
        if action:
            return action

    unclosed_tool_call = raw_output.rsplit("<tool_call>", 1)
    if len(unclosed_tool_call) == 2:
        action = malformed_tool_call_to_action(unclosed_tool_call[1])
        if action:
            return action

    # Treat a fence language only when it is followed by a newline. Without this,
    # ```click("12")``` is misparsed as language="click" and body=("12").
    code_blocks = re.findall(r"```(?:[a-zA-Z0-9_+.-]+[ \t]*\n)?(.*?)```", raw_output, re.S)
    for candidate in reversed(code_blocks):
        try:
            action = tool_call_json_to_action(json.loads(candidate))
        except json.JSONDecodeError:
            action = malformed_tool_call_to_action(candidate)
        if action:
            return action

        function_calls = find_action_calls(candidate)
        if function_calls:
            return function_calls[-1].strip()
        stripped = candidate.strip()
        if stripped:
            return stripped

    function_calls = find_action_calls(raw_output)
    if function_calls:
        return function_calls[-1].strip()
    return raw_output.strip()


def coerce_plain_answer_to_action(raw_output: str, action: str) -> str:
    """Wrap a plain final answer as a BrowserGym chat action when no action is present."""
    stripped = raw_output.strip()
    if not stripped or action != stripped:
        return action
    if find_action_calls(stripped):
        return action
    if "<tool_call" in stripped or "</tool_call>" in stripped:
        return action

    answer = stripped.split("</think>")[-1].strip()
    if not answer:
        answer = stripped
    answer = re.sub(r"\n{3,}", "\n\n", answer)
    if len(answer) > 2000:
        answer = answer[:2000].rstrip()
    return f"send_msg_to_user({quote_arg(answer)})"


def patch_webarena_eval_llm() -> None:
    """Route WebArena's optional LLM fuzzy evaluator to an OpenAI-compatible endpoint."""
    eval_model = os.environ.get("WEBARENA_EVAL_MODEL")
    eval_key = os.environ.get("WEBARENA_EVAL_API_KEY") or os.environ.get("OPENAI_API_KEY")
    eval_base_url = os.environ.get("WEBARENA_EVAL_BASE_URL") or os.environ.get("OPENAI_BASE_URL")
    eval_timeout = float(os.environ.get("WEBARENA_EVAL_TIMEOUT", "180"))
    if not eval_model or not eval_key:
        return

    client = openai.OpenAI(api_key=eval_key, base_url=eval_base_url, timeout=eval_timeout)

    def generate_from_eval_chat_completion(
        messages: list[dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int,
        top_p: float,
        context_length: int,
        stop_token: str | None = None,
    ) -> str:
        response = client.chat.completions.create(
            model=eval_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            stop=[stop_token] if stop_token else None,
        )
        return response.choices[0].message.content or ""

    try:
        import webarena.evaluation_harness.helper_functions as helper_functions

        helper_functions.generate_from_openai_chat_completion = generate_from_eval_chat_completion
    except Exception:
        pass

    try:
        import webarena.llms.providers.openai_utils as openai_utils

        openai_utils.generate_from_openai_chat_completion = generate_from_eval_chat_completion
    except Exception:
        pass


def patch_webarena_login_timeout() -> None:
    """WebArena login pages can be slow under parallel eval load."""
    timeout_ms = int(os.environ.get("WEBARENA_LOGIN_TIMEOUT_MS", "60000"))
    try:
        import browsergym.webarena.instance as instance_module
    except Exception:
        return

    original = instance_module.WebArenaInstance.ui_login
    if getattr(original, "_timeout_patched", False):
        return

    def ui_login_with_longer_timeout(self, site, page):
        try:
            page.context.set_default_timeout(timeout_ms)
            page.context.set_default_navigation_timeout(timeout_ms)
        except Exception:
            pass
        return original(self, site, page)

    ui_login_with_longer_timeout._timeout_patched = True
    instance_module.WebArenaInstance.ui_login = ui_login_with_longer_timeout


class TextOnlyAgent:
    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str | None,
        max_tokens: int,
        temperature: float,
        extra_body: dict[str, Any],
        request_timeout: float,
        use_axtree: bool,
        use_html: bool,
        coerce_plain_final_answer: bool,
    ) -> None:
        from browsergym.core.action.highlevel import HighLevelActionSet

        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.extra_body = extra_body
        self.use_axtree = use_axtree
        self.use_html = use_html
        self.coerce_plain_final_answer = coerce_plain_final_answer
        self.client = (
            openai.OpenAI(api_key=api_key, base_url=base_url, timeout=request_timeout)
            if base_url
            else openai.OpenAI(api_key=api_key, timeout=request_timeout)
        )
        self.action_set = HighLevelActionSet(
            subsets=["chat", "tab", "nav", "bid", "infeas"],
            strict=False,
            multiaction=False,
            demo_mode="off",
        )
        self.history: list[str] = []

    def _obs_text(self, obs: dict[str, Any]) -> str:
        from browsergym.utils.obs import flatten_axtree_to_str, flatten_dom_to_str, prune_html

        parts = []
        goal_object = obs.get("goal_object") or []
        if goal_object:
            parts.append("# Goal")
            for message in goal_object:
                if isinstance(message, dict):
                    parts.append(str(message.get("text", message)))
                else:
                    parts.append(str(message))

        parts.append("# Currently open tabs")
        for page_index, (page_url, page_title) in enumerate(
            zip(obs.get("open_pages_urls", []), obs.get("open_pages_titles", []))
        ):
            active = " (active tab)" if page_index == obs.get("active_page_index") else ""
            parts.append(f"Tab {page_index}{active}\n  Title: {page_title}\n  URL: {page_url}")

        if self.use_axtree:
            parts.append("# Current page Accessibility Tree")
            parts.append(flatten_axtree_to_str(obs["axtree_object"]))

        if self.use_html:
            parts.append("# Current page DOM")
            parts.append(prune_html(flatten_dom_to_str(obs["dom_object"])))

        parts.append("# Action Space")
        parts.append(self.action_set.describe(with_long_description=False, with_examples=True))
        parts.append("# Output Format")
        parts.append(
            "Return exactly one BrowserGym action call and nothing else. "
            "Do not output reasoning, analysis, XML, JSON, markdown fences, or copied prompt text.\n"
            "Plain text final answers are invalid. If you know the final answer, call "
            "send_msg_to_user(\"...\").\n"
            "Valid examples:\n"
            "click(\"12\")\n"
            "fill(\"45\", \"example text\")\n"
            "send_msg_to_user(\"final answer\")\n"
            "report_infeasible(\"reason\")"
        )

        if self.history:
            parts.append("# History of past model outputs and executed actions")
            parts.extend(self.history)

        if obs.get("last_action_error"):
            parts.append("# Error message from last action")
            parts.append(str(obs["last_action_error"]))

        parts.append("# Next action")
        parts.append("Return exactly one action call now.")
        return "\n\n".join(parts)

    def get_action(self, obs: dict[str, Any]) -> tuple[str, str]:
        system = (
            "You are a browser automation agent. You interact with a live browser using the "
            "provided action space. Use only text observations: URLs, page titles, and the "
            "accessibility tree or DOM. Do not ask for screenshots. Return only one executable "
            "BrowserGym action call, with no prose or reasoning. If the task is complete, use "
            "send_msg_to_user(\"final answer\")."
        )
        user = self._obs_text(obs)
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if self.extra_body:
            kwargs["extra_body"] = self.extra_body
        response = self.client.chat.completions.create(**kwargs)
        raw = response.choices[0].message.content or ""
        action = extract_action(raw)
        if self.coerce_plain_final_answer:
            action = coerce_plain_answer_to_action(raw, action)
        # Keep prompt history compact. Storing raw model outputs causes some
        # models to echo prior prompts/actions and makes long episodes explode.
        self.history.append(f"executed_action: {action}")
        self.history = self.history[-12:]
        return raw, action


def make_env(task_id: int, headless: bool, max_steps: int):
    return gym.make(
        f"browsergym/webarena.{task_id}",
        disable_env_checker=True,
        headless=headless,
        wait_for_user_message=False,
        max_episode_steps=max_steps,
    )


@contextlib.contextmanager
def optional_file_lock(path: str | None):
    if not path:
        yield
        return
    lock_path = Path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def run_one(task_id: int, args: argparse.Namespace) -> dict[str, Any]:
    task_dir = args.output_root / f"webarena.{task_id}"
    task_dir.mkdir(parents=True, exist_ok=True)
    steps_path = task_dir / "steps.jsonl"

    agent = TextOnlyAgent(
        model=args.model,
        api_key=args.api_key,
        base_url=args.base_url,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        extra_body=parse_json_arg(args.extra_body_json),
        request_timeout=args.request_timeout,
        use_axtree=args.use_axtree,
        use_html=args.use_html,
        coerce_plain_final_answer=args.coerce_plain_final_answer,
    )

    result: dict[str, Any] = {
        "task_id": task_id,
        "env_id": f"browsergym/webarena.{task_id}",
        "model": args.model,
        "base_url": args.base_url,
        "max_steps": args.max_steps,
        "status": "unknown",
        "reward": 0.0,
        "terminated": False,
        "truncated": False,
        "error": None,
        "steps": 0,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    env = None
    try:
        env = make_env(task_id, headless=args.headless, max_steps=args.max_steps)
        with optional_file_lock(args.reset_lock_path):
            obs, info = env.reset(seed=args.seed)
        result["goal"] = obs.get("goal")

        repeated_action_error_count = 0
        previous_action_error_signature: tuple[str, str] | None = None
        with steps_path.open("w") as step_file:
            for step_idx in range(args.max_steps):
                raw, action = agent.get_action(obs)
                obs, reward, terminated, truncated, info = env.step(action)
                last_action_error = str(obs.get("last_action_error", ""))
                action_error_signature = (action, last_action_error)
                if last_action_error and action_error_signature == previous_action_error_signature:
                    repeated_action_error_count += 1
                elif last_action_error:
                    repeated_action_error_count = 1
                    previous_action_error_signature = action_error_signature
                else:
                    repeated_action_error_count = 0
                    previous_action_error_signature = None

                record = {
                    "step": step_idx,
                    "raw_output": raw,
                    "action": action,
                    "reward": reward,
                    "terminated": terminated,
                    "truncated": truncated,
                    "last_action_error": last_action_error,
                    "task_info": info.get("task_info", {}),
                }
                step_file.write(json.dumps(record, ensure_ascii=False) + "\n")
                step_file.flush()

                result["reward"] = float(reward)
                result["terminated"] = bool(terminated)
                result["truncated"] = bool(truncated)
                result["steps"] = step_idx + 1
                result["last_action"] = action
                result["last_action_error"] = last_action_error
                result["task_info"] = info.get("task_info", {})
                if (
                    args.max_repeated_action_errors
                    and repeated_action_error_count >= args.max_repeated_action_errors
                ):
                    result["early_stop_reason"] = (
                        f"same action error repeated {repeated_action_error_count} times"
                    )
                    break
                if terminated or truncated:
                    break
        result["status"] = "success" if result["reward"] > 0 else "failure"
    except Exception as exc:
        result["status"] = "error"
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if env is not None:
            env.close()
        result["ended_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        (task_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--task-ids", type=str, default=None, help="Comma list/ranges, e.g. 0,1,10-19")
    parser.add_argument("--task-file", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--model", type=str, required=True)
    parser.add_argument("--api-key", type=str, default=os.environ.get("OPENAI_API_KEY"))
    parser.add_argument("--base-url", type=str, default=os.environ.get("OPENAI_BASE_URL"))
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument("--max-tokens", type=int, default=32768)
    parser.add_argument("--request-timeout", type=float, default=180)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--headless", type=str2bool, default=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--use-axtree", type=str2bool, default=True)
    parser.add_argument("--use-html", type=str2bool, default=False)
    parser.add_argument("--extra-body-json", type=str, default=None)
    parser.add_argument("--reset-lock-path", type=str, default=os.environ.get("WEBARENA_RESET_LOCK_PATH"))
    parser.add_argument("--reset-once", action="store_true")
    parser.add_argument("--coerce-plain-final-answer", action="store_true")
    parser.add_argument("--max-repeated-action-errors", type=int, default=0)
    parser.add_argument("--fail-on-error", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.api_key:
        raise SystemExit("Missing --api-key or OPENAI_API_KEY.")

    import browsergym.core  # noqa: F401
    import browsergym.webarena  # noqa: F401
    patch_webarena_eval_llm()
    patch_webarena_login_timeout()

    if args.reset_once:
        from browsergym.webarena.instance import WebArenaInstance

        WebArenaInstance().full_reset(skip_if_not_set=True)

    args.output_root.mkdir(parents=True, exist_ok=True)
    task_ids = parse_task_ids(args.task_ids, args.task_file, args.limit)
    summary_path = args.output_root / "summary.jsonl"

    counts = {"success": 0, "failure": 0, "error": 0}
    with summary_path.open("a") as summary:
        for task_id in task_ids:
            result = run_one(task_id, args)
            counts[result["status"]] = counts.get(result["status"], 0) + 1
            summary.write(json.dumps(result, ensure_ascii=False) + "\n")
            summary.flush()
            print(
                f"task={task_id} status={result['status']} reward={result['reward']} "
                f"steps={result['steps']} error={result['error']}",
                flush=True,
            )

    total = sum(counts.values())
    print(json.dumps({"total": total, **counts}, indent=2))
    return 1 if args.fail_on_error and counts.get("error", 0) else 0


if __name__ == "__main__":
    sys.exit(main())
