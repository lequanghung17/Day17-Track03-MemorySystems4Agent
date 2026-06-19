from __future__ import annotations

from pathlib import Path
from dataclasses import replace

from agent_advanced import AdvancedAgent
from agent_baseline import BaselineAgent
from config import load_config
from memory_store import UserProfileStore


def make_config(tmp_path: Path):
    """Student TODO: build an isolated config for tests."""

    # Hint:
    # - point `state_dir` into tmp_path
    # - reduce compact threshold so compaction happens quickly in tests
    config = load_config(Path(__file__).resolve().parent.parent)
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    return replace(
        config,
        state_dir=state_dir,
        compact_threshold_tokens=80,
        compact_keep_messages=2,
    )


def test_user_markdown_read_write_edit(tmp_path: Path) -> None:
    """Student TODO: verify `User.md` can be created, updated, and edited."""

    store = UserProfileStore(tmp_path / "profiles")

    assert "## Facts" in store.read_text("user 01")
    path = store.write_text("user 01", "# User Profile: user 01\n\n## Facts\n- name: Dung")

    assert path.exists()
    assert store.file_size("user 01") > 0
    assert "name: Dung" in store.read_text("user 01")

    changed = store.edit_text("user 01", "name: Dung", "name: DungCT")

    assert changed is True
    assert "name: DungCT" in store.read_text("user 01")
    assert store.edit_text("user 01", "missing", "replacement") is False


def test_compact_trigger(tmp_path: Path) -> None:
    """Student TODO: verify long threads trigger compaction."""

    config = make_config(tmp_path)
    advanced = AdvancedAgent(config=config, force_offline=True)

    for index in range(8):
        advanced.reply(
            user_id="u1",
            thread_id="long-thread",
            message=f"Turn {index}: " + "Python AI memory benchmark " * 12,
        )

    context = advanced.compact_memory.context("long-thread")

    assert advanced.compaction_count("long-thread") > 0
    assert context["summary"]
    assert len(context["messages"]) <= config.compact_keep_messages


def test_cross_session_recall(tmp_path: Path) -> None:
    """Student TODO: verify advanced remembers across sessions and baseline does not."""

    config = make_config(tmp_path)
    advanced = AdvancedAgent(config=config, force_offline=True)
    baseline = BaselineAgent(config=config, force_offline=True)

    advanced.reply("u1", "session-a", "Mình tên là DũngCT. Mình ở Huế và đang là MLOps engineer.")
    baseline.reply("u1", "session-a", "Mình tên là DũngCT. Mình ở Huế và đang là MLOps engineer.")

    advanced_answer = advanced.reply("u1", "session-b", "Mình tên gì và hiện tại làm nghề gì?")["answer"]
    baseline_answer = baseline.reply("u1", "session-b", "Mình tên gì và hiện tại làm nghề gì?")["answer"]

    assert "DũngCT" in advanced_answer
    assert "MLOps engineer" in advanced_answer
    assert "DũngCT" not in baseline_answer
    assert "MLOps engineer" not in baseline_answer


def test_compact_reduces_prompt_load_on_long_thread(tmp_path: Path) -> None:
    """Student TODO: compare prompt load of baseline vs advanced on a long thread."""

    config = make_config(tmp_path)
    advanced = AdvancedAgent(config=config, force_offline=True)
    baseline = BaselineAgent(config=config, force_offline=True)

    long_turns = [
        f"Turn {index}: mình đang ghi một đoạn rất dài về Python, AI agent, benchmark memory và token cost. "
        + "Thông tin này được lặp lại để tạo áp lực context. " * 8
        for index in range(14)
    ]

    for turn in long_turns:
        baseline.reply("u1", "long-thread", turn)
        advanced.reply("u1", "long-thread", turn)

    assert advanced.compaction_count("long-thread") > 0
    assert advanced.prompt_token_usage("long-thread") < baseline.prompt_token_usage("long-thread")
