import logging
from typing import Any, Literal
import numpy as np

import json

from source.schemas.secsgem import EquipmentSpec
from source.utils.embedder import VectorStoreManager
from source.utils.llm_factory import LLMStrategy
from source.services.entity_embeddings import build_or_load

logger = logging.getLogger(__name__)

Source = Literal["json", "rag"]


class QAService:

    def __init__(
        self,
        llm_strategy: LLMStrategy,
        vector_store: VectorStoreManager | None = None,
        vector_filters: dict[str, Any] | None = None,
    ) -> None:
        self._llm = llm_strategy.get_model(temperature=0, require_json=False)
        self._llm_json = llm_strategy.get_model(temperature=0, require_json=True)
        self._vector_store = vector_store
        self._vector_filters = vector_filters or {}
        self._embedder = VectorStoreManager.get_embeddings()

    def answer(
        self, 
        query: str, 
        spec: EquipmentSpec, 
        project_id: int, 
        document_id: str, 
        storage_service: Any
    ) -> tuple[str, str, list[str]]:
        """Return (answer_text, source, context_chunks) using the requested category context."""
        q = query.strip()
        
        # 1. Gather context from the primary vector store (if provided)
        text_chunks = []
        table_chunks = []
        
        if self._vector_store:
            text_chunks, table_chunks = self._fetch_context(
                q, spec, project_id, document_id, storage_service, self._vector_store, self._vector_filters
            )

        text_context_str = "\n\n---\n\n".join(text_chunks)
        table_context_str = "\n".join(table_chunks)
        all_chunks = text_chunks + table_chunks

        # 2. Generate final answer
        if not text_chunks and not table_chunks:
            return "No relevant context found in the requested category.", "rag", []

        prompt = (
            "You are an expert equipment engineer. Answer the user's question using ONLY the provided contexts below. "
            "Cite VIDs/CEIDs/AlarmIDs verbatim if present. If the context does not contain the answer, say so.\n\n"
            "CRITICAL CITATION RULE: For every factual claim, you MUST append a citation using the exact [Source: ...] tag provided in the context blocks below.\n\n"
            "[UNSTRUCTURED TEXT CONTEXT]\n"
            f"{text_context_str or 'None'}\n\n"
            "[STRUCTURED TABULAR CONTEXT]\n"
            f"{table_context_str or 'None'}\n\n"
            f"QUESTION: {q}"
        )
        return self._llm.invoke(prompt).content, "rag", all_chunks

    def _fetch_context(
        self, 
        query: str, 
        spec: EquipmentSpec, 
        project_id: int, 
        document_id: str, 
        storage_service: Any,
        vector_store: VectorStoreManager,
        filters: dict
    ) -> tuple[list[str], list[str]]:
        """Fetch text and tabular context from a specific vector store and entity cache."""
        # 1. FAISS Text Chunks Search
        chunks = vector_store.search_with_filters(query, filters, k=6)
        
        formatted_chunks = []
        if chunks:
            for c in chunks:
                doc_name = c.metadata.get("document_name") or document_id
                page_num = c.metadata.get("page_number")
                source_str = f"Source: {doc_name}"
                if page_num:
                    source_str += f", Page {page_num}"
                formatted_chunks.append(f"[{source_str}]\n{c.page_content}")
            
        # 2. Tabular Entity Search
        lines = []
        try:
            cache_path = storage_service.spec_json_path(project_id, document_id).parent / f"{document_id}_entities.npz"
            entity_embeddings = build_or_load(spec, cache_path)
            
            if entity_embeddings.dim > 0:
                query_vector = self._embedder.embed_query(query)
                top_entities = entity_embeddings.search(np.array(query_vector), top_k=10)
                
                if top_entities:
                    for row in top_entities:
                        lines.append(f"- [{row.entity_class}] ID: {row.entity_id} | Name: {row.name} | Desc: {row.description} | Type: {row.data_type} | Unit: {row.unit}")
        except Exception as e:
            logger.error("Failed to perform tabular entity search: %s", e)

        return formatted_chunks, lines
