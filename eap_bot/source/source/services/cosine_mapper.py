import logging
from typing import List, Tuple
import numpy as np

from source.schemas.mapping import MESTag, MappingEntry
from source.schemas.secsgem import EquipmentSpec
from source.utils.embedder import VectorStoreManager

logger = logging.getLogger(__name__)

COSINE_THRESHOLD = 0.85

class CosineSimilarityMapper:
    """
    Performs purely mathematical vector matching between MES Tags and Equipment Spec entities.
    Returns high-confidence matches and the remaining (unresolved) MES Tags.
    """

    @staticmethod
    def _tag_text(tag: MESTag) -> str:
        parts = [f"{tag.name}"]
        if tag.description:
            parts.append(f"— {tag.description}")
        if tag.expected_unit:
            parts.append(f"({tag.expected_unit})")
        return " ".join(parts)

    @staticmethod
    def _entity_text(entity: dict) -> str:
        parts = [f"{entity['entity_type']}: {entity['name']}"]
        if entity.get("description"):
            parts.append(f"— {entity['description']}")
        return " ".join(parts)

    @classmethod
    def map_tags(
        cls, spec: EquipmentSpec, target_tags: List[MESTag]
    ) -> Tuple[List[MappingEntry], List[MESTag], List[dict]]:
        """
        Maps tags using cosine similarity.
        Returns:
            (high_confidence_mappings, unresolved_target_tags, unresolved_equipment_entities)
        """
        if not target_tags:
            return [], [], []

        # Gather all equipment entities
        equipment_entities = []
        for v in spec.StatusVariables:
            equipment_entities.append({
                "entity_id": str(v.SVID),
                "entity_type": "variable",
                "name": v.Name,
                "description": v.Description or "",
            })
        for v in spec.DataVariables:
            equipment_entities.append({
                "entity_id": str(v.DvID),
                "entity_type": "variable",
                "name": v.Name,
                "description": "",
            })
        for e in spec.Events:
            equipment_entities.append({
                "entity_id": str(e.CEID),
                "entity_type": "event",
                "name": e.EventName,
                "description": e.Description or "",
            })
        for a in spec.Alarms:
            equipment_entities.append({
                "entity_id": str(a.AlarmID),
                "entity_type": "alarm",
                "name": a.AlarmName,
                "description": a.Description or "",
            })

        if not equipment_entities:
            return [], target_tags, equipment_entities

        # Embed MES tags
        tag_texts = [cls._tag_text(t) for t in target_tags]
        embedder = VectorStoreManager.get_embeddings()
        
        logger.info("Computing embeddings for %d MES Tags and %d Equipment Entities...", len(target_tags), len(equipment_entities))
        tag_vecs = np.asarray(embedder.embed_documents(tag_texts), dtype=np.float32)
        
        # Embed Equipment entities
        entity_texts = [cls._entity_text(e) for e in equipment_entities]
        entity_vecs = np.asarray(embedder.embed_documents(entity_texts), dtype=np.float32)

        # Normalize
        tag_norms = np.linalg.norm(tag_vecs, axis=1, keepdims=True)
        tag_norms[tag_norms == 0] = 1.0
        tag_vecs = tag_vecs / tag_norms

        entity_norms = np.linalg.norm(entity_vecs, axis=1, keepdims=True)
        entity_norms[entity_norms == 0] = 1.0
        entity_vecs = entity_vecs / entity_norms

        # Cosine Similarity Matrix
        scores = tag_vecs @ entity_vecs.T  # shape: (num_tags, num_entities)

        high_confidence_mappings = []
        unresolved_tags = []
        mapped_entity_ids = set()

        for i, tag in enumerate(target_tags):
            row = scores[i]
            top_idx = int(np.argmax(row))
            top_score = float(row[top_idx])

            # Apply hard threshold
            if top_score >= COSINE_THRESHOLD:
                best_entity = equipment_entities[top_idx]
                
                # Check entity type compatibility loosely
                # Alarms usually map to alarm entities. Events to events. Variables to variables.
                if tag.name.lower().endswith("alarm") and best_entity["entity_type"] != "alarm":
                    unresolved_tags.append(tag)
                    continue

                high_confidence_mappings.append(MappingEntry(
                    EquipmentFieldName=best_entity["entity_id"],
                    EntityType=best_entity["entity_type"],
                    MESField=tag.tag_id,
                    Confidence=top_score,
                    Reasoning=f"High vector similarity match ({top_score:.2f})",
                    Method="vector"
                ))
                mapped_entity_ids.add(best_entity["entity_id"])
            else:
                unresolved_tags.append(tag)

        unresolved_entities = [e for e in equipment_entities if e["entity_id"] not in mapped_entity_ids]

        logger.info("Vector pass mapped %d tags automatically. %d tags sent to LLM fallback.", len(high_confidence_mappings), len(unresolved_tags))
        return high_confidence_mappings, unresolved_tags, unresolved_entities
