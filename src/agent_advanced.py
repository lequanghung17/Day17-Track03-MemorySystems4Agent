from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import unicodedata

from config import LabConfig, load_config
from memory_store import CompactMemoryManager, UserProfileStore, estimate_tokens, extract_profile_updates
from model_provider import build_chat_model


@dataclass
class AgentContext:
    user_id: str
    memory_path: str


class AdvancedAgent:
    """Student TODO: implement Agent B / Advanced Agent.

    Required memory layers:
    1. within-session memory
    2. persistent `User.md`
    3. compact memory for long threads
    """

    def __init__(self, config: LabConfig | None = None, force_offline: bool = False) -> None:
        self.config = config or load_config()
        self.force_offline = force_offline
        self.profile_store = UserProfileStore(self.config.state_dir / "profiles")
        self.compact_memory = CompactMemoryManager(
            threshold_tokens=self.config.compact_threshold_tokens,
            keep_messages=self.config.compact_keep_messages,
        )
        self.thread_tokens: dict[str, int] = {}
        self.thread_prompt_tokens: dict[str, int] = {}

        # TODO: optionally initialize a real LangChain/LangGraph agent.
        self.langchain_agent = None if force_offline else self._maybe_build_langchain_agent()

    def reply(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        """Student TODO: route between offline mode and live mode."""

        if self.langchain_agent is not None and not self.force_offline:
            try:
                return self._reply_live(user_id=user_id, thread_id=thread_id, message=message)
            except Exception:
                return self._reply_offline(user_id=user_id, thread_id=thread_id, message=message)

        return self._reply_offline(user_id=user_id, thread_id=thread_id, message=message)

    def token_usage(self, thread_id: str) -> int:
        return self.thread_tokens.get(thread_id, 0)

    def prompt_token_usage(self, thread_id: str) -> int:
        return self.thread_prompt_tokens.get(thread_id, 0)

    def memory_file_size(self, user_id: str) -> int:
        return self.profile_store.file_size(user_id)

    def compaction_count(self, thread_id: str) -> int:
        return self.compact_memory.compaction_count(thread_id)

    def _reply_offline(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        """Student TODO: implement the deterministic advanced path.

        Pseudocode:
        1. Extract stable profile facts from the incoming message.
        2. Persist those facts into `User.md`.
        3. Append the message into compact memory.
        4. Estimate prompt-context load from `User.md` + summary + recent messages.
        5. Generate a response that can answer long-term recall questions.
        6. Append the assistant reply and update token counters.
        """

        updates = _profile_updates_to_persist(message)
        for key, value in updates.items():
            if key == "correction_note":
                continue
            if key == "interests":
                value = _merge_fact_values(self.profile_store.facts(user_id).get(key), value)
            self.profile_store.upsert_fact(user_id, key, value)

        self.compact_memory.append(thread_id, "user", message)
        prompt_tokens = self._estimate_prompt_context_tokens(user_id=user_id, thread_id=thread_id)
        answer = self._offline_response(user_id=user_id, thread_id=thread_id, message=message)
        agent_tokens = estimate_tokens(answer)

        self.compact_memory.append(thread_id, "assistant", answer)
        self.thread_tokens[thread_id] = self.thread_tokens.get(thread_id, 0) + agent_tokens
        self.thread_prompt_tokens[thread_id] = self.thread_prompt_tokens.get(thread_id, 0) + prompt_tokens

        return {
            "agent": "advanced",
            "mode": "offline",
            "user_id": user_id,
            "thread_id": thread_id,
            "answer": answer,
            "response": answer,
            "agent_tokens": agent_tokens,
            "prompt_tokens": prompt_tokens,
            "total_agent_tokens": self.thread_tokens[thread_id],
            "total_prompt_tokens": self.thread_prompt_tokens[thread_id],
            "memory_file_size": self.memory_file_size(user_id),
            "compactions": self.compaction_count(thread_id),
        }

    def _estimate_prompt_context_tokens(self, user_id: str, thread_id: str) -> int:
        """Student TODO: estimate the context carried into one turn.

        Hint:
        - Include `User.md`
        - Include compact summary text
        - Include recent kept messages
        """

        profile_text = self.profile_store.read_text(user_id)
        compact_context = self.compact_memory.context(thread_id)
        recent_messages = compact_context["messages"]
        assert isinstance(recent_messages, list)

        context_parts = [
            "Persistent profile:",
            profile_text,
            "Compact summary:",
            str(compact_context["summary"]),
            "Recent messages:",
            _format_messages(recent_messages),
        ]
        return estimate_tokens("\n".join(context_parts))

    def _offline_response(self, user_id: str, thread_id: str, message: str) -> str:
        """Student TODO: return a deterministic answer using persisted memory.

        Make sure the advanced agent can answer questions like:
        - "Mình tên gì?"
        - "Hiện tại mình làm nghề gì?"
        - "Nhắc lại style trả lời mình thích"
        - questions in the long stress dataset
        """

        facts = self.profile_store.facts(user_id)
        normalized = _normalize_for_match(message)

        if _asks_for_memory_recall(normalized):
            requested_parts = _requested_profile_parts(normalized, facts)
            if requested_parts:
                return "Mình nhớ từ User.md: " + "; ".join(requested_parts) + "."

            return _profile_summary(facts)

        updates = _profile_updates_to_persist(message)
        if updates:
            visible = ", ".join(f"{key}={value}" for key, value in updates.items() if key != "correction_note")
            return f"Mình đã lưu vào User.md: {visible}."

        if "trade-off" in normalized or "token" in normalized or "recall" in normalized:
            return "Ghi nhận. Với advanced agent, mình sẽ ưu tiên giữ facts bền vững trong User.md và dùng compact summary để giảm prompt tokens."

        return "Đã nhận. Advanced agent sẽ kết hợp User.md, compact summary và các message gần nhất."

    def _maybe_build_langchain_agent(self):
        """Student TODO: wire a live agent with tools and compact middleware.

        High-level design:
        - `build_chat_model(self.config.model)` for the selected provider
        - `InMemorySaver` for short-term thread state
        - tool to read `User.md`
        - tool to write/edit `User.md`
        - dynamic prompt that injects profile memory
        - summarization middleware for long threads
        """

        try:
            return build_chat_model(self.config.model)
        except Exception:
            return None

    def _reply_live(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        updates = _profile_updates_to_persist(message)
        for key, value in updates.items():
            if key != "correction_note":
                if key == "interests":
                    value = _merge_fact_values(self.profile_store.facts(user_id).get(key), value)
                self.profile_store.upsert_fact(user_id, key, value)

        self.compact_memory.append(thread_id, "user", message)
        prompt_tokens = self._estimate_prompt_context_tokens(user_id=user_id, thread_id=thread_id)

        profile_text = self.profile_store.read_text(user_id)
        prompt = (
            "You are an advanced memory agent. Use this persistent profile when relevant.\n\n"
            f"{profile_text}\n\nUser: {message}"
        )
        result = self.langchain_agent.invoke(prompt)
        answer = getattr(result, "content", str(result))
        agent_tokens = estimate_tokens(answer)

        self.compact_memory.append(thread_id, "assistant", answer)
        self.thread_tokens[thread_id] = self.thread_tokens.get(thread_id, 0) + agent_tokens
        self.thread_prompt_tokens[thread_id] = self.thread_prompt_tokens.get(thread_id, 0) + prompt_tokens

        return {
            "agent": "advanced",
            "mode": "live",
            "user_id": user_id,
            "thread_id": thread_id,
            "answer": answer,
            "response": answer,
            "agent_tokens": agent_tokens,
            "prompt_tokens": prompt_tokens,
            "total_agent_tokens": self.thread_tokens[thread_id],
            "total_prompt_tokens": self.thread_prompt_tokens[thread_id],
            "memory_file_size": self.memory_file_size(user_id),
            "compactions": self.compaction_count(thread_id),
        }


def _format_messages(messages: list[dict[str, str]]) -> str:
    return "\n".join(f"{item.get('role', '')}: {item.get('content', '')}" for item in messages)


def _profile_updates_to_persist(message: str) -> dict[str, str]:
    normalized = _normalize_for_match(message)
    if _is_open_profile_question(normalized):
        return {}
    if _asks_for_memory_recall(normalized) and not _has_profile_statement(normalized):
        return {}
    return extract_profile_updates(message)


def _merge_fact_values(existing: str | None, new_value: str) -> str:
    if not existing:
        return new_value

    parts: list[str] = []
    for value in (existing, new_value):
        for part in value.split(";"):
            cleaned = part.strip()
            if cleaned and cleaned.casefold() not in {item.casefold() for item in parts}:
                parts.append(cleaned)
    return "; ".join(parts[:8])


def _normalize_for_match(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text.casefold())
    folded = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    return folded.replace("đ", "d")


def _asks_for_memory_recall(normalized: str) -> bool:
    markers = (
        "ten",
        "biet",
        "nhac",
        "nho lai",
        "tom tat",
        "do uong",
        "mon an",
        "nghe",
        "engineer",
        "o dau",
        "noi o",
        "style",
        "kieu tra loi",
        "quan tam",
        "python",
        "ai",
        "pet",
        "corgi",
        "nuoi",
        "3 bullet",
    )
    question_like = (
        "?" in normalized
        or "nhac" in normalized
        or "nho lai" in normalized
        or "tom tat" in normalized
        or "ban biet" in normalized
    )
    return question_like and _contains_any_marker(normalized, markers)


def _has_profile_statement(normalized: str) -> bool:
    markers = (
        "minh ten la",
        "ten minh la",
        "hien o",
        "dang o",
        "minh o",
        "dang la",
        "chuyen sang",
        "nghe nghiep hien tai la",
        "do uong yeu thich la",
        "mon an yeu thich la",
        "muon ban tra loi",
        "hay tra loi",
        "theo dang",
    )
    return any(marker in normalized for marker in markers)


def _is_open_profile_question(normalized: str) -> bool:
    markers = (
        "ten gi",
        "la gi",
        "la ai",
        "o dau",
        "con gi",
        "nhu the nao",
        "mo ta ngan gon minh",
    )
    return any(marker in normalized for marker in markers)


def _requested_profile_parts(normalized: str, facts: dict[str, str]) -> list[str]:
    include_all = "tom tat" in normalized or "ban biet" in normalized
    checks = [
        ("Tên", "name", ("ten", "ai")),
        ("Nơi ở hiện tại", "location", ("o dau", "noi o", "hue", "da nang", "ha noi")),
        ("Nghề nghiệp hiện tại", "profession", ("nghe", "engineer", "viec")),
        ("Đồ uống yêu thích", "favorite_drink", ("do uong", "uong")),
        ("Món ăn yêu thích", "favorite_food", ("mon an", "an")),
        ("Style trả lời", "response_style", ("style", "kieu tra loi", "tra loi", "3 bullet")),
        ("Mối quan tâm", "interests", ("quan tam", "python", "ai", "benchmark", "memory")),
        ("Pet", "pet", ("nuoi", "pet", "corgi", "con gi")),
    ]

    parts = []
    for label, key, markers in checks:
        value = facts.get(key)
        if value and (include_all or _contains_any_marker(normalized, markers)):
            parts.append(f"{label}: {value}")
    return parts


def _profile_summary(facts: dict[str, str]) -> str:
    if not facts:
        return "Mình chưa có đủ thông tin trong User.md để nhắc lại."

    parts = []
    for key in (
        "name",
        "profession",
        "location",
        "favorite_drink",
        "favorite_food",
        "response_style",
        "interests",
        "pet",
    ):
        value = facts.get(key)
        if value:
            parts.append(f"{key}: {value}")
    return "Mình nhớ từ User.md: " + "; ".join(parts) + "."


def _contains_any_marker(normalized: str, markers: tuple[str, ...]) -> bool:
    words = set(normalized.replace("?", " ").replace(",", " ").replace(".", " ").split())
    for marker in markers:
        if len(marker) <= 2:
            if marker in words:
                return True
        elif marker in normalized:
            return True
    return False
