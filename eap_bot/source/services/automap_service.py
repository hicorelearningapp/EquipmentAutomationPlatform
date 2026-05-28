"""
AutoMapService — vector-only mapping of MES template tags to equipment entities.

Phase 1: pure cosine similarity + hard-rule entity-type/data-type filter.
Phase 2 (later): LLM rerank for the ambiguous middle band (0.50–0.80).

Writes the result into the template file's `AutoMapping` block only.
Never touches the Events / Variables / Alarms entity arrays — those are
user-curated and updated via the existing PUT /UpdateMesTemplateInfo endpoint.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple

import numpy as np

from source.schemas.automap import (
    AutoMapAlternative,
    AutoMapBlock,
    AutoMapResponse,
    AutoMapStats,
    AutoMapSuggestion,
    NeedsReviewEntry,
)
from source.schemas.secsgem import EquipmentSpec
from source.services.automap_rerank import RerankCandidate, RerankService
from source.services.automap_rules import is_compatible
from source.services.entity_embeddings import EntityEmbeddings, build_or_load
from source.services.storage_service import StorageService
from source.utils.embedder import VectorStoreManager
from source.utils.llm_factory import LLMStrategy

logger = logging.getLogger(__name__)


# Decision thresholds. Hand-picked from the MappingService eval results; will tune on real data.
HIGH_CONFIDENCE = 0.80       # auto-accept above this when the gap is also big enough
GAP_THRESHOLD = 0.10         # required margin between top1 and top2 for auto-accept
RERANK_MIN_SCORE = 0.30      # cosine floor for triggering an LLM rerank
LOW_CONFIDENCE = 0.50        # below this, even after rerank, treat as needs_review
TOP_K = 5

MES_MAP_DIR: Path = Path(__file__).resolve().parent.parent.parent / "MESMapTemplates"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _increment_minor_version(version: str) -> str:
    try:
        major, minor = version.split(".", 1)
        return f"{major}.{int(minor) + 1}"
    except (ValueError, AttributeError):
        return "1.1"


def _resolve_template_path(family: str, template: str) -> Path:
    if not template.lower().endswith(".json"):
        template = f"{template}.json"
    family_dir = (MES_MAP_DIR / family).resolve()
    path = (family_dir / template).resolve()
    if not path.exists() or family_dir not in path.parents:
        raise FileNotFoundError(f"Template '{template}' not found in family '{family}'")
    return path


def _extract_tagged_sections(template: dict) -> List[dict]:
    """
    Pull MES tags out of the template with their source section preserved.

    Each returned dict has keys:
        tag_id, tag_source, name, description, expected_type, expected_unit
    """
    out: List[dict] = []
    for v in template.get("Variables", []):
        field = v.get("MESField", "")
        if not field:
            continue
        out.append({
            "tag_id": field,
            "tag_source": "Variables",
            "name": field,
            "description": v.get("Description", "") or "",
            "expected_type": v.get("Type", "") or "",
            "expected_unit": v.get("Unit", "") or "",
        })
    for e in template.get("Events", []):
        name = e.get("EventName", "")
        if not name:
            continue
        out.append({
            "tag_id": name,
            "tag_source": "Events",
            "name": name,
            "description": e.get("Description", "") or "",
            "expected_type": "",
            "expected_unit": "",
        })
    for a in template.get("Alarms", []):
        atype = a.get("AlarmType", "")
        if not atype:
            continue
        out.append({
            "tag_id": atype,
            "tag_source": "Alarms",
            "name": atype,
            "description": a.get("Description", "") or "",
            "expected_type": "",
            "expected_unit": "",
        })
    return out


def _tag_text_for_embedding(tag: dict) -> str:
    parts = [f"{tag['tag_source']}: {tag['name']}"]
    if tag.get("description"):
        parts.append(f"— {tag['description']}")
    if tag.get("expected_unit"):
        parts.append(f"({tag['expected_unit']})")
    return " ".join(parts)


# ── Spec loading (project_batch preferred, falls back to merging *_list.json) ─

def _load_spec_from_project(storage: StorageService, project_id: int) -> EquipmentSpec:
    # Preferred: a single project_batch.json
    batch_path = storage.spec_json_path(project_id, "project_batch")
    if batch_path.exists():
        return EquipmentSpec.model_validate_json(batch_path.read_text(encoding="utf-8"))

    # Fallback: merge whatever per-document specs exist in ExtractedJson
    extracted_dir = batch_path.parent
    if not extracted_dir.exists():
        raise FileNotFoundError(f"No extracted data for project {project_id} at {extracted_dir}")

    merged = {
        "ToolID": f"project_{project_id}",
        "ToolType": "merged",
        "Protocol": "SECS/GEM",
        "StatusVariables": [],
        "DataVariables": [],
        "Events": [],
        "Alarms": [],
        "RemoteCommands": [],
    }
    files = sorted(p for p in extracted_dir.glob("*.json"))
    if not files:
        raise FileNotFoundError(f"No extracted JSON files in {extracted_dir}")
    for f in files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Skipping unreadable spec file %s: %s", f, exc)
            continue
        for k in ("StatusVariables", "DataVariables", "Events", "Alarms", "RemoteCommands"):
            merged[k].extend(d.get(k, []))

    merged["StatusVariables"] = list({v["SVID"]: v for v in merged["StatusVariables"]}.values())
    merged["DataVariables"] = list({v["DvID"]: v for v in merged["DataVariables"]}.values())
    merged["Events"] = list({v["CEID"]: v for v in merged["Events"]}.values())
    merged["Alarms"] = list({v["AlarmID"]: v for v in merged["Alarms"]}.values())
    merged["RemoteCommands"] = list({v["RCMD"]: v for v in merged["RemoteCommands"]}.values())

    return EquipmentSpec.model_validate(merged)


# ── The service ──────────────────────────────────────────────────────────────

class AutoMapService:

    def __init__(self, storage: StorageService, llm_strategy: LLMStrategy | None = None) -> None:
        self.storage = storage
        self._rerank: RerankService | None = RerankService(llm_strategy) if llm_strategy else None

    def run(self, project_id: int, family: str, template: str) -> AutoMapResponse:
        # 1. Load spec + template
        spec = _load_spec_from_project(self.storage, project_id)
        template_path = _resolve_template_path(family, template)
        template_data = json.loads(template_path.read_text(encoding="utf-8"))
        tags = _extract_tagged_sections(template_data)

        if not tags:
            block = AutoMapBlock(
                generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                project_id=project_id,
                stats=AutoMapStats(total_tags=0),
            )
            new_version = self._persist(template_path, template_data, block)
            return AutoMapResponse(auto_mapping=block, version=new_version, template_path=str(template_path))

        # 2. Build / load entity embeddings (cached per project)
        cache_path = self.storage.spec_json_path(project_id, "project_batch").parent / "entity_embeddings.npz"
        entities = build_or_load(spec, cache_path)

        # 3. Embed tag descriptions in-memory (query side, no need to persist)
        tag_texts = [_tag_text_for_embedding(t) for t in tags]
        embedder = VectorStoreManager.get_embeddings()
        tag_vecs = np.asarray(embedder.embed_documents(tag_texts), dtype=np.float32)
        norms = np.linalg.norm(tag_vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        tag_vecs = tag_vecs / norms

        # 4. Cosine matrix — both sides are L2-normalized, so dot product == cosine
        if entities.vectors.size and tag_vecs.size:
            scores = tag_vecs @ entities.vectors.T          # shape (T, E)
        else:
            scores = np.zeros((len(tags), 0), dtype=np.float32)

        # 5. Per-tag decision
        suggestions: List[AutoMapSuggestion] = []
        needs_review: List[NeedsReviewEntry] = []

        for ti, tag in enumerate(tags):
            row = scores[ti] if scores.shape[1] > 0 else np.zeros((0,), dtype=np.float32)
            # All candidate indices sorted by score desc
            order = np.argsort(-row) if row.size else np.array([], dtype=int)

            # Apply hard-rule filter; keep filtered indices in original score order
            compatible: List[Tuple[int, float]] = []
            for idx in order:
                entity = entities.rows[idx].to_dict()
                if is_compatible(tag, entity):
                    compatible.append((int(idx), float(row[idx])))
                if len(compatible) >= TOP_K:
                    break

            if not compatible:
                needs_review.append(NeedsReviewEntry(
                    tag_id=tag["tag_id"],
                    tag_source=tag["tag_source"],
                    top_score=float(row.max()) if row.size else 0.0,
                    reason="no_compatible_candidates" if row.size else "no_entities_of_type",
                ))
                continue

            top_idx, top_score = compatible[0]
            second_score = compatible[1][1] if len(compatible) > 1 else 0.0
            top_entity = entities.rows[top_idx]
            gap = top_score - second_score

            alternatives = [
                AutoMapAlternative(
                    entity_id=entities.rows[idx].entity_id,
                    entity_type=entities.rows[idx].entity_type,
                    name=entities.rows[idx].name,
                    confidence=score,
                )
                for idx, score in compatible[1:]
            ]

            # Three-way decision: auto-accept / rerank / needs_review
            if top_score >= HIGH_CONFIDENCE and gap >= GAP_THRESHOLD:
                # Clearly the best match — no LLM needed
                suggestions.append(AutoMapSuggestion(
                    tag_id=tag["tag_id"],
                    tag_source=tag["tag_source"],
                    entity_id=top_entity.entity_id,
                    entity_type=top_entity.entity_type,
                    name=top_entity.name,
                    confidence=top_score,
                    method="vector",
                    reasoning=None,
                    alternatives=alternatives,
                ))
                continue

            if top_score < RERANK_MIN_SCORE or self._rerank is None:
                # Either nothing scored well enough to rerank, or LLM not configured
                needs_review.append(NeedsReviewEntry(
                    tag_id=tag["tag_id"],
                    tag_source=tag["tag_source"],
                    top_score=top_score,
                    reason="low_confidence",
                ))
                continue

            # Ambiguous band — ask the LLM to judge between the candidates
            rerank_candidates = [
                RerankCandidate(
                    entity_id=entities.rows[idx].entity_id,
                    entity_type=entities.rows[idx].entity_type,
                    name=entities.rows[idx].name,
                    description=entities.rows[idx].description,
                    data_type=entities.rows[idx].data_type,
                    unit=entities.rows[idx].unit,
                    cosine_score=score,
                )
                for idx, score in compatible
            ]
            result = self._rerank.rerank(tag, rerank_candidates)

            if result.entity_id is None:
                needs_review.append(NeedsReviewEntry(
                    tag_id=tag["tag_id"],
                    tag_source=tag["tag_source"],
                    top_score=top_score,
                    reason="llm_rejected",
                ))
                continue

            # Find the chosen entity row (rerank guarantees entity_id is in the candidate set)
            chosen_idx = next(idx for idx, _ in compatible if entities.rows[idx].entity_id == result.entity_id)
            chosen = entities.rows[chosen_idx]

            # Trust the LLM's own confidence — it has more context than cosine here
            final_confidence = result.confidence

            # Floor: even if the LLM picked something, low confidence means review it
            if final_confidence < LOW_CONFIDENCE:
                needs_review.append(NeedsReviewEntry(
                    tag_id=tag["tag_id"],
                    tag_source=tag["tag_source"],
                    top_score=top_score,
                    reason="llm_low_confidence",
                ))
                continue

            suggestions.append(AutoMapSuggestion(
                tag_id=tag["tag_id"],
                tag_source=tag["tag_source"],
                entity_id=chosen.entity_id,
                entity_type=chosen.entity_type,
                name=chosen.name,
                confidence=final_confidence,
                method="llm_rerank",
                reasoning=result.reasoning or None,
                alternatives=[a for a in alternatives if a.entity_id != chosen.entity_id],
            ))

        # 6. Assemble block + persist
        stats = AutoMapStats(
            auto_accepted=sum(1 for s in suggestions if s.method == "vector" and s.confidence >= HIGH_CONFIDENCE),
            llm_reranked=sum(1 for s in suggestions if s.method == "llm_rerank"),
            needs_review=len(needs_review),
            total_tags=len(tags),
        )
        block = AutoMapBlock(
            generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            project_id=project_id,
            stats=stats,
            suggestions=suggestions,
            needs_review=needs_review,
        )
        new_version = self._persist(template_path, template_data, block)
        response = AutoMapResponse(
            auto_mapping=block,
            version=new_version,
            template_path=str(template_path),
        )
        self.storage.save_automap_result(project_id, family, template, response)
        return response

    # ── Persistence ─────────────────────────────────────────────────────────

    @staticmethod
    def _persist(template_path: Path, template_data: dict, block: AutoMapBlock) -> str:
        """Write block into template['AutoMapping'] and bump Version."""
        existing_version = template_data.get("Version", "1.0")
        new_version = _increment_minor_version(existing_version)
        template_data["AutoMapping"] = block.model_dump()
        template_data["Version"] = new_version
        with open(template_path, "w", encoding="utf-8") as f:
            json.dump(template_data, f, indent=2)
        logger.info("AutoMap persisted to %s (version %s -> %s)", template_path, existing_version, new_version)
        return new_version
