"""Local text embeddings with ONNX Runtime.

Replaces sentence-transformers/PyTorch with the same model (all-MiniLM-L6-v2) in ONNX form.
Measured in Phase 2: identical vectors to six decimal places and identical search ranking,
but ~15 MB of libraries instead of ~700 MB and a 1 s model load instead of ~19 s.
See LOCAL_EXE_IMPLEMENTATION_PLAN.md.

The steps match what sentence-transformers did: tokenize, run the model, average the token
vectors using the attention mask, then scale each vector to unit length.

Model files are looked for in EAP_EMBEDDING_MODEL_DIR, otherwise in the app folder
(models/onnx/all-MiniLM-L6-v2 - see app_paths.py). They live inside the backend folder so a
copy of it, which is how the tests run, brings the model along. Download them with
packaging/download_assets.py.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List

import numpy as np
from langchain_core.embeddings import Embeddings

from source.app_paths import app_dir

logger = logging.getLogger(__name__)

MODEL_NAME = "all-MiniLM-L6-v2"
MAX_TOKENS = 256  # the model's limit, the same value sentence-transformers used
BATCH_SIZE = 32


def model_dir() -> Path:
    configured = os.environ.get("EAP_EMBEDDING_MODEL_DIR")
    if configured:
        return Path(configured)
    return app_dir() / "models" / "onnx" / MODEL_NAME


class OnnxEmbeddings(Embeddings):
    """Embeddings for FAISS and the rest of LangChain, without PyTorch."""

    def __init__(self, directory: Path | str | None = None) -> None:
        # Imported here so that loading this module stays cheap.
        import onnxruntime
        from tokenizers import Tokenizer

        directory = Path(directory) if directory else model_dir()
        model_file = directory / "model.onnx"
        if not model_file.exists():
            raise FileNotFoundError(
                f"Embedding model not found at {model_file}. Run packaging/download_assets.py."
            )

        self._tokenizer = Tokenizer.from_file(str(directory / "tokenizer.json"))
        self._tokenizer.enable_truncation(max_length=MAX_TOKENS)
        self._tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
        self._session = onnxruntime.InferenceSession(
            str(model_file), providers=["CPUExecutionProvider"]
        )
        self._input_names = {i.name for i in self._session.get_inputs()}
        logger.info("Embeddings: using %s", model_file)

    def _embed_batch(self, texts: List[str]) -> np.ndarray:
        encoded = self._tokenizer.encode_batch(texts)
        attention_mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)
        inputs = {
            "input_ids": np.array([e.ids for e in encoded], dtype=np.int64),
            "attention_mask": attention_mask,
        }
        if "token_type_ids" in self._input_names:
            inputs["token_type_ids"] = np.array([e.type_ids for e in encoded], dtype=np.int64)

        token_vectors = self._session.run(None, inputs)[0]  # (texts, tokens, 384)
        mask = attention_mask[..., None].astype(np.float32)
        pooled = (token_vectors * mask).sum(axis=1) / np.clip(mask.sum(axis=1), 1e-9, None)
        return pooled / np.clip(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12, None)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        vectors: List[List[float]] = []
        for start in range(0, len(texts), BATCH_SIZE):
            vectors.extend(self._embed_batch(texts[start : start + BATCH_SIZE]).tolist())
        return vectors

    def embed_query(self, text: str) -> List[float]:
        return self._embed_batch([text])[0].tolist()
