import json
import logging
from pathlib import Path
from typing import List, Optional, Any

from fastapi import APIRouter, File, HTTPException, UploadFile
import numpy as np

from source.managers.service_container import container
from source.schemas.mapping import (
    MESMappingRequest,
    MESTag,
    SaveMappingRequest
)
from source.schemas.secsgem import EquipmentSpec, StatusVariable, Event, Alarm
from source.services.storage_service import StorageService, StorageError, ProjectNotFoundError
from source.utils.template_parser import _extract_tags_from_template
from source.services.automap_rules import is_compatible
from source.services.entity_embeddings import build_or_load
from source.utils.embedder import VectorStoreManager

logger = logging.getLogger(__name__)


def _safe_int(val: str) -> int:
    try:
        return int(val)
    except ValueError:
        return abs(hash(val)) % 10000000


MAPPING_SECTIONS = ("Variables", "Events", "Alarms")
SECTION_TO_ENTITY_TYPE = {
    "Variables": "variable",
    "Events": "event",
    "Alarms": "alarm",
}


def _is_equipment_field(key: str) -> bool:
    k = key.lower()
    if k.startswith("mes"):
        return False
    if "equipment" in k:
        return True
    if any(x in k for x in ("vid", "ceid", "alid")):
        return True
    return False


def _needs_mapping(entry: dict) -> bool:
    equip_keys = [k for k in entry if _is_equipment_field(k)]
    if not equip_keys:
        return False
    # Skip if ANY equipment field already has a value
    if any(str(entry.get(k, "")).strip() for k in equip_keys):
        return False
    # Needs mapping if at least one equipment field is explicitly empty
    return any(isinstance(entry.get(k), str) and entry[k] == "" for k in equip_keys)


def _get_mes_tag_name(entry: dict, section: str) -> str:
    # Priority 1: MES-prefixed keys (FactoryWorks)
    for key, val in entry.items():
        if key.lower().startswith("mes") and "description" not in key.lower():
            if isinstance(val, str) and val.strip():
                return val.strip()
    # Priority 2: section-specific fallbacks (Camstar NEW_MODEL)
    fallbacks = {
        "Variables": ("mesfield", "variablename"),
        "Events": ("eventname",),
        "Alarms": ("alarmtype", "alarmname"),
    }
    for key, val in entry.items():
        if key.lower() in fallbacks.get(section, ()) and isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _get_mes_description(entry: dict) -> str:
    for key, val in entry.items():
        if "description" in key.lower() and isinstance(val, str):
            return val
    return ""


def _tag_text_for_embedding(tag_name: str, description: str) -> str:
    parts = [tag_name]
    if description:
        parts.append(f"— {description}")
    return " ".join(parts)


def _fill_entry(entry: dict, entity_id: str, entity_name: str, entity_description: str) -> None:
    for key in entry:
        if not isinstance(entry[key], str) or entry[key] != "":
            continue
        if not _is_equipment_field(key):
            continue
        k = key.lower()
        if any(x in k for x in ("vid", "ceid", "alid", "id")):
            entry[key] = entity_id
        elif "name" in k:
            entry[key] = entity_name
        elif "description" in k:
            entry[key] = entity_description
        elif "equipment" in k:
            entry[key] = entity_id


def _entity_details(spec: EquipmentSpec, entity_id: str, entity_type: str) -> tuple[str, str, str]:
    """Returns (id, name, description) or ("", "", "") if not found."""
    eid_str = str(entity_id).strip().lower()
    if entity_type == "variable":
        for v in spec.DataVariables + spec.StatusVariables:
            vid = getattr(v, 'DvID', getattr(v, 'SVID', ''))
            if str(vid).strip().lower() == eid_str or v.Name.lower() == eid_str:
                return (str(vid), v.Name, getattr(v, 'Description', '-'))
    elif entity_type == "event":
        for e in spec.Events:
            ceid = e.CEID
            if str(ceid).strip().lower() == eid_str or e.EventName.lower() == eid_str:
                return (str(ceid), e.EventName, getattr(e, 'Description', '-'))
    elif entity_type == "alarm":
        for a in spec.Alarms:
            alid = a.AlarmID
            aname = getattr(a, 'AlarmName', getattr(a, 'Name', ''))
            if str(alid).strip().lower() == eid_str or aname.lower() == eid_str:
                return (str(alid), aname, getattr(a, 'Description', '-'))
    return ("", "", "")


def _build_batch_prompt(unresolved_by_section: dict, spec: EquipmentSpec) -> str:
    entities = []
    for v in spec.StatusVariables:
        entities.append({
            "entity_id": str(v.SVID),
            "entity_type": "variable",
            "name": v.Name,
            "description": getattr(v, 'Description', '-') or '-'
        })
    for v in spec.DataVariables:
        entities.append({
            "entity_id": str(v.DvID),
            "entity_type": "variable",
            "name": v.Name,
            "description": "-"
        })
    for e in spec.Events:
        entities.append({
            "entity_id": str(e.CEID),
            "entity_type": "event",
            "name": e.EventName,
            "description": getattr(e, 'Description', '-') or '-'
        })
    for a in spec.Alarms:
        aname = getattr(a, 'AlarmName', getattr(a, 'Name', ''))
        entities.append({
            "entity_id": str(a.AlarmID),
            "entity_type": "alarm",
            "name": aname,
            "description": getattr(a, 'Description', '-') or '-'
        })

    return f"""You are a semiconductor automation expert. Your task is to map Equipment Entities (Variables, Events, Alarms) to target MES Tags.

EQUIPMENT ENTITIES:
{json.dumps(entities, indent=2)}

UNRESOLVED MES TAGS BY SECTION:
{json.dumps(unresolved_by_section, indent=2)}

Please provide a JSON object with mappings for each section (Variables, Events, Alarms).
Use the following JSON schema:
{{
  "Variables": [
    {{
      "mes_tag": "MESVariableName",
      "entity_id": "SVID/DvID",
      "entity_name": "VariableName",
      "confidence": 0.9,
      "reasoning": "..."
    }}
  ],
  "Events": [
    {{
      "mes_tag": "MESEventName",
      "entity_id": "CEID",
      "entity_name": "EventName",
      "confidence": 0.85,
      "reasoning": "..."
    }}
  ],
  "Alarms": [
    {{
      "mes_tag": "MESAlarmName",
      "entity_id": "AlarmID",
      "entity_name": "AlarmName",
      "confidence": 0.95,
      "reasoning": "..."
    }}
  ]
}}

GUIDELINES:
1. Make best-effort, fuzzy matches.
2. Only map to compatible types (Variables mapping to variables, Events to events, Alarms to alarms).
3. Do not invent or hallucinate IDs. Only use entity_id values that exist in the EQUIPMENT ENTITIES list.
4. If a tag cannot be mapped, do not include it in the response lists, or set entity_id to null.
5. Only output the JSON object. No markdown formatting, no code block fences, no prose.
"""


def _parse_batch_llm_response(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        json_lines = []
        in_block = False
        for line in lines:
            if line.startswith("```"):
                if in_block:
                    break
                else:
                    in_block = True
                    continue
            if in_block:
                json_lines.append(line)
        if json_lines:
            text = "\n".join(json_lines)
    try:
        return json.loads(text)
    except Exception as exc:
        logger.warning("Failed to parse LLM JSON: %s. Raw: %s", exc, raw)
        return {}


class MappingAPI:
    def __init__(self):
        self.router = APIRouter(tags=["mapping"])
        self.storage = StorageService()
        self.register_routes()

    def register_routes(self):
        self.router.put("/UpdateMapping/{project_id}")(self.update_mapping)
        self.router.post("/AutoMap")(self.auto_map)

    def update_mapping(self, project_id: int, body: SaveMappingRequest):
        try:
            from source.managers.service_container import container
            # Use project_id from path if needed, override body
            body.project_id = project_id

            # Load raw template
            template_name = body.template if body.template.lower().endswith(".json") else f"{body.template}.json"
            template_path = Path("MESMapTemplates") / body.family / template_name
            
            if not template_path.exists():
                raise HTTPException(404, f"Raw template not found: {template_path}")
                
            with open(template_path, "r", encoding="utf-8") as f:
                raw_template = json.load(f)
                
            # Create lookup dictionaries for approved mappings
            # MESField/TagID is the key
            approved_vars = {m.MESField: m.EquipmentFieldName for m in body.Mappings if m.EntityType == "variable"}
            approved_events = {m.MESField: m.EquipmentFieldName for m in body.Mappings if m.EntityType == "event"}
            approved_alarms = {m.MESField: m.EquipmentFieldName for m in body.Mappings if m.EntityType == "alarm"}
            
            # Resolve Equipment Spec to get descriptions
            spec_vars_desc = {}
            spec_events_desc = {}
            spec_alarms_desc = {}
            try:
                _, aggregated = container.project_service.aggregate_project_data(body.project_id)
                spec = EquipmentSpec.model_validate(aggregated.model_dump())
                for v in spec.DataVariables + spec.StatusVariables:
                    vid = getattr(v, 'DvID', getattr(v, 'SVID', ''))
                    spec_vars_desc[str(vid)] = v.Description
                    spec_vars_desc[v.Name] = v.Description
                for e in spec.Events:
                    spec_events_desc[str(e.CEID)] = e.Description
                    spec_events_desc[e.EventName] = e.Description
                for a in spec.Alarms:
                    spec_alarms_desc[str(a.AlarmID)] = a.Description
                    spec_alarms_desc[a.Name] = a.Description
            except Exception:
                pass
            
            
            # Populate EquipmentFieldName in raw template
            if "Variables" in raw_template:
                for item in raw_template["Variables"]:
                    if item.get("MESVariableName") in approved_vars:
                        item["EquipmentVariableName"] = approved_vars[item["MESVariableName"]]
                        item["EquipmentDescription"] = spec_vars_desc.get(str(item["EquipmentVariableName"]), "")
                        
            if "Events" in raw_template:
                for item in raw_template["Events"]:
                    event_name = item.get("MESEventName")
                    if event_name in approved_events:
                        item["EquipmentEventName"] = approved_events[event_name]
                        item["EquipmentDescription"] = spec_events_desc.get(str(item["EquipmentEventName"]), "")
                        
            if "Alarms" in raw_template:
                for item in raw_template["Alarms"]:
                    alarm_name = item.get("MESAlarmName")
                    if alarm_name in approved_alarms:
                        item["EquipmentAlarmName"] = approved_alarms[alarm_name]
                        item["EquipmentDescription"] = spec_alarms_desc.get(str(item["EquipmentAlarmName"]), "")
                        
            # Save the mapped template via storage service
            saved_path = self.storage.save_mes_mapping(body.project_id, body.family, body.template, raw_template)
            
            return {
                "ProjectID": body.project_id,
                "Status": "success",
                "Message": f"Mapping saved to {saved_path}"
            }
        except StorageError as exc:
            raise HTTPException(400, str(exc))
        except Exception as exc:
            logger.exception("Error saving mapping")
            raise HTTPException(500, str(exc))

    # async def upload_mes_tag_document(self, project_id: str, file: UploadFile = File(...)):
    #     if not file.filename or not file.filename.lower().endswith(".pdf"):
    #         raise HTTPException(400, "Only .pdf files are accepted for MES tags")
    #     try:
    #         document_id = self.storage.slugify(file.filename.replace(".pdf", ""))
    #         mes_path = self.storage.mes_tag_path(project_id, document_id)
    #         contents = await file.read()
    #         self.storage.save_pdf(mes_path, contents)
    #         extracted_tags = ["Tag1", "Tag2", "Tag3"]
    #         return {
    #             "ProjectID": project_id,
    #             "DocumentID": document_id,
    #             "Status": "success",
    #             "Message": "MES Tag document uploaded and tags extracted",
    #             "ExtractedTags": extracted_tags,
    #         }
    #     except StorageError as exc:
    #         raise HTTPException(500, str(exc))

    # def get_mes_mapping(self, project_id: int, body: MESMappingRequest):
    #     try:
    #         return container.project_service.get_mes_mapping(project_id, body)
    #     except ProjectNotFoundError as exc:
    #         raise HTTPException(404, str(exc)) from exc
    #     except FileNotFoundError as exc:
    #         raise HTTPException(404, str(exc)) from exc
    #     except Exception as exc:
    #         logger.error("MES mapping failed: %s", exc)
    #         raise HTTPException(500, f"Error generating mapping suggestions: {exc}") from exc

    def auto_map(self, project_id: int, body: dict) -> dict:
        from source.schemas.mapping import AutoMapSectionRequest

        try:
            req = AutoMapSectionRequest.model_validate(body)
        except Exception as exc:
            raise HTTPException(422, f"Invalid request body format: {exc}")

        family = body.get("family", "")
        template = body.get("template", "")

        # 1. Resolve Equipment Spec
        try:
            try:
                spec_json = container.project_service.storage.read_spec_json(project_id, "project_batch")
                spec = EquipmentSpec.model_validate_json(spec_json)
            except Exception:
                metadata, aggregated = container.project_service.aggregate_project_data(project_id)
                spec = EquipmentSpec.model_validate(aggregated.model_dump())
        except Exception as exc:
            logger.error("Failed to load project extractions for project %s: %s", project_id, exc)
            raise HTTPException(404, f"Could not find extraction data for project {project_id}. {exc}")

        # 2. Build / load entity embeddings
        cache_path = self.storage.spec_json_path(project_id, "project_batch").parent / "entity_embeddings.npz"
        entities = build_or_load(spec, cache_path)

        # 3. Create a clean deepish copy of body mapping sections to mutate
        result = dict(body)
        for section in MAPPING_SECTIONS:
            if section in result:
                result[section] = [dict(item) for item in result[section]]

        # 4. Extract unresolved entries needing mapping
        unresolved_list = []
        unresolved_by_section = {
            "Variables": [],
            "Events": [],
            "Alarms": []
        }

        for section in MAPPING_SECTIONS:
            items = result.get(section, [])
            for i, entry in enumerate(items):
                if not _needs_mapping(entry):
                    # Populate description for already mapped entries
                    equip_keys = [k for k in entry if _is_equipment_field(k)]
                    filled_val = None
                    for k in equip_keys:
                        val = str(entry.get(k, "")).strip()
                        if val:
                            filled_val = val
                            break
                    if filled_val:
                        _, _, entity_desc = _entity_details(spec, filled_val, SECTION_TO_ENTITY_TYPE[section])
                        for k in entry:
                            if "description" in k.lower() and not k.lower().startswith("mes"):
                                entry[k] = entity_desc
                    continue

                tag_name = _get_mes_tag_name(entry, section)
                if not tag_name:
                    logger.warning("Empty MES tag name in section %s entry: %s", section, entry)
                    continue

                desc = _get_mes_description(entry)
                unresolved_by_section[section].append({
                    "tag_name": tag_name,
                    "description": desc
                })
                unresolved_list.append({
                    "section": section,
                    "index": i,
                    "tag_name": tag_name,
                    "description": desc,
                    "entry": entry
                })

        # 5. Local Vector Similarity Pass
        still_unresolved = []
        if unresolved_list:
            tag_texts = [_tag_text_for_embedding(item["tag_name"], item["description"]) for item in unresolved_list]
            embedder = VectorStoreManager.get_embeddings()
            tag_vecs = np.asarray(embedder.embed_documents(tag_texts), dtype=np.float32)
            norms = np.linalg.norm(tag_vecs, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            tag_vecs = tag_vecs / norms

            if entities.vectors.size and tag_vecs.size:
                scores = tag_vecs @ entities.vectors.T
            else:
                scores = np.zeros((len(unresolved_list), 0), dtype=np.float32)

            for ti, item in enumerate(unresolved_list):
                row = scores[ti] if scores.shape[1] > 0 else np.zeros((0,), dtype=np.float32)
                order = np.argsort(-row) if row.size else np.array([], dtype=int)

                compatible = []
                expected_type = item["entry"].get("Type") or item["entry"].get("ValueType") or ""
                tag_dict = {
                    "tag_source": item["section"],
                    "expected_type": expected_type
                }
                for idx in order:
                    entity_dict = entities.rows[idx].to_dict()
                    if is_compatible(tag_dict, entity_dict):
                        compatible.append((int(idx), float(row[idx])))
                    if len(compatible) >= 5: # TOP_K = 5
                        break

                if compatible:
                    top_idx, top_score = compatible[0]
                    second_score = compatible[1][1] if len(compatible) > 1 else 0.0
                    gap = top_score - second_score
                    top_entity = entities.rows[top_idx]

                    if top_score >= 0.80 and gap >= 0.10:
                        _fill_entry(item["entry"], top_entity.entity_id, top_entity.name, top_entity.description)
                        logger.info("AutoMap vector auto-accept for tag %s: ID=%s Name=%s Score=%f", 
                                    item["tag_name"], top_entity.entity_id, top_entity.name, top_score)
                    else:
                        still_unresolved.append(item)
                else:
                    still_unresolved.append(item)

        # 6. Single Batch LLM Fallback Pass
        if still_unresolved:
            unresolved_by_section_llm = {
                "Variables": [],
                "Events": [],
                "Alarms": []
            }
            for item in still_unresolved:
                unresolved_by_section_llm[item["section"]].append({
                    "mes_tag": item["tag_name"],
                    "description": item["description"]
                })
            # Remove empty sections
            unresolved_by_section_llm = {k: v for k, v in unresolved_by_section_llm.items() if v}

            prompt = _build_batch_prompt(unresolved_by_section_llm, spec)
            try:
                llm = container.mapping_service._llm
                raw = llm.invoke(prompt).content
                if isinstance(raw, list):
                    raw = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in raw)
                llm_data = _parse_batch_llm_response(raw)
            except Exception as e:
                logger.warning("Primary batch LLM mapping failed: %s. Retrying with fallback model.", e)
                try:
                    llm_retry = container.mapping_service._llm_retry
                    raw = llm_retry.invoke(prompt).content
                    if isinstance(raw, list):
                        raw = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in raw)
                    llm_data = _parse_batch_llm_response(raw)
                except Exception as retry_exc:
                    logger.error("Fallback batch LLM mapping failed: %s", retry_exc)
                    llm_data = {}

            # Apply LLM recommendations
            for section, suggestions in llm_data.items():
                if section not in MAPPING_SECTIONS:
                    continue
                for sugg in suggestions:
                    mes_tag = sugg.get("mes_tag")
                    entity_id = sugg.get("entity_id")
                    confidence = sugg.get("confidence", 0.0)
                    if not mes_tag or not entity_id or confidence < 0.30:
                        continue

                    entity_type = SECTION_TO_ENTITY_TYPE[section]
                    eid, ename, edesc = _entity_details(spec, str(entity_id), entity_type)
                    if not eid:
                        logger.warning("LLM mapping ID not found in spec: %s (Type: %s)", entity_id, entity_type)
                        continue

                    # Apply to matching unresolved item
                    for item in still_unresolved:
                        if item["section"] == section and item["tag_name"] == mes_tag:
                            _fill_entry(item["entry"], eid, ename, edesc)
                            logger.info("AutoMap LLM mapped tag %s: ID=%s Name=%s Score=%f", 
                                        mes_tag, eid, ename, confidence)
                            break

        # 7. Persist result
        if family and template:
            template_name = template if template.lower().endswith(".json") else f"{template}.json"
            try:
                self.storage.save_automap_result(project_id, family, template_name, result)
            except Exception as exc:
                logger.error("Failed to save automap result: %s", exc)
                raise HTTPException(500, f"Failed to save automap result: {exc}")

        # Update mes_mapping.json so they appear in /LoadProject
        try:
            from source.schemas.mapping import ProjectMapping, VariableMapping
            mapping = self.storage.get_mapping(project_id)
            
            # Ensure mappings dictionary structure exists
            if not isinstance(mapping.Mappings, dict):
                mapping.Mappings = {}
                
            fam = family or "DefaultFamily"
            tpl = template or "DefaultTemplate.json"
            if not tpl.lower().endswith(".json"):
                tpl = f"{tpl}.json"
                
            if fam not in mapping.Mappings:
                mapping.Mappings[fam] = {}
            if tpl not in mapping.Mappings[fam]:
                mapping.Mappings[fam][tpl] = {
                    "Variables": [],
                    "Events": [],
                    "Alarms": []
                }
                
            vars_list = []
            events_list = []
            alarms_list = []

            for entry in result.get("Variables", []):
                mes_tag = _get_mes_tag_name(entry, "Variables")
                vid = str(entry.get("VID") or entry.get("EquipmentVariableName") or "").strip()
                if mes_tag and vid:
                    vars_list.append(VariableMapping(
                        MESTag=mes_tag,
                        SVID=vid,
                        CEID="",
                        Description=entry.get("EquipmentDescription", "")
                    ))

            for entry in result.get("Events", []):
                mes_tag = _get_mes_tag_name(entry, "Events")
                ceid = str(entry.get("CEID") or entry.get("EquipmentEventName") or "").strip()
                if mes_tag and ceid:
                    events_list.append(VariableMapping(
                        MESTag=mes_tag,
                        SVID="",
                        CEID=ceid,
                        Description=entry.get("EquipmentDescription", "")
                    ))

            for entry in result.get("Alarms", []):
                mes_tag = _get_mes_tag_name(entry, "Alarms")
                alid = str(entry.get("ALID") or entry.get("EquipmentAlarmName") or "").strip()
                if mes_tag and alid:
                    alarms_list.append(VariableMapping(
                        MESTag=mes_tag,
                        SVID=alid,
                        CEID="",
                        Description=entry.get("EquipmentDescription", "")
                    ))

            mapping.Mappings[fam][tpl] = {
                "Variables": vars_list,
                "Events": events_list,
                "Alarms": alarms_list
            }
            self.storage.save_mapping(project_id, mapping)
            logger.info("Updated nested mes_mapping.json for project %s", project_id)
        except Exception as exc:
            logger.warning("Failed to update mapping file for project %s: %s", project_id, exc)

        return result
