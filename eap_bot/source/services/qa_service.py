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
        """Return (answer_text, source, context_chunks) using Agentic Sequential Fallback."""
        q = query.strip()
        
        # 1. Gather initial context from the primary vector store (if provided)
        text_chunks = []
        table_chunks = []
        used_stores = set()
        
        if self._vector_store:
            text_chunks, table_chunks = self._fetch_context(
                q, spec, project_id, document_id, storage_service, self._vector_store, self._vector_filters
            )
            # Mark the initial store's directory as used so we don't query it again
            used_stores.add(str(self._vector_store.vector_dir))

        text_context_str = "\n\n---\n\n".join(text_chunks)
        table_context_str = "\n".join(table_chunks)
        
        # 2. Evaluate if we have enough context
        evaluation = self._evaluate_context(q, text_context_str, table_context_str)
        
        # 3. Agentic Fallback: If not enough context, search other categories
        if not evaluation.get("can_answer", False):
            logger.info("Agent decided initial context is insufficient. Missing: %s. Initiating fallback search...", evaluation.get("missing_info"))
            fallback_query = evaluation.get("missing_info") or q
            
            # Find all available vector stores in the project
            project_dir = storage_service._project_dir(project_id)
            vs_dir = project_dir / storage_service.VECTORSTORE_DIR
            
            if vs_dir.exists():
                for cat_dir in vs_dir.iterdir():
                    if cat_dir.is_dir() and str(cat_dir) not in used_stores and (cat_dir / "index.faiss").exists():
                        logger.info("Fallback searching category store: %s", cat_dir.name)
                        fallback_vs = VectorStoreManager(cat_dir)
                        # We do not restrict by document_id in fallback, we want project-wide knowledge
                        fb_text, fb_table = self._fetch_context(
                            fallback_query, spec, project_id, document_id, storage_service, fallback_vs, {"project_id": project_id}
                        )
                        if fb_text:
                            text_chunks.extend([f"[Fallback Context: {cat_dir.name}]\n{c}" for c in fb_text])
                        if fb_table:
                            table_chunks.extend(fb_table)
                            
            # Rebuild context strings for final answer if fallback added chunks
            text_context_str = "\n\n---\n\n".join(text_chunks)
            table_context_str = "\n".join(table_chunks)

        all_chunks = text_chunks + table_chunks

        # 4. Generate final answer
        if not text_chunks and not table_chunks:
            return "No relevant context found in the project documentation.", "rag", []

        prompt = (
            "You are an expert equipment engineer. Answer the user's question using ONLY the provided contexts below. "
            "Cite VIDs/CEIDs/AlarmIDs verbatim if present. If the context does not contain the answer, say so.\n\n"
            "CRITICAL CITATION RULE: For every factual claim, you MUST append a citation using the format [DocumentName, Page X]. "
            "The DocumentName and Page number are provided in the [UNSTRUCTURED TEXT CONTEXT] blocks below. If page number is unknown, cite the DocumentName.\n\n"
            "[UNSTRUCTURED TEXT CONTEXT]\n"
            f"{text_context_str or 'None'}\n\n"
            "[STRUCTURED TABULAR CONTEXT]\n"
            f"{table_context_str or 'None'}\n\n"
            f"QUESTION: {q}"
        )
        return self._llm.invoke(prompt).content, "rag", all_chunks

    def _evaluate_context(self, query: str, text_context: str, table_context: str) -> dict:
        """Use a fast LLM call to evaluate if the context is sufficient to answer the query."""
        if not text_context and not table_context:
            return {"can_answer": False, "missing_info": query}
            
        prompt = (
            "You are a context evaluator. Your job is to determine if the provided context is sufficient to fully answer the user's question.\n"
            "Respond ONLY with a valid JSON object matching this schema:\n"
            "{\"can_answer\": boolean, \"missing_info\": \"string describing what specific information is missing, or null if can_answer is true\"}\n\n"
            "[CONTEXT]\n"
            f"{text_context}\n{table_context}\n\n"
            f"[QUESTION]\n{query}"
        )
        try:
            raw = self._llm_json.invoke(prompt).content
            if isinstance(raw, list):
                raw = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in raw)
            data = json.loads(raw)
            return data
        except Exception as e:
            logger.warning("Agentic context evaluation failed: %s. Defaulting to True to attempt generation.", e)
            return {"can_answer": True}

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
                doc_name = c.metadata.get("document_name", "Unknown Document")
                page_num = c.metadata.get("page_number", "Unknown Page")
                formatted_chunks.append(f"[Source: {doc_name}, Page {page_num}]\n{c.page_content}")
            
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
