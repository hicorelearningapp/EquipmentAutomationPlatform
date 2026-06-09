import logging
from typing import List, Dict, Any
from source.schemas.mapping import MESTag

logger = logging.getLogger(__name__)

def _extract_tags_from_template(data: Dict[str, Any], entity_filter: str = None) -> List[MESTag]:
    tags = []
    # Variables section
    if entity_filter is None or entity_filter == "Variables":
        for v in data.get("Variables", []):
            field_name = v.get("MESVariableName", "")
            description = v.get("MESDescription", "")
            if field_name:
                tags.append(MESTag(
                    tag_id=field_name,
                    name=field_name,
                    description=description,
                    expected_type="",
                ))
    # Events section
    if entity_filter is None or entity_filter == "Events":
        for e in data.get("Events", []):
            event_name = e.get("MESEventName", "")
            if event_name:
                tags.append(MESTag(
                    tag_id=event_name,
                    name=event_name,
                    description=e.get("MESDescription", "")
                ))
    # Alarms section
    if entity_filter is None or entity_filter == "Alarms":
        for a in data.get("Alarms", []):
            alarm_name = a.get("MESAlarmName", "")
            if alarm_name:
                tags.append(MESTag(
                    tag_id=alarm_name,
                    name=alarm_name,
                    description=a.get("MESDescription", "")
                ))
    return tags
