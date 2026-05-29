import logging
from typing import Any, Literal
import numpy as np

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
        vector_store: VectorStoreManager,
        vector_filters: dict[str, Any] | None = None,
    ) -> None:
        self._llm = llm_strategy.get_model(temperature=0, require_json=False)
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
    ) -> tuple[str, Source]:
        """Return (answer_text, source) using Hybrid RAG."""
        q = query.strip()
        return self._hybrid_rag(q, spec, project_id, document_id, storage_service), "rag"

    def _hybrid_rag(
        self, 
        query: str, 
        spec: EquipmentSpec, 
        project_id: int, 
        document_id: str, 
        storage_service: Any
    ) -> str:
        # 1. FAISS Text Chunks Search
        filters = {"tool_id": spec.ToolID, **self._vector_filters}
        chunks = self._vector_store.search_with_filters(query, filters, k=6)
        
        text_context = ""
        if chunks:
            text_context = "\n\n---\n\n".join(c.page_content for c in chunks)
        else:
            logger.warning("RAG: no text chunks found for ToolID=%s", spec.ToolID)
            
        # 2. Tabular Entity Search
        table_context = ""
        try:
            cache_path = storage_service.spec_json_path(project_id, document_id).parent / f"{document_id}_entities.npz"
            entity_embeddings = build_or_load(spec, cache_path)
            
            if entity_embeddings.dim > 0:
                query_vector = self._embedder.embed_query(query)
                top_entities = entity_embeddings.search(np.array(query_vector), top_k=10)
                
                if top_entities:
                    lines = []
                    for row in top_entities:
                        # Convert each entity row to a readable string
                        lines.append(f"- [{row.entity_class}] ID: {row.entity_id} | Name: {row.name} | Desc: {row.description} | Type: {row.data_type} | Unit: {row.unit}")
                    table_context = "\n".join(lines)
        except Exception as e:
            logger.error("Failed to perform tabular entity search: %s", e)

        if not text_context and not table_context:
            return "No relevant context found in the indexed document or tables."

        prompt = (
            "You are an expert equipment engineer. Answer the user's question using ONLY the provided contexts below. "
            "Cite VIDs/CEIDs/AlarmIDs verbatim if present. If the context does not contain the answer, say so.\n\n"
            "[UNSTRUCTURED TEXT CONTEXT]\n"
            f"{text_context or 'None'}\n\n"
            "[STRUCTURED TABULAR CONTEXT]\n"
            f"{table_context or 'None'}\n\n"
            f"QUESTION: {query}"
        )
        return self._llm.invoke(prompt).content
