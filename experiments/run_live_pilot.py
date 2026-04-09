#!/usr/bin/env python3
"""Run a small live CyberEval pilot against real LLM APIs.

The pilot intentionally stays bounded: one stratified question per dimension, each
asked in both MCQ and scenario-reframed formats. It writes a full reproducibility
artifact bundle under ``paper/artifacts/live_llm/<timestamp>/``.

The preferred transport is direct provider APIs, but the script also supports the
authenticated Hermes CLI as a live model transport so the repo can refresh evidence
without hardcoding provider secrets.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PAPER_DIR = ROOT / "paper"
RESULTS_PATH = ROOT / "experiments" / "results" / "real_results.json"
DIMENSION_ORDER = ["VK", "TI", "SC", "IR", "CG", "FA", "SA"]
DIMENSION_NAMES = {
    "VK": "Vulnerability Knowledge",
    "TI": "Threat Intelligence",
    "SC": "Secure Coding",
    "IR": "Incident Response",
    "CG": "Compliance & Governance",
    "FA": "Forensic Analysis",
    "SA": "Security Architecture",
}
SCENARIO_FRAMES = {
    "VK": "You are helping an application-security reviewer classify a weakness found during triage.",
    "TI": "You are assisting a threat-intelligence analyst who needs the most accurate interpretation for a report.",
    "SC": "You are helping an AppSec engineer choose the safest explanation during secure-code review.",
    "IR": "You are supporting an incident responder making an initial containment or triage decision.",
    "CG": "You are assisting a governance analyst interpreting a compliance or policy control question.",
    "FA": "You are helping a forensic analyst interpret the most defensible investigative answer.",
    "SA": "You are assisting a security architect selecting the best architecture-oriented answer.",
}
MODEL_SPECS = {
    "openai-codex:gpt-5.3-codex": {
        "provider": "openai-codex",
        "model": "gpt-5.3-codex",
        "transport": "hermes",
    },
    "openrouter:openai/gpt-4o": {
        "provider": "openrouter",
        "model": "openai/gpt-4o",
        "env": "OPENROUTER_API_KEY",
    },
    "openrouter:anthropic/claude-3.5-sonnet": {
        "provider": "openrouter",
        "model": "anthropic/claude-3.5-sonnet",
        "env": "OPENROUTER_API_KEY",
    },
    "openai:gpt-4o": {"provider": "openai", "model": "gpt-4o", "env": "OPENAI_API_KEY"},
    "anthropic:claude-3-5-sonnet-latest": {
        "provider": "anthropic",
        "model": "claude-3-5-sonnet-latest",
        "env": "ANTHROPIC_API_KEY",
    },
}
SYSTEM_PROMPT = (
    "You are participating in a cybersecurity benchmark. Return valid JSON only, "
    "with keys selected_option (integer 0-3), confidence (number 0-1), and rationale (string). "
    "Do not include markdown fences or any extra text."
)


def _load_dotenv() -> None:
    for env_path in [ROOT / ".env", Path.home() / ".hermes" / ".env"]:
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


def _load_question_bank() -> list[dict[str, Any]]:
    module_path = ROOT / "experiments" / "run_real_evaluation.py"
    spec = importlib.util.spec_from_file_location("run_real_evaluation", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load question-bank module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.generate_question_bank()


def _select_sample(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sample: list[dict[str, Any]] = []
    for dim in DIMENSION_ORDER:
        candidates = [
            q for q in questions if q["dimension"] == dim and q["difficulty"] in {2, 3}
        ]
        if not candidates:
            candidates = [q for q in questions if q["dimension"] == dim]
        if not candidates:
            raise RuntimeError(f"No question found for dimension {dim}")
        sample.append(candidates[0])
    return sample


def _option_block(question: dict[str, Any]) -> str:
    lines = []
    for idx, choice in enumerate(question["choices"]):
        lines.append(f"{idx}. {choice}")
    return "\n".join(lines)


def _build_prompt(question: dict[str, Any], fmt: str) -> str:
    header = [
        f"Question ID: {question['id']}",
        f"Dimension: {question['dimension']} ({DIMENSION_NAMES[question['dimension']]})",
        f"Difficulty: {question['difficulty']}",
    ]
    if fmt == "mcq":
        task = "Answer the following cybersecurity multiple-choice question. Select the single best option."
    elif fmt == "scenario":
        task = (
            f"{SCENARIO_FRAMES[question['dimension']]} Re-read the same underlying question in a workflow setting, "
            "reason briefly, and still choose the single best option from the list."
        )
    else:
        raise ValueError(f"Unsupported format: {fmt}")
    return (
        "\n".join(header)
        + "\n\n"
        + task
        + "\n\nQuestion:\n"
        + question["question"]
        + "\n\nOptions:\n"
        + _option_block(question)
        + "\n\nReturn JSON only."
    )


def _extract_json_blob(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        anchored_starts = [
            idx
            for idx, ch in enumerate(cleaned)
            if ch == "{" and (idx == 0 or cleaned[idx - 1] == "\n")
        ]
        candidate_starts = anchored_starts or [
            idx for idx, ch in enumerate(cleaned) if ch == "{"
        ]
        parsed_objects: list[dict[str, Any]] = []
        for start in candidate_starts:
            try:
                parsed, _ = decoder.raw_decode(cleaned[start:])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                parsed_objects.append(parsed)
        if parsed_objects:
            return parsed_objects[-1]
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def _normalize_rationale(parsed: dict[str, Any]) -> str | None:
    for key in ["rationale", "reason", "reasoning", "brief_reason"]:
        value = parsed.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _normalize_selected_option(
    parsed: dict[str, Any], choices: list[str]
) -> int | None:
    def _coerce(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value if 0 <= value < len(choices) else None
        if isinstance(value, float) and value.is_integer():
            ivalue = int(value)
            return ivalue if 0 <= ivalue < len(choices) else None
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.isdigit():
                ivalue = int(stripped)
                return ivalue if 0 <= ivalue < len(choices) else None
            letter_map = {"A": 0, "B": 1, "C": 2, "D": 3}
            if stripped.upper() in letter_map:
                idx = letter_map[stripped.upper()]
                return idx if idx < len(choices) else None
            lowered = stripped.casefold()
            for idx, choice in enumerate(choices):
                if lowered == choice.casefold():
                    return idx
        return None

    for key in [
        "selected_option",
        "best_option",
        "answer",
        "selected_choice",
        "selected_text",
    ]:
        idx = _coerce(parsed.get(key))
        if idx is not None:
            return idx
    return None


def _post_json(
    url: str, headers: dict[str, str], payload: dict[str, Any], timeout: int = 90
) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _extract_hermes_text(stdout: str) -> tuple[str, str | None]:
    lines = stdout.splitlines()
    content_lines: list[str] = []
    session_id: str | None = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("╭") and "Hermes" in stripped:
            continue
        if stripped.startswith("┊"):
            continue
        if stripped.startswith("session_id:"):
            session_id = stripped.split(":", 1)[1].strip() or None
            continue
        if stripped.startswith("Reached maximum iterations"):
            continue
        content_lines.append(line)
    return "\n".join(content_lines).strip(), session_id


def _call_hermes(provider: str, model: str, prompt: str) -> dict[str, Any]:
    hermes_prompt = f"{SYSTEM_PROMPT}\n\n{prompt}"
    cmd = [
        "hermes",
        "chat",
        "-Q",
        "--provider",
        provider,
        "-m",
        model,
        "-t",
        "",
        "--max-turns",
        "1",
        "--source",
        "tool",
        "-q",
        hermes_prompt,
    ]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        detail = (
            proc.stderr.strip() or proc.stdout.strip() or f"exit code {proc.returncode}"
        )
        raise RuntimeError(f"Hermes CLI call failed: {detail}")
    text, session_id = _extract_hermes_text(proc.stdout)
    if not text:
        raise RuntimeError("Hermes CLI returned empty output")
    return {
        "provider": provider,
        "model": model,
        "response_id": session_id,
        "text": text,
        "usage": {},
        "raw": {
            "transport": "hermes",
            "command": cmd,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "session_id": session_id,
        },
    }


def _call_openai(model: str, prompt: str) -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": 220,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    }
    raw = _post_json(
        "https://api.openai.com/v1/chat/completions",
        {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        payload,
    )
    return {
        "provider": "openai",
        "model": model,
        "response_id": raw.get("id"),
        "text": raw["choices"][0]["message"]["content"],
        "usage": raw.get("usage", {}),
        "raw": raw,
    }


def _call_anthropic(model: str, prompt: str) -> dict[str, Any]:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    payload = {
        "model": model,
        "max_tokens": 220,
        "temperature": 0,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": prompt}],
    }
    raw = _post_json(
        "https://api.anthropic.com/v1/messages",
        {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        payload,
    )
    text_blocks = [
        block.get("text", "")
        for block in raw.get("content", [])
        if block.get("type") == "text"
    ]
    return {
        "provider": "anthropic",
        "model": model,
        "response_id": raw.get("id"),
        "text": "\n".join(text_blocks).strip(),
        "usage": raw.get("usage", {}),
        "raw": raw,
    }


def _call_openrouter(model: str, prompt: str) -> dict[str, Any]:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": 220,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    }
    raw = _post_json(
        "https://openrouter.ai/api/v1/chat/completions",
        {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/technion-cs-nlp/hermes-agent",
            "X-Title": "CyberEval live pilot",
        },
        payload,
    )
    return {
        "provider": "openrouter",
        "model": model,
        "response_id": raw.get("id"),
        "text": raw["choices"][0]["message"]["content"],
        "usage": raw.get("usage", {}),
        "raw": raw,
    }


def _call_model(
    provider: str, model: str, prompt: str, transport: str | None = None
) -> dict[str, Any]:
    if transport == "hermes":
        return _call_hermes(provider, model, prompt)
    if provider == "openai":
        return _call_openai(model, prompt)
    if provider == "anthropic":
        return _call_anthropic(model, prompt)
    if provider == "openrouter":
        return _call_openrouter(model, prompt)
    raise ValueError(f"Unsupported provider: {provider}")


def _load_simulated_frontier() -> dict[str, Any]:
    simulated = json.loads(RESULTS_PATH.read_text())
    ranking = simulated["model_ranking"]
    top_two = ranking[:2]
    return {
        "ranking": top_two,
        "aggregate": {
            model: simulated["model_scores"][model]["aggregate"] for model in top_two
        },
    }


def _compute_metrics(
    records: list[dict[str, Any]], sample: list[dict[str, Any]]
) -> dict[str, Any]:
    by_model: dict[str, dict[str, Any]] = {}
    model_names = sorted(
        {record["model_label"] for record in records if record["status"] == "ok"}
    )
    for model_label in model_names:
        rows = [
            record
            for record in records
            if record["model_label"] == model_label and record["status"] == "ok"
        ]
        total = len(rows)
        total_correct = sum(1 for row in rows if row["correct"])
        by_format = {}
        for fmt in ["mcq", "scenario"]:
            fmt_rows = [row for row in rows if row["format"] == fmt]
            fmt_correct = sum(1 for row in fmt_rows if row["correct"])
            by_format[fmt] = {
                "count": len(fmt_rows),
                "correct": fmt_correct,
                "accuracy": (fmt_correct / len(fmt_rows)) if fmt_rows else None,
            }
        by_dimension = {}
        for question in sample:
            dim = question["dimension"]
            dim_rows = [row for row in rows if row["dimension"] == dim]
            dim_correct = sum(1 for row in dim_rows if row["correct"])
            by_dimension[dim] = {
                "count": len(dim_rows),
                "correct": dim_correct,
                "accuracy": (dim_correct / len(dim_rows)) if dim_rows else None,
            }
        usage_totals: dict[str, float] = {}
        for row in rows:
            for key, value in row.get("usage", {}).items():
                if isinstance(value, (int, float)):
                    usage_totals[key] = usage_totals.get(key, 0) + value
        by_model[model_label] = {
            "count": total,
            "correct": total_correct,
            "accuracy": (total_correct / total) if total else None,
            "mcq_accuracy": by_format["mcq"]["accuracy"],
            "scenario_accuracy": by_format["scenario"]["accuracy"],
            "scenario_gap_pp": None
            if by_format["mcq"]["accuracy"] is None
            or by_format["scenario"]["accuracy"] is None
            else (by_format["mcq"]["accuracy"] - by_format["scenario"]["accuracy"])
            * 100,
            "by_format": by_format,
            "by_dimension": by_dimension,
            "usage": usage_totals,
        }
    ranking = sorted(
        [{"model": model, **metrics} for model, metrics in by_model.items()],
        key=lambda item: (
            -1 if item["accuracy"] is None else -item["accuracy"],
            item["model"],
        ),
    )
    simulated = _load_simulated_frontier()
    ranking_labels = [item["model"] for item in ranking]
    return {
        "sample_question_count": len(sample),
        "sample_prompt_count": len(records),
        "models": by_model,
        "ranking": ranking,
        "simulated_frontier": simulated,
        "live_order_matches_simulated_frontier": ranking_labels[:2]
        == simulated["ranking"][: len(ranking_labels[:2])],
    }


def _make_summary(metrics: dict[str, Any], artifact_dir: Path) -> str:
    lines = [
        "# CyberEval live LLM pilot",
        "",
        f"Artifact directory: `{artifact_dir}`",
        f"Sample questions: {metrics['sample_question_count']} (one per dimension)",
        f"Prompt count: {metrics['sample_prompt_count']}",
        "",
        "## Model summary",
        "",
    ]
    for item in metrics["ranking"]:
        lines.extend(
            [
                f"- **{item['model']}**: overall {item['accuracy'] * 100:.1f}% "
                f"({item['correct']}/{item['count']}), MCQ {item['mcq_accuracy'] * 100:.1f}%, "
                f"scenario {item['scenario_accuracy'] * 100:.1f}%, gap {item['scenario_gap_pp']:.1f} pp",
            ]
        )
    lines.extend(
        [
            "",
            "## Simulated frontier reference",
            "",
            f"- Simulated top two: {', '.join(metrics['simulated_frontier']['ranking'])}",
            f"- Live order matches simulated frontier: {metrics['live_order_matches_simulated_frontier']}",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=None,
        help="Optional explicit artifact directory. Defaults to paper/artifacts/live_llm/<timestamp>/",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=[
            "openai-codex:gpt-5.3-codex",
        ],
        help="Models to run as provider:model keys.",
    )
    args = parser.parse_args()

    _load_dotenv()
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifact_dir = args.artifact_dir or (
        PAPER_DIR / "artifacts" / "live_llm" / timestamp
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)

    baseline_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    questions = _load_question_bank()
    sample = _select_sample(questions)

    command = " ".join([sys.executable, *sys.argv])
    inputs = {
        "utc_timestamp": timestamp,
        "baseline_commit": baseline_commit,
        "models": args.models,
        "selection_policy": "first difficulty-2-or-3 item per dimension, fallback to first available item",
        "sample": sample,
        "prompt_templates": {
            "system": SYSTEM_PROMPT,
            "formats": {
                fmt: {q["id"]: _build_prompt(q, fmt) for q in sample}
                for fmt in ["mcq", "scenario"]
            },
        },
    }

    records: list[dict[str, Any]] = []
    for model_label in args.models:
        spec = MODEL_SPECS.get(model_label)
        if not spec:
            raise RuntimeError(f"Unknown model spec: {model_label}")
        provider = spec["provider"]
        model = spec["model"]
        transport = spec.get("transport")
        for question in sample:
            for fmt in ["mcq", "scenario"]:
                prompt = _build_prompt(question, fmt)
                started = time.time()
                api_result: dict[str, Any] | None = None
                try:
                    api_result = _call_model(
                        provider, model, prompt, transport=transport
                    )
                    latency_s = time.time() - started
                    parsed = _extract_json_blob(api_result["text"])
                    selected_option = _normalize_selected_option(
                        parsed, question["choices"]
                    )
                    correct = (
                        selected_option == question["correct"]
                        if selected_option is not None
                        else False
                    )
                    records.append(
                        {
                            "status": "ok",
                            "provider": provider,
                            "model": model,
                            "model_label": model_label,
                            "question_id": question["id"],
                            "dimension": question["dimension"],
                            "difficulty": question["difficulty"],
                            "format": fmt,
                            "prompt": prompt,
                            "selected_option": selected_option,
                            "selected_choice": None
                            if selected_option is None
                            else question["choices"][selected_option],
                            "correct_option": question["correct"],
                            "correct_choice": question["choices"][question["correct"]],
                            "correct": bool(correct),
                            "confidence": parsed.get("confidence"),
                            "rationale": _normalize_rationale(parsed),
                            "latency_s": round(latency_s, 3),
                            "usage": api_result.get("usage", {}),
                            "response_id": api_result.get("response_id"),
                            "raw_text": api_result["text"],
                            "raw_response": api_result["raw"],
                        }
                    )
                except Exception as exc:  # noqa: BLE001
                    latency_s = time.time() - started
                    records.append(
                        {
                            "status": "error",
                            "provider": provider,
                            "model": model,
                            "model_label": model_label,
                            "question_id": question["id"],
                            "dimension": question["dimension"],
                            "difficulty": question["difficulty"],
                            "format": fmt,
                            "prompt": prompt,
                            "latency_s": round(latency_s, 3),
                            "error": f"{type(exc).__name__}: {exc}",
                            "response_id": None
                            if api_result is None
                            else api_result.get("response_id"),
                            "raw_text": None
                            if api_result is None
                            else api_result.get("text"),
                            "raw_response": None
                            if api_result is None
                            else api_result.get("raw"),
                        }
                    )

    successful = [record for record in records if record["status"] == "ok"]
    if not successful:
        (artifact_dir / "command.txt").write_text(command + "\n", encoding="utf-8")
        (artifact_dir / "inputs.json").write_text(
            json.dumps(inputs, indent=2), encoding="utf-8"
        )
        (artifact_dir / "outputs.json").write_text(
            json.dumps(records, indent=2), encoding="utf-8"
        )
        raise RuntimeError("Live pilot produced no successful model responses")

    metrics = _compute_metrics(records, sample)
    manifest = {
        "utc_timestamp": timestamp,
        "baseline_commit": baseline_commit,
        "command": command,
        "artifact_dir": str(artifact_dir),
        "models": args.models,
        "sample_question_ids": [question["id"] for question in sample],
    }
    summary = _make_summary(metrics, artifact_dir)

    (artifact_dir / "command.txt").write_text(command + "\n", encoding="utf-8")
    (artifact_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    (artifact_dir / "inputs.json").write_text(
        json.dumps(inputs, indent=2), encoding="utf-8"
    )
    (artifact_dir / "outputs.json").write_text(
        json.dumps(records, indent=2), encoding="utf-8"
    )
    (artifact_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )
    (artifact_dir / "summary.md").write_text(summary + "\n", encoding="utf-8")
    latest_summary = {
        "artifact_dir": str(artifact_dir),
        "utc_timestamp": timestamp,
        "baseline_commit": baseline_commit,
        "metrics": metrics,
    }
    latest_summary_path = PAPER_DIR / "artifacts" / "live_llm" / "latest_summary.json"
    latest_summary_path.parent.mkdir(parents=True, exist_ok=True)
    latest_summary_path.write_text(
        json.dumps(latest_summary, indent=2), encoding="utf-8"
    )

    print(json.dumps(latest_summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
