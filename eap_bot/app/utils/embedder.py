import logging
import re
from pathlib import Path
from typing import Dict, List

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document as LC_Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import settings

logger = logging.getLogger(__name__)


class VectorStoreManager:

    _WS_RE = re.compile(r"[ \t\xa0]+")

    def __init__(self, vector_dir: Path | str = settings.VECTORSTORE_ROOT) -> None:
        self.vector_dir = Path(vector_dir)
        self._faiss_cache: FAISS | None = None
        self._embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )

    def _load_or_create_faiss(self) -> FAISS | None:
        """Return the cached FAISS index, loading from disk if needed."""
        if self._faiss_cache is not None:
            return self._faiss_cache

        if self.vector_dir.exists() and any(self.vector_dir.iterdir()):
            logger.info("Loading FAISS index from disk: %s", self.vector_dir)
            self._faiss_cache = FAISS.load_local(
                str(self.vector_dir),
                self._embeddings,
                allow_dangerous_deserialization=True,
            )
            return self._faiss_cache

        return None

    @classmethod
    def normalize_pdf_text(cls, text: str) -> str:
        if not text:
            return ""
        text = text.replace("\xa0", " ")
        text = cls._WS_RE.sub(" ", text)
        return text.strip()

    def add_document(self, text: str, metadata: Dict) -> bool:
        """Chunk, embed, and persist a document. Updates the in-memory cache."""
        clean = self.normalize_pdf_text(text)

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            separators=["\n\n", "\n", ".", " "],
        )
        chunks = [c for c in splitter.split_text(clean) if c.strip()]
        if not chunks:
            logger.warning("add_document: no usable chunks for metadata=%s", metadata)
            return False

        docs = [
            LC_Document(page_content=chunk, metadata={**metadata, "chunk_id": i})
            for i, chunk in enumerate(chunks)
        ]

        vs = self._load_or_create_faiss()
        if vs is None:
            vs = FAISS.from_documents(docs, self._embeddings)
        else:
            vs.add_documents(docs)

        self.vector_dir.mkdir(parents=True, exist_ok=True)
        vs.save_local(str(self.vector_dir))

        # Update the in-memory cache so the next search sees the new document
        # without a disk round-trip.
        self._faiss_cache = vs
        logger.info(
            "FAISS index updated and cached (%d new chunks, metadata=%s)",
            len(chunks),
            metadata,
        )
        return True

    def search(self, query: str, k: int = 6) -> List[LC_Document]:
        vs = self._load_or_create_faiss()
        if vs is None:
            return []
        return vs.similarity_search(query, k=k)

    def search_with_filters(self, query: str, filters: Dict, k: int = 6) -> List[LC_Document]:
        vs = self._load_or_create_faiss()
        if vs is None:
            return []

        results = vs.similarity_search(query, k=max(k * 4, 25))
        if not filters:
            return results[:k]

        def norm(x):
            return str(x).strip().lower() if x else ""

        filtered = [
            r
            for r in results
            if all(
                not val or norm(val) in norm(r.metadata.get(key))
                for key, val in filters.items()
            )
        ]

        return (filtered or results)[:k]
