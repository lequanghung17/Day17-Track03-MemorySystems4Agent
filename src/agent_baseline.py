from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from config import LabConfig, load_config
from memory_store import estimate_tokens, extract_profile_updates
from model_provider import build_chat_model


@dataclass
class SessionState:
    messages: list[dict[str, str]] = field(default_factory=list)
    token_usage: int = 0
    prompt_tokens_processed: int = 0


class BaselineAgent:
    """Student TODO: implement Agent A.

    Requirements:
    - Within-session memory only
    - No persistent `User.md`
    - Should forget long-term facts across new threads
    """

    def __init__(self, config: LabConfig | None = None, force_offline: bool = False) -> None:
        self.config = config or load_config()
        self.force_offline = force_offline
        self.sessions: dict[str, SessionState] = {}

        # TODO: optionally initialize a real LangChain/LangGraph agent when dependencies exist.
        self.langchain_agent = None if force_offline else self._maybe_build_langchain_agent()

    def reply(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        """Student TODO: return the agent response and token accounting.

        Pseudocode:
        - If a live agent exists, call the live path.
        - Otherwise use a deterministic offline path.
        """

        if self.langchain_agent is not None and not self.force_offline:
            try:
                return self._reply_live(user_id=user_id, thread_id=thread_id, message=message)
            except Exception:
                return self._reply_offline(thread_id=thread_id, message=message)

        return self._reply_offline(thread_id=thread_id, message=message)

    def token_usage(self, thread_id: str) -> int:
        # TODO: return cumulative agent token count for one thread.
        return self.sessions.get(thread_id, SessionState()).token_usage

    def prompt_token_usage(self, thread_id: str) -> int:
        # TODO: estimate how much prompt context this baseline kept processing.
        return self.sessions.get(thread_id, SessionState()).prompt_tokens_processed

    def compaction_count(self, thread_id: str) -> int:
        # Baseline has no compact memory.
        return 0

    def _reply_offline(self, thread_id: str, message: str) -> dict[str, Any]:
        """Student TODO: implement a simple offline behavior.

        Suggested behavior:
        - Store the new user message in the session
        - Generate a short deterministic reply
        - Update token counts
        - Never remember facts across different thread ids
        """

        session = self.sessions.setdefault(thread_id, SessionState())

        prompt_messages = session.messages + [{"role": "user", "content": message}]
        prompt_tokens = _estimate_message_tokens(prompt_messages)
        session.prompt_tokens_processed += prompt_tokens

        session.messages.append({"role": "user", "content": message})
        answer = self._offline_response(thread_id=thread_id, message=message)
        agent_tokens = estimate_tokens(answer)

        session.messages.append({"role": "assistant", "content": answer})
        session.token_usage += agent_tokens

        return {
            "agent": "baseline",
            "mode": "offline",
            "thread_id": thread_id,
            "answer": answer,
            "response": answer,
            "agent_tokens": agent_tokens,
            "prompt_tokens": prompt_tokens,
            "total_agent_tokens": session.token_usage,
            "total_prompt_tokens": session.prompt_tokens_processed,
        }

    def _maybe_build_langchain_agent(self):
        """Student TODO: optionally wire `create_agent` + `InMemorySaver` here.

        Use `build_chat_model(self.config.model)` so the baseline can run with any supported provider.
        """

        try:
            return build_chat_model(self.config.model)
        except Exception:
            return None

    def _reply_live(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        session = self.sessions.setdefault(thread_id, SessionState())
        prompt_messages = session.messages + [{"role": "user", "content": message}]
        prompt_tokens = _estimate_message_tokens(prompt_messages)
        session.prompt_tokens_processed += prompt_tokens

        result = self.langchain_agent.invoke(message)
        answer = getattr(result, "content", str(result))
        agent_tokens = estimate_tokens(answer)

        session.messages.append({"role": "user", "content": message})
        session.messages.append({"role": "assistant", "content": answer})
        session.token_usage += agent_tokens

        return {
            "agent": "baseline",
            "mode": "live",
            "user_id": user_id,
            "thread_id": thread_id,
            "answer": answer,
            "response": answer,
            "agent_tokens": agent_tokens,
            "prompt_tokens": prompt_tokens,
            "total_agent_tokens": session.token_usage,
            "total_prompt_tokens": session.prompt_tokens_processed,
        }

    def _offline_response(self, thread_id: str, message: str) -> str:
        facts = self._facts_for_thread(thread_id)
        lowered = message.casefold()

        if _asks_for_profile(lowered):
            parts = []
            if "tên" in lowered or "ten" in lowered or "ai" in lowered:
                parts.append(_fact_sentence("Tên", facts.get("name")))
            if "nghề" in lowered or "nghe" in lowered or "engineer" in lowered:
                parts.append(_fact_sentence("Nghề hiện tại", facts.get("profession")))
            if "ở đâu" in lowered or "o dau" in lowered or "nơi ở" in lowered or "noi o" in lowered:
                parts.append(_fact_sentence("Nơi ở", facts.get("location")))
            if "đồ uống" in lowered or "do uong" in lowered:
                parts.append(_fact_sentence("Đồ uống yêu thích", facts.get("favorite_drink")))
            if "món ăn" in lowered or "mon an" in lowered:
                parts.append(_fact_sentence("Món ăn yêu thích", facts.get("favorite_food")))
            if "style" in lowered or "kiểu trả lời" in lowered or "kieu tra loi" in lowered:
                parts.append(_fact_sentence("Style trả lời", facts.get("response_style")))
            if "quan tâm" in lowered or "quan tam" in lowered:
                parts.append(_fact_sentence("Mối quan tâm", facts.get("interests")))

            known_parts = [part for part in parts if part]
            if known_parts:
                return "Trong thread hiện tại mình nhớ: " + "; ".join(known_parts) + "."
            return "Trong thread hiện tại mình chưa có đủ thông tin để nhắc lại. Baseline không có bộ nhớ dài hạn."

        updates = extract_profile_updates(message)
        if updates:
            visible = ", ".join(f"{key}={value}" for key, value in updates.items() if key != "correction_note")
            return f"Mình đã ghi nhận trong thread hiện tại: {visible}. Baseline sẽ không lưu thông tin này sang thread khác."

        return "Đã nhận. Baseline chỉ dùng lịch sử trong thread hiện tại và không lưu hồ sơ dài hạn."

    def _facts_for_thread(self, thread_id: str) -> dict[str, str]:
        facts: dict[str, str] = {}
        session = self.sessions.get(thread_id)
        if session is None:
            return facts

        for item in session.messages:
            if item.get("role") != "user":
                continue
            facts.update(extract_profile_updates(item.get("content", "")))
        return facts


def _estimate_message_tokens(messages: list[dict[str, str]]) -> int:
    return sum(estimate_tokens(f"{item.get('role', '')}: {item.get('content', '')}") for item in messages)


def _asks_for_profile(lowered: str) -> bool:
    markers = (
        "tên",
        "ten",
        "biết",
        "biet",
        "nhắc lại",
        "nhac lai",
        "đồ uống",
        "do uong",
        "món ăn",
        "mon an",
        "nghề",
        "nghe",
        "ở đâu",
        "o dau",
        "nơi ở",
        "noi o",
        "style",
        "kiểu trả lời",
        "kieu tra loi",
        "quan tâm",
        "quan tam",
    )
    return "?" in lowered and any(marker in lowered for marker in markers)


def _fact_sentence(label: str, value: str | None) -> str:
    if not value:
        return ""
    return f"{label}: {value}"
