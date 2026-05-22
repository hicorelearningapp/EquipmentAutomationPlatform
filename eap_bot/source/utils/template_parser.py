import logging
from typing import List, Dict, Any
from source.schemas.mapping import MESTag

logger = logging.getLogger(__name__)

def _extract_tags_from_template(data: Dict[str, Any]) -> List[MESTag]:
    tags = []
    # Variables section
    for v in data.get("Variables", []):
        field_name = v.get("MESField", "")
        if field_name:
            tags.append(MESTag(
                tag_id=field_name,
                name=field_name,
                expected_type=v.get("Type", ""),
            ))
    # Events section
    for e in data.get("Events", []):
        event_name = e.get("EventName", "")
        if event_name:
            tags.append(MESTag(
                tag_id=event_name,
                name=event_name,
                description=e.get("EventType", ""),
            ))
    # Alarms section
    for a in data.get("Alarms", []):
        alarm_type = a.get("AlarmType", "")
        if alarm_type:
            tags.append(MESTag(
                tag_id=alarm_type,
                name=alarm_type,
                description=a.get("Severity", ""),
            ))
    return tags
