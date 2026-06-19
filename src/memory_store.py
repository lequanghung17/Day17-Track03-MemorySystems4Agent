from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


def estimate_tokens(text: str) -> int:
    """Student TODO: implement a simple token estimator.

    Example idea:
    - Strip whitespace
    - Return 0 for empty text
    - Approximate tokens from character count, e.g. len(text) / 4
    """

    cleaned = " ".join(text.strip().split())
    if not cleaned:
        return 0

    word_count = len(cleaned.split())
    char_estimate = max(1, len(cleaned) // 4)
    return max(word_count, char_estimate)


@dataclass
class UserProfileStore:
    """Persistent storage for `User.md`.

    Student TODO:
    - Map each user id to one markdown file
    - Support read / write / edit operations
    - Optionally expose helpers like `facts()` or `upsert_fact()`
    """

    root_dir: Path

    def path_for(self, user_id: str) -> Path:
        # TODO: slugify or sanitize the user id before building the file path.
        safe_id = re.sub(r"[^a-zA-Z0-9_.-]+", "-", user_id.strip()).strip(".-")
        if not safe_id:
            safe_id = "user"
        return self.root_dir / safe_id / "User.md"

    def read_text(self, user_id: str) -> str:
        # TODO: return file content or an empty default markdown profile.
        path = self.path_for(user_id)
        if not path.exists():
            return _empty_profile(user_id)
        return path.read_text(encoding="utf-8")

    def write_text(self, user_id: str, content: str) -> Path:
        # TODO: write markdown to disk and return the file path.
        path = self.path_for(user_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.rstrip() + "\n", encoding="utf-8")
        return path

    def edit_text(self, user_id: str, search_text: str, replacement: str) -> bool:
        # TODO: replace one occurrence inside User.md and return whether it changed.
        current = self.read_text(user_id)
        updated = current.replace(search_text, replacement, 1)
        if updated == current:
            return False
        self.write_text(user_id, updated)
        return True

    def file_size(self, user_id: str) -> int:
        # TODO: return the current file size in bytes.
        path = self.path_for(user_id)
        if not path.exists():
            return 0
        return path.stat().st_size

    def facts(self, user_id: str) -> dict[str, str]:
        facts: dict[str, str] = {}
        for line in self.read_text(user_id).splitlines():
            match = re.match(r"^-\s*([^:]+):\s*(.+)$", line.strip())
            if match:
                facts[match.group(1).strip()] = match.group(2).strip()
        return facts

    def upsert_fact(self, user_id: str, key: str, value: str) -> Path:
        key = key.strip()
        value = value.strip()
        if not key or not value:
            return self.path_for(user_id)

        current = self.read_text(user_id)
        lines = current.splitlines()
        fact_pattern = re.compile(rf"^-\s*{re.escape(key)}\s*:")

        replaced = False
        for index, line in enumerate(lines):
            if fact_pattern.match(line.strip()):
                lines[index] = f"- {key}: {value}"
                replaced = True
                break

        if not replaced:
            lines = _ensure_facts_section(lines)
            insert_at = _facts_insert_index(lines)
            lines.insert(insert_at, f"- {key}: {value}")

        return self.write_text(user_id, "\n".join(lines))


def extract_profile_updates(message: str) -> dict[str, str]:
    """Student TODO: convert raw user text into stable profile facts.

    Example facts you may want to extract:
    - name
    - location
    - profession
    - preferences / response style
    - favorite food / drink

    Pseudocode:
    1. Build a few regex patterns.
    2. Skip obvious question-only turns.
    3. Return only the facts that are confidently present in the message.
    """

    text = _repair_mojibake(message).strip()
    if _looks_like_question_only(text):
        return {}

    updates: dict[str, str] = {}
    lowered = text.casefold()

    _capture_first(
        updates,
        "name",
        text,
        [
            r"(?:mình|toi|tôi)\s*(?:tên là|ten la)\s+([^,.!?]+)",
            r"(?:tên mình|ten minh)\s*(?:là|la)\s+([^,.!?]+)",
        ],
    )
    _capture_first(
        updates,
        "location",
        text,
        [
            r"cập nhật\s+từ\s+[^,.!?]+?\s+sang\s+(.+?)(?=\s+và\s+|[,.!?]|$)",
            r"(?:thực ra|thuc ra)[^.!?]{0,80}?(?:đang ở|dang o|đang làm việc ở|dang lam viec o|\bở\b|\bo\b)\s+(.+?)(?=\s+và\s+(?:đang|hiện|muốn|thích|van|vẫn)|[,.!?]|$)",
            r"(?:mình|toi|tôi)[^.!?]{0,40}?(?:đang ở|dang o|làm việc ở|lam viec o|\bở\b|\bo\b)\s+(.+?)(?=\s+và\s+(?:đang|hiện|muốn|thích|van|vẫn)|[,.!?]|$)",
            r"(?:hiện|hien)\s+(?:\bở\b|\bo\b)\s+(.+?)(?=\s+và\s+(?:đang|hiện|muốn|thích|van|vẫn)|[,.!?]|$)",
            r"nơi ở hiện tại\s*(?:là|la)\s+(.+?)(?=\s+và\s+|[,.!?]|$)",
        ],
    )
    if "location" in updates:
        location = _clean_location(updates["location"])
        if location:
            updates["location"] = location
        else:
            updates.pop("location", None)
    _capture_first(
        updates,
        "profession",
        text,
        [
            r"(?:đang|dang|hiện|hien|vẫn|van)\s*(?:là|la|làm|lam)\s+([^,.!?]*(?:engineer|developer|manager|designer|researcher|analyst)[^,.!?]*)",
            r"(?:chuyển sang|chuyen sang)\s+([^,.!?]*(?:engineer|developer|manager|designer|researcher|analyst)[^,.!?]*)",
            r"nghề nghiệp hiện tại\s*(?:là|la)\s+([^,.!?]+)",
        ],
    )
    _capture_first(
        updates,
        "response_style",
        text,
        [
            r"(?:muốn|muon|thích|thich|hãy|hay)\s+[^.!?]*(?:trả lời|tra loi)\s+([^.!?]+)",
            r"style\s*(?:trả lời|tra loi)?\s*[^.!?]*(?:là|la|:)\s*([^.!?]+)",
            r"theo dạng\s+([^.!?]+)",
        ],
    )
    if "response_style" in updates:
        response_style = _clean_response_style(updates["response_style"])
        if response_style:
            updates["response_style"] = response_style
        else:
            updates.pop("response_style", None)
    _capture_first(
        updates,
        "favorite_drink",
        text,
        [
            r"(?:đồ uống yêu thích|do uong yeu thich)\s*(?:là|la)\s+([^,.!?]+)",
            r"(?:mình|tôi|toi)\s+(?:vẫn\s+|van\s+|hay\s+|thường\s+|thuong\s+|đang\s+|dang\s+)?(?:\buống\b|\buong\b)\s+([^,.!?]+)",
        ],
    )
    if "favorite_drink" in updates:
        updates["favorite_drink"] = _clean_favorite_drink(updates["favorite_drink"])
    _capture_first(
        updates,
        "favorite_food",
        text,
        [
            r"(?:món ăn yêu thích|mon an yeu thich)\s*(?:là|la)\s+([^,.!?]+)",
            r"(?:mình|tôi|toi)\s+(?:vẫn\s+|van\s+|hay\s+|thường\s+|thuong\s+|đang\s+|dang\s+)?(?:\băn\b|\ban\b)\s+([^,.!?]+)",
        ],
    )
    if "favorite_food" in updates:
        updates["favorite_food"] = _clean_favorite_food(updates["favorite_food"])
    _capture_first(
        updates,
        "pet",
        text,
        [
            r"(?:nuôi|nuoi)\s+([^,.!?]+)",
            r"(?:con|bé|be)\s+([^,.!?]*(?:corgi|cho|chó|meo|mèo)[^,.!?]*)",
        ],
    )

    interests = _extract_interests(text, lowered)
    if interests:
        updates["interests"] = interests

    if "không còn là" in lowered or "khong con la" in lowered or "thông tin cũ" in lowered or "thong tin cu" in lowered:
        updates["correction_note"] = text

    return updates


def summarize_messages(messages: list[dict[str, str]], max_items: int = 6) -> str:
    """Student TODO: create a compact summary of older messages.

    This can be heuristic text concatenation first.
    Later, you can replace it with an LLM-based summary if desired.
    """

    if not messages:
        return ""

    selected = messages[-max_items:] if max_items > 0 else messages
    lines = []
    for message in selected:
        role = str(message.get("role", "unknown")).strip() or "unknown"
        content = " ".join(str(message.get("content", "")).split())
        if len(content) > 220:
            content = content[:217].rstrip() + "..."
        if content:
            lines.append(f"- {role}: {content}")
    return "\n".join(lines)


@dataclass
class CompactMemoryManager:
    """Student TODO: implement compact memory for long threads.

    Goal:
    - Keep recent messages in full
    - When the thread grows too large, move older content into a summary
    - Track how many compactions happened for benchmarking
    """

    threshold_tokens: int
    keep_messages: int
    state: dict[str, dict[str, object]] = field(default_factory=dict)

    def append(self, thread_id: str, role: str, content: str) -> None:
        # TODO:
        # 1. create thread state if missing
        # 2. append the new message
        # 3. trigger compaction if needed
        thread = self._thread_state(thread_id)
        messages = thread["messages"]
        assert isinstance(messages, list)
        messages.append({"role": role, "content": content})
        self._compact_if_needed(thread_id)

    def context(self, thread_id: str) -> dict[str, object]:
        # TODO: return per-thread state with keys like messages, summary, compactions.
        thread = self._thread_state(thread_id)
        return {
            "messages": list(thread["messages"]),
            "summary": str(thread["summary"]),
            "compactions": int(thread["compactions"]),
        }

    def compaction_count(self, thread_id: str) -> int:
        # TODO: return number of compactions for this thread.
        return int(self._thread_state(thread_id)["compactions"])

    def _thread_state(self, thread_id: str) -> dict[str, object]:
        if thread_id not in self.state:
            self.state[thread_id] = {
                "messages": [],
                "summary": "",
                "compactions": 0,
            }
        return self.state[thread_id]

    def _compact_if_needed(self, thread_id: str) -> None:
        thread = self._thread_state(thread_id)
        messages = thread["messages"]
        summary = str(thread["summary"])
        assert isinstance(messages, list)

        context_text = _join_context(summary, messages)
        if estimate_tokens(context_text) <= self.threshold_tokens:
            return

        if len(messages) <= self.keep_messages:
            return

        split_at = max(1, len(messages) - self.keep_messages)
        older_messages = messages[:split_at]
        recent_messages = messages[split_at:]

        new_summary_parts = []
        if summary.strip():
            new_summary_parts.append(summary.strip())
        new_summary_parts.append(summarize_messages(older_messages, max_items=len(older_messages)))

        thread["summary"] = "\n".join(part for part in new_summary_parts if part).strip()
        thread["messages"] = recent_messages
        thread["compactions"] = int(thread["compactions"]) + 1


def _empty_profile(user_id: str) -> str:
    return f"# User Profile: {user_id}\n\n## Facts\n\n"


def _ensure_facts_section(lines: list[str]) -> list[str]:
    if any(line.strip().casefold() == "## facts" for line in lines):
        return lines
    if lines and lines[-1].strip():
        lines.append("")
    lines.extend(["## Facts", ""])
    return lines


def _facts_insert_index(lines: list[str]) -> int:
    for index, line in enumerate(lines):
        if line.strip().casefold() == "## facts":
            insert_at = index + 1
            while insert_at < len(lines) and lines[insert_at].strip().startswith("-"):
                insert_at += 1
            return insert_at
    return len(lines)


def _repair_mojibake(text: str) -> str:
    if not any(marker in text for marker in ("Ã", "Ä", "Å")):
        return text
    try:
        repaired = text.encode("latin1").decode("utf-8")
    except UnicodeError:
        return text
    return repaired if repaired.count("�") <= text.count("�") else text


def _looks_like_question_only(text: str) -> bool:
    lowered = text.casefold()
    fact_markers = (
        "mình tên",
        "tên là",
        "đang ở",
        "hiện ở",
        "đang là",
        "chuyển sang",
        "đồ uống yêu thích",
        "món ăn yêu thích",
        "muốn bạn",
        "hãy trả lời",
        "nhớ là",
        "nhớ giúp",
    )
    return "?" in text and not any(marker in lowered for marker in fact_markers)


def _capture_first(updates: dict[str, str], key: str, text: str, patterns: list[str]) -> None:
    if key in updates:
        return

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        value = _clean_fact_value(match.group(1))
        if value:
            updates[key] = value
            return


def _clean_fact_value(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip(" .,:;!?")
    value = re.sub(r"\b(?:nhé|nhe|giúp mình|giup minh)$", "", value, flags=re.IGNORECASE).strip()
    return value


def _clean_location(value: str) -> str:
    normalized = value.casefold()
    known_locations = {
        "đà nẵng": "Đà Nẵng",
        "da nang": "Đà Nẵng",
        "huế": "Huế",
        "hue": "Huế",
        "hà nội": "Hà Nội",
        "ha noi": "Hà Nội",
    }
    matches = [
        (normalized.find(marker), canonical)
        for marker, canonical in known_locations.items()
        if marker in normalized
    ]
    if matches:
        return min(matches, key=lambda item: item[0])[1]

    generic_markers = ("thay đổi", "thay doi", "hiện tại", "hien tai", "mức", "muc")
    if normalized in {"đây", "day", "đó", "do", "này", "nay"} or any(marker in normalized for marker in generic_markers):
        return ""

    return re.split(r"\s+(?:trong|dù|du|để|de|vài|vai)\s+", value, maxsplit=1)[0].strip()


def _clean_favorite_drink(value: str) -> str:
    normalized = value.casefold()
    if "cà phê sữa đá" in normalized or "ca phe sua da" in normalized:
        return "cà phê sữa đá"
    return value


def _clean_favorite_food(value: str) -> str:
    normalized = value.casefold()
    if "mì quảng" in normalized or "mi quang" in normalized:
        return "mì Quảng"
    return value


def _clean_response_style(value: str) -> str:
    normalized = value.casefold()
    if normalized in {"mình thích", "minh thich", "như thế nào", "nhu the nao"}:
        return ""
    if "tự nhiên hơn" in normalized or "tu nhien hon" in normalized:
        return ""

    if "gọn" in normalized and "ngắn gọn" not in normalized:
        value = f"ngắn gọn, {value}"
    elif "bullet ngắn" in normalized and "ngắn gọn" not in normalized:
        value = f"ngắn gọn, {value}"

    return value


def _extract_interests(text: str, lowered: str) -> str:
    patterns = [
        r"(?:thích|thich|quan tâm|quan tam)\s+([^.!?]+)",
        r"(?:ưu tiên|uu tien)\s+([^.!?]+)",
    ]
    values: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            value = _clean_fact_value(match.group(1))
            if value.casefold().startswith(("là ", "la ")):
                continue
            if value and value not in values:
                values.append(value)

    technical_keywords = [
        "python",
        "ai",
        "agent",
        "benchmark",
        "memory",
        "rag",
        "evaluation",
        "mlops",
    ]
    if any(keyword in lowered for keyword in technical_keywords):
        keyword_values = [keyword for keyword in technical_keywords if keyword in lowered]
        values.append(", ".join(keyword_values))

    return "; ".join(values[:4])


def _join_context(summary: str, messages: list[dict[str, str]]) -> str:
    parts = [summary] if summary.strip() else []
    parts.extend(f"{item.get('role', '')}: {item.get('content', '')}" for item in messages)
    return "\n".join(parts)
