from __future__ import annotations

import json
import time
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path
from typing import Any

from agent_advanced import AdvancedAgent
from agent_baseline import BaselineAgent
from config import load_config


@dataclass
class BenchmarkRow:
    agent_name: str
    agent_tokens_only: int
    prompt_tokens_processed: int
    recall_score: float
    response_quality: float
    memory_growth_bytes: int
    compactions: int


def load_conversations(path: Path) -> list[dict[str, Any]]:
    """Student TODO: read JSON conversations from disk."""

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON list of conversations.")
    return data


def recall_points(answer: str, expected: list[str]) -> float:
    """Student TODO: return 0 / 0.5 / 1 depending on how many expected facts appear."""

    if not expected:
        return 1.0

    normalized_answer = answer.casefold()
    matched = sum(1 for fact in expected if fact.casefold() in normalized_answer)
    if matched == 0:
        return 0.0
    if matched == len(expected):
        return 1.0
    return 0.5


def heuristic_quality(answer: str, expected: list[str]) -> float:
    """Student TODO: add a lightweight quality score for offline mode."""

    recall = recall_points(answer, expected)
    token_count = len(answer.split())
    concise_bonus = 1.0 if 5 <= token_count <= 80 else 0.75
    structure_bonus = 1.0 if any(mark in answer for mark in (";", "-", "\n", ":")) else 0.85
    return round((0.75 * recall) + (0.15 * concise_bonus) + (0.10 * structure_bonus), 3)


def run_agent_benchmark(agent_name: str, agent, conversations: list[dict[str, Any]], config) -> BenchmarkRow:
    """Student TODO: evaluate one agent over many conversations.

    Pseudocode:
    1. Feed all turns to the agent.
    2. Track `agent tokens only`.
    3. Track `prompt tokens processed`.
    4. Ask recall questions in a fresh thread.
    5. Compute average recall and quality.
    6. Record memory file growth and compaction count.
    """

    user_ids = sorted({str(conversation["user_id"]) for conversation in conversations})
    before_memory = _memory_size(agent, user_ids)
    observed_threads: set[str] = set()
    recall_scores: list[float] = []
    quality_scores: list[float] = []

    for conversation in conversations:
        conversation_id = str(conversation["id"])
        user_id = str(conversation["user_id"])
        thread_id = f"{conversation_id}:main"
        observed_threads.add(thread_id)

        for turn in conversation.get("turns", []):
            agent.reply(user_id=user_id, thread_id=thread_id, message=str(turn))

        for index, recall_question in enumerate(conversation.get("recall_questions", []), start=1):
            recall_thread = f"{conversation_id}:recall:{index}"
            observed_threads.add(recall_thread)
            question = str(recall_question["question"])
            expected = [str(item) for item in recall_question.get("expected_contains", [])]
            result = agent.reply(user_id=user_id, thread_id=recall_thread, message=question)
            answer = str(result.get("answer") or result.get("response") or "")
            recall_scores.append(recall_points(answer, expected))
            quality_scores.append(heuristic_quality(answer, expected))

    after_memory = _memory_size(agent, user_ids)

    return BenchmarkRow(
        agent_name=agent_name,
        agent_tokens_only=sum(agent.token_usage(thread_id) for thread_id in observed_threads),
        prompt_tokens_processed=sum(agent.prompt_token_usage(thread_id) for thread_id in observed_threads),
        recall_score=_average(recall_scores),
        response_quality=_average(quality_scores),
        memory_growth_bytes=max(0, after_memory - before_memory),
        compactions=sum(agent.compaction_count(thread_id) for thread_id in observed_threads),
    )


def format_rows(rows: list[BenchmarkRow]) -> str:
    """Student TODO: print a markdown table or tabulated output."""

    headers = [
        "Agent",
        "Agent tokens only",
        "Prompt tokens processed",
        "Cross-session recall",
        "Response quality",
        "Memory growth (bytes)",
        "Compactions",
    ]
    table = [
        [
            row.agent_name,
            row.agent_tokens_only,
            row.prompt_tokens_processed,
            f"{row.recall_score:.2f}",
            f"{row.response_quality:.2f}",
            row.memory_growth_bytes,
            row.compactions,
        ]
        for row in rows
    ]

    try:
        from tabulate import tabulate

        return tabulate(table, headers=headers, tablefmt="github")
    except ImportError:
        return _format_markdown_table(headers, table)


def main() -> None:
    """Student TODO: run both benchmark suites.

    Required benchmark sections:
    - Standard benchmark from `data/conversations.json`
    - Long-context stress benchmark from `data/advanced_long_context.json`

    Compare:
    - Baseline
    - Advanced

    Keep the same output columns as the solved lab:
    - Agent tokens only
    - Prompt tokens processed
    - Cross-session recall
    - Response quality
    - Memory growth (bytes)
    - Compactions
    """

    config = load_config(Path(__file__).resolve().parent.parent)
    run_root = config.state_dir / "benchmark_runs" / str(int(time.time()))

    suites = [
        ("Standard Benchmark", config.data_dir / "conversations.json"),
        ("Long-Context Stress Benchmark", config.data_dir / "advanced_long_context.json"),
    ]

    for suite_name, dataset_path in suites:
        conversations = load_conversations(dataset_path)
        suite_slug = suite_name.lower().replace(" ", "_").replace("-", "_")
        baseline_config = replace(config, state_dir=run_root / suite_slug / "baseline")
        advanced_config = replace(config, state_dir=run_root / suite_slug / "advanced")

        rows = [
            run_agent_benchmark(
                "Baseline",
                BaselineAgent(config=baseline_config, force_offline=True),
                conversations,
                baseline_config,
            ),
            run_agent_benchmark(
                "Advanced",
                AdvancedAgent(config=advanced_config, force_offline=True),
                conversations,
                advanced_config,
            ),
        ]

        print(f"\n## {suite_name}")
        print(f"Dataset: {dataset_path}")
        print(format_rows(rows))


def _memory_size(agent, user_ids: list[str]) -> int:
    if not hasattr(agent, "memory_file_size"):
        return 0
    return sum(int(agent.memory_file_size(user_id)) for user_id in user_ids)


def _average(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 3)


def _format_markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
