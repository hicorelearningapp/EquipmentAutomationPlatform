"""
Builds and caches per-entity embedding vectors for an EquipmentSpec.

One vector per SVID / DVID / CEID / AlarmID. Cached to a .npz file
alongside the spec so subsequent AutoMap calls on the same project
don't re-embed. Cache is invalidated whenever the entity set changes
(by hashing the structured fingerprint).
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List

import numpy as np

from source.schemas.secsgem import EquipmentSpec
from source.utils.embedder import VectorStoreManager

logger = logging.getLogger(__name__)


@dataclass
class EntityRow:
    entity_id: str
    entity_type: str    # "variable" | "event" | "alarm"
    name: str
    description: str
    data_type: str
    unit: str

    def to_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "name": self.name,
            "description": self.description,
            "data_type": self.data_type,
            "unit": self.unit,
        }

    def text_for_embedding(self) -> str:
        parts = [self.name]
        if self.description:
            parts.append(f"— {self.description}")
        if self.unit:
            parts.append(f"({self.unit})")
        return " ".join(parts)


def flatten_spec(spec: EquipmentSpec) -> List[EntityRow]:
    rows: List[EntityRow] = []
    for v in spec.StatusVariables:
        rows.append(EntityRow(
            entity_id=str(v.SVID),
            entity_type="variable",
            name=v.Name,
            description=v.Description or "",
            data_type=v.DataType or "",
            unit="",
        ))
    for v in spec.DataVariables:
        rows.append(EntityRow(
            entity_id=str(v.DvID),
            entity_type="variable",
            name=v.Name,
            description="",
            data_type=v.ValueType or "",
            unit=v.Unit or "",
        ))
    for e in spec.Events:
        rows.append(EntityRow(
            entity_id=str(e.CEID),
            entity_type="event",
            name=e.Name,
            description=e.Description or "",
            data_type="",
            unit="",
        ))
    for a in spec.Alarms:
        rows.append(EntityRow(
            entity_id=str(a.AlarmID),
            entity_type="alarm",
            name=a.Name,
            description=a.Description or "",
            data_type="",
            unit="",
        ))
    return rows


def _fingerprint(rows: List[EntityRow]) -> str:
    payload = json.dumps([r.to_dict() for r in rows], sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class EntityEmbeddings:
    """Holds aligned metadata + vectors for one project."""

    def __init__(self, rows: List[EntityRow], vectors: np.ndarray, fingerprint: str) -> None:
        assert len(rows) == vectors.shape[0], "rows/vectors must be aligned"
        self.rows = rows
        self.vectors = vectors            # shape (E, D), L2-normalized
        self.fingerprint = fingerprint

    @property
    def dim(self) -> int:
        return int(self.vectors.shape[1]) if self.vectors.size else 0


def build_or_load(spec: EquipmentSpec, cache_path: Path) -> EntityEmbeddings:
    """
    Returns an EntityEmbeddings. Loads from cache if the spec fingerprint matches,
    otherwise embeds from scratch and writes the cache.
    """
    rows = flatten_spec(spec)
    fp = _fingerprint(rows)

    if cache_path.exists():
        try:
            data = np.load(cache_path, allow_pickle=True)
            if str(data["fingerprint"]) == fp:
                cached_rows = [EntityRow(**r) for r in data["rows"].tolist()]
                logger.info("EntityEmbeddings: cache hit (%d rows) %s", len(cached_rows), cache_path)
                return EntityEmbeddings(cached_rows, data["vectors"], fp)
            logger.info("EntityEmbeddings: cache stale, re-embedding")
        except Exception as exc:
            logger.warning("EntityEmbeddings: cache unreadable (%s), re-embedding", exc)

    embedder = VectorStoreManager.get_embeddings()
    texts = [r.text_for_embedding() for r in rows]
    if not texts:
        vectors = np.zeros((0, 384), dtype=np.float32)
    else:
        raw = embedder.embed_documents(texts)
        vectors = np.asarray(raw, dtype=np.float32)
        # MiniLM with normalize_embeddings=True returns unit vectors already,
        # but renormalize defensively in case the embedder config changes.
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        vectors = vectors / norms

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        cache_path,
        rows=np.array([r.to_dict() for r in rows], dtype=object),
        vectors=vectors,
        fingerprint=fp,
    )
    logger.info("EntityEmbeddings: embedded %d rows, cached to %s", len(rows), cache_path)
    return EntityEmbeddings(rows, vectors, fp)
