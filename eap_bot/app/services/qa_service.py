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
            if not event.LinkedVIDs:
                return f"Event {event.CEID} ({event.Name}) has no linked VIDs."
            by_vid = {v.VID: v.Name for v in spec.Variables}
            parts = [f"{vid} {by_vid.get(vid, '?')}" for vid in event.LinkedVIDs]
            return f"{event.CEID} {event.Name} -> " + ", ".join(parts)

        if m := self._PATTERNS["trigger_cmd"].search(q):
            target = m.group(1).strip().rstrip("?").strip()
            event = self._find_event(spec, target)
            for t in spec.StateTransitions:
                if event and (t.TriggerEvent in (event.Name, event.CEID)) and t.TriggerCommand:
                    return f"{t.TriggerCommand} (transition {t.FromState} -> {t.ToState})"
                if t.TriggerCommand and target.lower() in t.TriggerCommand.lower():
                    return f"{t.TriggerCommand} (transition {t.FromState} -> {t.ToState})"
            return f"No command found that triggers {target!r}."

        if m := self._PATTERNS["list_alarms_sev"].search(q):
            sev = m.group(1).lower()
            matches = [a for a in spec.Alarms if a.Severity.lower() == sev]
            if not matches:
                return f"No {sev} alarms."
            return ", ".join(
                f"{a.AlarmID} {a.Name}: {a.Description or '(no description)'}"
                for a in matches
            )

        if m := self._PATTERNS["next_state"].search(q):
            target = m.group(1).strip().rstrip("?").strip().lower()
            match_keys = {target}
            for s in spec.States:
                if s.Name.lower() == target or s.StateID.lower() == target:
                    match_keys |= {s.Name.lower(), s.StateID.lower()}
            id_to_name = {s.StateID: s.Name for s in spec.States}
            nexts = [
                f"{t.ToState} ({id_to_name.get(t.ToState, '?')})"
                for t in spec.StateTransitions
                if t.FromState.lower() in match_keys
            ]
            if not nexts:
                return f"No transitions found from {m.group(1).strip().rstrip('?')!r}."
            return ", ".join(nexts)

        if m := self._PATTERNS["list_kind"].search(q):
            kind = m.group(1).lower()
            if kind == "variables":
                items = [f"{v.VID} {v.Name} ({v.Category})" for v in spec.Variables]
            elif kind == "events":
                items = [f"{e.CEID} {e.Name}" for e in spec.Events]
            elif kind == "alarms":
                items = [f"{a.AlarmID} {a.Name} [{a.Severity}]" for a in spec.Alarms]
            elif kind == "commands":
                items = [f"{c.RCMD} {c.Description or ''}".strip() for c in spec.RemoteCommands]
            elif kind == "states":
                items = [f"{s.StateID} {s.Name}" for s in spec.States]
            else:
                items = []
            if not items:
                return f"No {kind} in spec."
            return "\n".join(f"{i + 1}. {item}" for i, item in enumerate(items))

        return None


    def _rag(self, query: str, spec: EquipmentSpec) -> str:
        filters = {"tool_id": spec.ToolID, **self._vector_filters}
        chunks = self._vector_store.search_with_filters(query, filters, k=6)
        if not chunks:
            logger.warning("RAG: no chunks found for ToolID=%s", spec.ToolID)
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
        for e in spec.Events:
            if e.Name.lower() == n or str(e.CEID).lower() == n:
                return e
        for e in spec.Events:
            if n in e.Name.lower():
                return e
        return None
