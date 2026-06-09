"""
Pure-function compatibility filter applied BEFORE vector ranking.

Rules are deliberately conservative — when in doubt, allow the candidate
through and let cosine + LLM rerank sort it out. The point here is to
block clear category errors (e.g. an Alarm-section tag matching a Status
Variable) that the LLM was getting wrong on the eval fixture.
"""
from typing import Mapping


# MES template section → equipment entity_type that may be matched
_SECTION_TO_ENTITY_TYPE = {
    "Variables": "variable",
    "Events": "event",
    "Alarms": "alarm",
}


_NUMERIC_TYPES = {"int", "integer", "float", "double", "real", "number", "numeric", "u4", "u8", "i4", "i8"}
_TEXT_TYPES = {"str", "string", "ascii", "text", "char"}
_BOOL_TYPES = {"bool", "boolean", "binary"}
_TIME_TYPES = {"datetime", "date", "time", "timestamp", "utcdatetime"}


def _norm(s: str | None) -> str:
    return (s or "").strip().lower()


def _type_family(t: str) -> str:
    n = _norm(t)
    if n in _NUMERIC_TYPES:
        return "numeric"
    if n in _TEXT_TYPES:
        return "text"
    if n in _BOOL_TYPES:
        return "bool"
    if n in _TIME_TYPES:
        return "time"
    return "other"


def entity_type_for_section(section: str) -> str | None:
    """Returns the equipment entity_type that a template section's tags may match."""
    return _SECTION_TO_ENTITY_TYPE.get(section)


def is_compatible(tag: Mapping, entity: Mapping) -> bool:
    """
    Decide if `entity` is a legal candidate for `tag` before similarity ranking.

    tag    : {"tag_source": "Variables"|"Events"|"Alarms", "expected_type": str}
    entity : {"entity_type": "variable"|"event"|"alarm", "data_type": str}

    Returns False only on clear category errors. Type-family mismatch
    between text/numeric/etc. is treated as a soft signal — we still allow
    the match through so the rerank step can override on strong semantic
    signals. (Today the most common error is cross-category, not cross-type.)
    """
    required = entity_type_for_section(tag.get("tag_source", ""))
    if required is None:
        # Unknown section — be permissive
        return True

    if entity.get("entity_type") != required:
        return False

    # Variables-of-variables: enforce numeric vs text vs time at family level
    if required == "variable":
        tag_fam = _type_family(tag.get("expected_type", ""))
        ent_fam = _type_family(entity.get("data_type", ""))
        if tag_fam != "other" and ent_fam != "other" and tag_fam != ent_fam:
            return False

    return True
