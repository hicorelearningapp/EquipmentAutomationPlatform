# Implementation Plan: Per-Category Vector Stores + Table Vector Store

## Overview

This document describes every change needed to implement three features:

1. **Per-category vector stores** — instead of one single FAISS index per project, each `DocumentCategory` gets its own FAISS subdirectory.
2. **Category-filtered `/Ask` endpoint** — the caller can choose which document category to search, or search all of them.
3. **Table vector store** — CSV rows extracted by `pdfplumber` are also embedded and indexed into a dedicated `tables/` FAISS store so structured data is queryable.

---

## Repository structure (relevant files only)

```
eap_bot/
  source/
    managers/
      service_container.py
    routers/
      equipment_routes.py       ← delete_document needs updating
      project_routes.py         ← ask_project needs updating
    schemas/
      project.py                ← AskRequest needs a new field
    services/
      document_service.py       ← analyze_document vectorstore call changes
      equipment_extractor.py    ← _extract_and_save_tables must also index rows
      storage_service.py        ← new helper methods for category-aware paths
    utils/
      embedder.py               ← NO CHANGES NEEDED
```

---

## Detailed changes — file by file

---

### FILE 1: `source/schemas/project.py`

**What to change:** Add an optional `DocumentCategory` field to `AskRequest`.

**Find this class:**
```python
class AskRequest(BaseModel):
    Category: str
    Question: str
```

**Replace with:**
```python
class AskRequest(BaseModel):
    Category: str
    Question: str
    DocumentCategory: Optional[str] = None
    # Accepted values: any DocumentCategory enum value string (e.g. "GEM Manual",
    # "User Manuals", "Troubleshooting Guidance", "Variable Files", "SML Scripts"),
    # the special string "tables" to search only the table store,
    # or None / omitted to search ALL stores and merge results.
```

No other changes to this file.

---

### FILE 2: `source/services/storage_service.py`

**What to change:** Add a new directory constant and two new path-helper methods.

#### Change 2a — Add directory constant

**Find:**
```python
EXTRACTED_TABLES_DIR = "ExtractedTables"
```

**Replace with:**
```python
EXTRACTED_TABLES_DIR = "ExtractedTables"
VECTORSTORE_DIR = "Vectorstore"
```

> Note: `VECTORSTORE_DIR` likely already exists. If it does, do NOT add it again. Just confirm it is there.

#### Change 2b — Add `vectorstore_path_for_category` method

Add this method anywhere after the existing `vectorstore_path` method:

```python
def vectorstore_path_for_category(self, project_id: int, category_slug: str) -> Path:
    """
    Return the FAISS directory for a specific document category or 'tables'.

    category_slug must be one of:
        "gem_manual", "user_manuals", "troubleshooting_guidance",
        "variable_files", "sml_scripts", "tables"

    These slugs are derived by lowercasing the DocumentCategory enum value
    and replacing spaces with underscores.

    Example:
        DocumentCategory.GEM_MANUAL -> "gem_manual"
        DocumentCategory.USER_MANUALS -> "user_manuals"
        "tables" -> "tables"  (special, not a DocumentCategory)
    """
    self.get_project(project_id)  # raises ProjectNotFoundError if missing
    return self._project_dir(project_id) / self.VECTORSTORE_DIR / category_slug
```

#### Change 2c — Add `all_vectorstore_paths` method

Add this method directly after `vectorstore_path_for_category`:

```python
def all_vectorstore_paths(self, project_id: int) -> dict[str, Path]:
    """
    Return a dict mapping category_slug -> Path for every known
    FAISS subdirectory under this project's Vectorstore/ folder.

    Only returns paths that actually exist on disk (i.e. at least
    one document of that category has been analyzed).

    Keys: "gem_manual", "user_manuals", "troubleshooting_guidance",
          "variable_files", "sml_scripts", "tables"
    """
    self.get_project(project_id)
    base = self._project_dir(project_id) / self.VECTORSTORE_DIR
    all_slugs = [
        "gem_manual",
        "user_manuals",
        "troubleshooting_guidance",
        "variable_files",
        "sml_scripts",
        "tables",
    ]
    return {
        slug: base / slug
        for slug in all_slugs
        if (base / slug).exists() and any((base / slug).iterdir())
    }
```

#### Change 2d — Add `_doc_category_to_slug` static method

Add this static method anywhere in the class:

```python
@staticmethod
def _doc_category_to_slug(document_category) -> str:
    """
    Convert a DocumentCategory enum instance or its string value
    to the filesystem slug used as the FAISS subdirectory name.

    DocumentCategory.GEM_MANUAL        -> "gem_manual"
    DocumentCategory.USER_MANUALS      -> "user_manuals"
    DocumentCategory.TROUBLESHOOTING_GUIDANCE -> "troubleshooting_guidance"
    DocumentCategory.VARIABLE_FILES    -> "variable_files"
    DocumentCategory.SML_SCRIPTS       -> "sml_scripts"
    """
    val = document_category.value if hasattr(document_category, "value") else str(document_category)
    return val.strip().lower().replace(" ", "_").replace("/", "_")
```

#### Change 2e — Update `_ensure_project_dirs`

The existing `_ensure_project_dirs` creates subdirectories. Add `Vectorstore` itself but NOT the category subdirs — those are created on demand by `VectorStoreManager.add_document` (which calls `vector_dir.mkdir(parents=True, exist_ok=True)` already).

No change needed here — `VectorStoreManager` handles its own directory creation.

---

### FILE 3: `source/services/document_service.py`

**What to change:** In `analyze_document`, replace the single `vectorstore_path` call with a category-aware path.

#### Change 3a — Replace vectorstore indexing call

**Find this block inside `analyze_document`:**
```python
            if doc_text:
                vector_store = VectorStoreManager(self.storage.vectorstore_path(project_id))
                vector_store.add_document(
                    doc_text,
                    metadata={
                        "project_id": project_id,
                        "document_id": document_id,
                        "tool_id": spec.ToolID,
                    },
                )
```

**Replace with:**
```python
            if doc_text:
                category_slug = self.storage._doc_category_to_slug(document.DocumentType)
                category_store_path = self.storage.vectorstore_path_for_category(
                    project_id, category_slug
                )
                vector_store = VectorStoreManager(category_store_path)
                vector_store.add_document(
                    doc_text,
                    metadata={
                        "project_id": project_id,
                        "document_id": document_id,
                        "document_category": category_slug,
                        "tool_id": spec.ToolID,
                    },
                )
```

Note: `document` is already available in this method (fetched earlier as `document = self.storage.get_document(project_id, document_id)`).

No other changes to this file.

---

### FILE 4: `source/services/equipment_extractor.py`

**What to change:** After saving CSVs in `_extract_and_save_tables`, also index each table's rows into the `tables/` vector store.

#### Change 4a — Add `tables_store_path` parameter to `extract()`

**Find the current `extract` signature:**
```python
def extract(self, pdf_text: str, pdf_path: Union[str, Path, None] = None, tables_dir: Union[str, Path, None] = None) -> EquipmentSpec:
```

**Replace with:**
```python
def extract(self, pdf_text: str, pdf_path: Union[str, Path, None] = None, tables_dir: Union[str, Path, None] = None, tables_store_path: Union[str, Path, None] = None) -> EquipmentSpec:
```

#### Change 4b — Pass `tables_store_path` into `_extract_and_save_tables`

**Find this line inside `extract()`:**
```python
            section_csvs = self._extract_and_save_tables(Path(pdf_path), Path(tables_dir) if tables_dir else None)
```

**Replace with:**
```python
            section_csvs = self._extract_and_save_tables(
                Path(pdf_path),
                Path(tables_dir) if tables_dir else None,
                Path(tables_store_path) if tables_store_path else None,
            )
```

#### Change 4c — Update `_extract_and_save_tables` signature and add indexing logic

**Find the current method signature:**
```python
    def _extract_and_save_tables(
        self, pdf_path: Path, tables_dir: Union[Path, None]
    ) -> dict[str, str]:
```

**Replace with:**
```python
    def _extract_and_save_tables(
        self,
        pdf_path: Path,
        tables_dir: Union[Path, None],
        tables_store_path: Union[Path, None] = None,
    ) -> dict[str, str]:
```

Then find the end of `_extract_and_save_tables`, just before the final `return section_csvs` line. Insert this block:

```python
        # ── Index table rows into the dedicated 'tables' vector store ──────────
        # Each row from each classified table is embedded as a short sentence so
        # it can be retrieved by semantic search in ask_project.
        if tables_store_path is not None and section_rows:
            try:
                from source.utils.embedder import VectorStoreManager
                tables_vs = VectorStoreManager(tables_store_path)
                for section, rows in section_rows.items():
                    if len(rows) < 2:
                        continue
                    headers = rows[0]
                    for row_idx, row in enumerate(rows[1:], start=1):
                        # Build a natural-language sentence from the row
                        parts = []
                        for header, cell in zip(headers, row):
                            if cell:
                                parts.append(f"{header}: {cell}")
                        if not parts:
                            continue
                        sentence = f"[{section}] " + " | ".join(parts)
                        tables_vs.add_document(
                            sentence,
                            metadata={
                                "project_id": str(pdf_path.parent.parent.name),  # best effort
                                "document_id": pdf_path.stem,
                                "document_category": "tables",
                                "section": section,
                                "row_index": row_idx,
                            },
                        )
                logger.info(
                    "Indexed table rows from %s into tables vector store at %s",
                    pdf_path.name, tables_store_path,
                )
            except Exception as exc:
                logger.warning(
                    "Table vector store indexing failed for %s (non-fatal): %s",
                    pdf_path.name, exc,
                )

        return section_csvs
```

#### Change 4d — Update the call site in `document_service.py` to pass `tables_store_path`

This is in `document_service.py` inside the `PdfProcessingStrategy.analyze` method (or wherever `container.extractor.extract(...)` is called for PDFs).

**Find:**
```python
            tables_dir = self.storage.extracted_tables_path(project_id)
            spec = container.extractor.extract(text, pdf_path=pdf_path, tables_dir=tables_dir)
```

**Replace with:**
```python
            tables_dir = self.storage.extracted_tables_path(project_id)
            tables_store_path = self.storage.vectorstore_path_for_category(project_id, "tables")
            spec = container.extractor.extract(
                text,
                pdf_path=pdf_path,
                tables_dir=tables_dir,
                tables_store_path=tables_store_path,
            )
```

> Note: This call site is inside `document_strategies.py` inside `PdfProcessingStrategy.analyze()`, not directly in `document_service.py`. Find it by searching for `container.extractor.extract(` in the codebase. It may also appear in `analyze_project` in `equipment_routes.py`. Apply the same replacement everywhere `container.extractor.extract(` is called with a `tables_dir` argument.

---

### FILE 5: `source/routers/equipment_routes.py`

**What to change:** `delete_document` currently removes from one global vectorstore. It must now remove from all category stores.

#### Change 5a — Update `delete_document`

**Find:**
```python
    def delete_document(self, project_id: int, document_id: str):
        try:
            self.storage.delete_document(project_id, document_id)
            from source.utils.embedder import VectorStoreManager
            vector_store = VectorStoreManager(self.storage.vectorstore_path(project_id))
            vector_store.remove_document(document_id)
        except InvalidSlugError as exc:
            raise HTTPException(400, str(exc)) from exc
        except (ProjectNotFoundError, DocumentNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc
        return {"Status": "success", "Message": f"Document {document_id} deleted"}
```

**Replace with:**
```python
    def delete_document(self, project_id: int, document_id: str):
        try:
            self.storage.delete_document(project_id, document_id)
            from source.utils.embedder import VectorStoreManager
            # Remove the document's chunks from every category store that exists
            all_store_paths = self.storage.all_vectorstore_paths(project_id)
            for slug, store_path in all_store_paths.items():
                try:
                    vs = VectorStoreManager(store_path)
                    removed = vs.remove_document(document_id)
                    if removed:
                        logger.info(
                            "Removed %d chunks for document %s from %s store",
                            removed, document_id, slug,
                        )
                except Exception as exc:
                    logger.warning(
                        "Could not clean up vector store '%s' for document %s: %s",
                        slug, document_id, exc,
                    )
        except InvalidSlugError as exc:
            raise HTTPException(400, str(exc)) from exc
        except (ProjectNotFoundError, DocumentNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc
        return {"Status": "success", "Message": f"Document {document_id} deleted"}
```

---

### FILE 6: `source/routers/project_routes.py`

**What to change:** `ask_project` currently searches one global vectorstore. It must now:
- Search the specific category store if `DocumentCategory` is given in the request
- Search ALL category stores and merge results if `DocumentCategory` is `None` or `"all"`
- Search only the `tables/` store if `DocumentCategory == "tables"`

#### Change 6a — Replace `ask_project` method entirely

**Find:**
```python
    def ask_project(self, project_id: int, request: AskRequest):
        try:
            self.storage.get_project(project_id)
            vector_store = VectorStoreManager(self.storage.vectorstore_path(project_id))
            chunks = vector_store.search_with_filters(
                request.Question, {"project_id": project_id}, k=1
            )
            if not chunks:
                raise HTTPException(404, "No indexed content in this project yet")

            document_id = chunks[0].metadata.get("document_id")
            if not document_id:
                raise HTTPException(500, "Indexed chunk is missing document_id metadata")

            spec_json = self.storage.read_spec_json(project_id, document_id)
            spec = EquipmentSpec.model_validate_json(spec_json)
            qa_service = container.create_qa_service(
                vector_store,
                vector_filters={"project_id": project_id, "document_id": document_id},
            )
            answer_text, source = qa_service.answer(request.Question, spec)
        except InvalidSlugError as exc:
            raise HTTPException(400, str(exc)) from exc
        except (ProjectNotFoundError, DocumentNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc

        return {
            "ProjectID": project_id,
            "DocumentID": document_id,
            "Category": request.Category,
            "Answer": answer_text,
            "Source": source,
        }
```

**Replace with:**
```python
    def ask_project(self, project_id: int, request: AskRequest):
        try:
            self.storage.get_project(project_id)

            # ── Determine which vector store(s) to search ─────────────────────
            requested_category = (request.DocumentCategory or "").strip().lower()

            if requested_category in ("", "all"):
                # Search every category store that exists and merge results
                all_paths = self.storage.all_vectorstore_paths(project_id)
                if not all_paths:
                    raise HTTPException(404, "No indexed content in this project yet")

                all_chunks = []
                for slug, store_path in all_paths.items():
                    try:
                        vs = VectorStoreManager(store_path)
                        hits = vs.search_with_filters(
                            request.Question, {"project_id": project_id}, k=4
                        )
                        all_chunks.extend(hits)
                    except Exception as exc:
                        logger.warning("Search failed for store '%s': %s", slug, exc)

                if not all_chunks:
                    raise HTTPException(404, "No indexed content in this project yet")

                # Sort by FAISS similarity score if available, else keep order
                # Deduplicate by (document_id, chunk_id) to avoid double answers
                seen = set()
                unique_chunks = []
                for chunk in all_chunks:
                    key = (
                        chunk.metadata.get("document_id"),
                        chunk.metadata.get("chunk_id"),
                    )
                    if key not in seen:
                        seen.add(key)
                        unique_chunks.append(chunk)

                chunks = unique_chunks[:6]

            else:
                # Specific category requested — map the string to a slug
                # Accept either the enum value string ("GEM Manual") or the slug ("gem_manual")
                # or the special value "tables"
                if requested_category == "tables":
                    slug = "tables"
                else:
                    # Normalise: lowercase + spaces to underscores
                    slug = requested_category.replace(" ", "_").replace("/", "_")

                store_path = self.storage.vectorstore_path_for_category(project_id, slug)
                if not store_path.exists():
                    raise HTTPException(
                        404,
                        f"No indexed content for document category '{request.DocumentCategory}' in this project. "
                        f"Upload and analyze a document of that type first.",
                    )

                vs = VectorStoreManager(store_path)
                chunks = vs.search_with_filters(
                    request.Question, {"project_id": project_id}, k=6
                )
                if not chunks:
                    raise HTTPException(
                        404,
                        f"No results found in the '{request.DocumentCategory}' store for this question.",
                    )

            # ── Pick the best document and answer ─────────────────────────────
            document_id = chunks[0].metadata.get("document_id")
            if not document_id:
                raise HTTPException(500, "Indexed chunk is missing document_id metadata")

            # For the tables store, document_id is the PDF stem (set during indexing).
            # Try to load its spec; if missing, answer from chunk content alone.
            try:
                spec_json = self.storage.read_spec_json(project_id, document_id)
                spec = EquipmentSpec.model_validate_json(spec_json)
            except Exception:
                # Fallback: build a minimal empty spec so QAService still works
                spec = EquipmentSpec(ToolID="", ToolType="")

            # Use the store from which the winning chunk came
            winning_category = chunks[0].metadata.get("document_category", "")
            if winning_category:
                winning_store_path = self.storage.vectorstore_path_for_category(
                    project_id, winning_category
                )
            else:
                # Legacy chunk without document_category metadata — fall back to the first hit's store
                winning_store_path = self.storage.vectorstore_path_for_category(
                    project_id,
                    requested_category if requested_category not in ("", "all") else "gem_manual",
                )

            qa_store = VectorStoreManager(winning_store_path)
            qa_service = container.create_qa_service(
                qa_store,
                vector_filters={"project_id": project_id, "document_id": document_id},
            )
            answer_text, source = qa_service.answer(request.Question, spec)

        except HTTPException:
            raise
        except InvalidSlugError as exc:
            raise HTTPException(400, str(exc)) from exc
        except (ProjectNotFoundError, DocumentNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc

        return {
            "ProjectID": project_id,
            "DocumentID": document_id,
            "Category": request.Category,
            "DocumentCategory": chunks[0].metadata.get("document_category", ""),
            "Answer": answer_text,
            "Source": source,
        }
```

---

## On-disk directory structure after these changes

```
EAP_STORAGE_ROOT/
  <project_id>/
    Documents/
    ExtractedJson/
    ExtractedTables/
    Vectorstore/
      gem_manual/           ← FAISS index for GEM Manual PDFs
        index.faiss
        index.pkl
      user_manuals/         ← FAISS index for User Manual PDFs
        index.faiss
        index.pkl
      troubleshooting_guidance/
        index.faiss
        index.pkl
      variable_files/
        index.faiss
        index.pkl
      sml_scripts/
        index.faiss
        index.pkl
      tables/               ← FAISS index for extracted table rows
        index.faiss
        index.pkl
    Metadata/
    ToolCharacterisation/
```

Each subdirectory is only created when the first document of that type is analyzed.

---

## Migration note for existing projects

Existing projects have a flat `Vectorstore/` directory (no subdirectories). They will still work because:
- `all_vectorstore_paths` only returns paths that exist AND are non-empty — a flat legacy store is not in its result set because the slugs don't match any of its expected subfolder names
- `ask_project` with no `DocumentCategory` will call `all_vectorstore_paths` which will return nothing for legacy projects and raise 404 — **this is a breaking change for existing data**

**To handle legacy projects without re-analyzing all documents**, add this extra path at the top of `all_vectorstore_paths`:

```python
# Legacy compatibility: if the project has a flat (pre-category) vectorstore, include it
legacy_path = self._project_dir(project_id) / self.VECTORSTORE_DIR
if legacy_path.exists() and (legacy_path / "index.faiss").exists():
    result["legacy"] = legacy_path
```

Then in `ask_project`, treat `"legacy"` as a valid category slug for searching.

---

## Summary of every changed symbol

| File | Symbol | Change |
|---|---|---|
| `schemas/project.py` | `AskRequest` | Add `DocumentCategory: Optional[str] = None` |
| `storage_service.py` | `vectorstore_path_for_category()` | New method |
| `storage_service.py` | `all_vectorstore_paths()` | New method |
| `storage_service.py` | `_doc_category_to_slug()` | New static method |
| `document_service.py` | `analyze_document()` | Use category-specific store path |
| `equipment_extractor.py` | `extract()` | Add `tables_store_path` param |
| `equipment_extractor.py` | `_extract_and_save_tables()` | Add `tables_store_path` param + indexing loop |
| `document_strategies.py` | `PdfProcessingStrategy.analyze()` | Pass `tables_store_path` to `extractor.extract()` |
| `equipment_routes.py` | `delete_document()` | Remove from all category stores |
| `project_routes.py` | `ask_project()` | Search specific or all category stores |

---

## What does NOT change

- `VectorStoreManager` class — zero changes. It already works per-directory.
- `add_document`, `remove_document`, `search_with_filters` — zero changes.
- FAISS index format — identical.
- All other endpoints — zero changes.
- `AskRequest.Category` field — still present, still works exactly as before.
