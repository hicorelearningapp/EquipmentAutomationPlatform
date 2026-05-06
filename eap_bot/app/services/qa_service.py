import logging
import re
from typing import Any, Literal

from app.schemas.secsgem import EquipmentSpec
from app.utils.embedder import VectorStoreManager
from app.utils.llm_factory import LLMStrategy

logger = logging.getLogger(__name__)

Source = Literal["json", "rag"]


class QAService:


    _PATTERNS: dict[str, re.Pattern] = {
        "linked_vars": re.compile(
            r"which variables.*(?:in|for|linked to)\s+(.+?)\??$", re.IGNORECASE
        ),
        "trigger_cmd": re.compile(
            r"what (?:command|rcmd) triggers\s+(.+?)\??$", re.IGNORECASE
        ),
        "list_alarms_sev": re.compile(
            r"list (critical|warning|info) alarms?", re.IGNORECASE
        ),
        "next_state": re.compile(
            r"what state follows\s+(.+?)\??$", re.IGNORECASE
        ),
        "list_kind": re.compile(
            r"list (events|variables|alarms|commands|states)", re.IGNORECASE
        ),
    }

    def __init__(
        self,
        llm_strategy: LLMStrategy,
        vector_store: VectorStoreManager,
        vector_filters: dict[str, Any] | None = None,
    ) -> None:
        # LLM used only for RAG-based answers (JSON answers need no LLM call).
        self._llm = llm_strategy.get_model(temperature=0, require_json=False)
        self._vector_store = vector_store
        self._vector_filters = vector_filters or {}


    def answer(self, query: str, spec: EquipmentSpec) -> tuple[str, Source]:
        """Return (answer_text, source) where source is 'json' or 'rag'."""
        q = query.strip()
        json_answer = self._try_json(q, spec)
        if json_answer is not None:
            return json_answer, "json"
        return self._rag(q, spec), "rag"


    def _try_json(self, q: str, spec: EquipmentSpec) -> str | None:
        if m := self._PATTERNS["linked_vars"].search(q):
            target = m.group(1).strip().rstrip("?").strip()
            event = self._find_event(spec, target)
            if not event:
                return f"No event matching {target!r} found in spec."
            if not event.linked_vids:
                return f"Event {event.ceid} ({event.name}) has no linked VIDs."
            by_vid = {v.vid: v.name for v in spec.variables}
            parts = [f"{vid} {by_vid.get(vid, '?')}" for vid in event.linked_vids]
            return f"{event.ceid} {event.name} -> " + ", ".join(parts)

        if m := self._PATTERNS["trigger_cmd"].search(q):
            target = m.group(1).strip().rstrip("?").strip()
            event = self._find_event(spec, target)
            for t in spec.state_transitions:
                if event and (t.trigger_event in (event.name, event.ceid)) and t.trigger_command:
                    return f"{t.trigger_command} (transition {t.from_state} -> {t.to_state})"
                if t.trigger_command and target.lower() in t.trigger_command.lower():
                    return f"{t.trigger_command} (transition {t.from_state} -> {t.to_state})"
            return f"No command found that triggers {target!r}."

        if m := self._PATTERNS["list_alarms_sev"].search(q):
            sev = m.group(1).lower()
            matches = [a for a in spec.alarms if a.severity == sev]
            if not matches:
                return f"No {sev} alarms."
            return ", ".join(
                f"{a.alarm_id} {a.name}: {a.description or '(no description)'}"
                for a in matches
            )

        if m := self._PATTERNS["next_state"].search(q):
            target = m.group(1).strip().rstrip("?").strip().lower()
            match_keys = {target}
            for s in spec.states:
                if s.name.lower() == target or s.state_id.lower() == target:
                    match_keys |= {s.name.lower(), s.state_id.lower()}
            id_to_name = {s.state_id: s.name for s in spec.states}
            nexts = [
                f"{t.to_state} ({id_to_name.get(t.to_state, '?')})"
                for t in spec.state_transitions
                if t.from_state.lower() in match_keys
            ]
            if not nexts:
                return f"No transitions found from {m.group(1).strip().rstrip('?')!r}."
            return ", ".join(nexts)

        if m := self._PATTERNS["list_kind"].search(q):
            kind = m.group(1).lower()
            if kind == "variables":
                items = [f"{v.vid} {v.name} ({v.category})" for v in spec.variables]
            elif kind == "events":
                items = [f"{e.ceid} {e.name}" for e in spec.events]
            elif kind == "alarms":
                items = [f"{a.alarm_id} {a.name} [{a.severity}]" for a in spec.alarms]
            elif kind == "commands":
                items = [f"{c.rcmd} {c.description or ''}".strip() for c in spec.remote_commands]
            elif kind == "states":
                items = [f"{s.state_id} {s.name}" for s in spec.states]
            else:
                items = []
            if not items:
                return f"No {kind} in spec."
            return "\n".join(f"{i + 1}. {item}" for i, item in enumerate(items))

        return None


    def _rag(self, query: str, spec: EquipmentSpec) -> str:
        filters = {"tool_id": spec.tool_id, **self._vector_filters}
        chunks = self._vector_store.search_with_filters(query, filters, k=6)
        if not chunks:
            logger.warning("RAG: no chunks found for tool_id=%s", spec.tool_id)
            return "No relevant context found in the indexed document."

        context = "\n\n---\n\n".join(c.page_content for c in chunks)
        prompt = (
            "Answer using only the context below. Cite VIDs/CEIDs verbatim if present. "
            "If the context does not contain the answer, say so.\n\n"
            f"CONTEXT:\n{context}\n\nQUESTION: {query}"
        )
        return self._llm.invoke(prompt).content


    def _find_event(self, spec: EquipmentSpec, needle: str):
        n = needle.lower()
        for e in spec.events:
            if e.name.lower() == n or e.ceid.lower() == n:
                return e
        for e in spec.events:
            if n in e.name.lower():
                return e
        return None
