# EAP SECS/GEM Backend Architecture

## Summary

This backend extracts SECS/GEM equipment specs from uploaded semiconductor
equipment PDF manuals. The active extraction pipeline is filesystem-backed:
the code repository contains application code only, while project data is kept
under a configurable external storage root.

Configure storage with:

```env
EAP_STORAGE_ROOT=/var/lib/eap/storage
```

For local development only, the fallback is:

```env
EAP_STORAGE_ROOT=./runtime_storage
```

Use an absolute path on the Azure VM so service startup location does not
change where data is written.

## Runtime Storage Layout

Each project is stored as a self-contained folder:

```text
<EAP_STORAGE_ROOT>/
  <project_slug>/
    Documents/
      <document_slug>.pdf
    ExtractedJson/
      <document_slug>.json
    Vectorstore/
      index.faiss
      index.pkl
    Metadata/
      project.json
```

`Metadata/project.json` is the source of truth for project listing, document
listing, and extracted JSON lookup. SQLite is not used by the extraction
pipeline.

## Upload Flow

```text
POST /projects/{project_slug}/equipment/upload
  -> validate PDF and size
  -> save original PDF to Documents/
  -> extract text from saved PDF
  -> extract EquipmentSpec with the configured LLM
  -> validate internally
  -> save only ExtractedJson/<document_slug>.json
  -> chunk and embed text into that project's Vectorstore/
  -> update Metadata/project.json
```

Validation reports are returned by the upload response for visibility, but
`report.json` is intentionally not written in this phase.

## Active API

```http
GET /health
```

Returns backend health.

```http
POST /projects
```

Creates the project folder and metadata file.

Request:

```json
{"name": "Frontend Etch Module"}
```

```http
GET /projects
```

Scans `EAP_STORAGE_ROOT` and returns project summaries.

```http
GET /projects/{project_slug}
```

Returns `Metadata/project.json`.

```http
POST /projects/{project_slug}/equipment/upload
```

Uploads and extracts one PDF into the selected project.

```http
GET /projects/{project_slug}/equipment/{document_id}/json
```

Downloads the extracted equipment spec JSON.

```http
POST /projects/{project_slug}/equipment/{document_id}/ask
```

Answers a question using structured JSON lookup first, then that project's
FAISS vectorstore filtered to the selected document.

## Important Code Paths

- `app/config.py`: environment settings, including `EAP_STORAGE_ROOT`.
- `app/services/storage_service.py`: filesystem layout, safe slugs, metadata,
  PDF/spec writes, and path validation.
- `app/routers/project_routes.py`: filesystem-backed project APIs.
- `app/routers/equipment_routes.py`: filesystem-backed upload and JSON download.
- `app/utils/embedder.py`: FAISS persistence for one project-local vectorstore.
- `app/services/equipment_extractor.py`: LLM extraction into `EquipmentSpec`.
- `app/validators/spec_validator.py`: internal deterministic validation.

## Notes

- `index.pkl` is LangChain docstore and metadata state, not embedding model
  weights. It is expected next to every project-level `index.faiss`.
- Mapping schemas and suggestion service code are retained as a framework for
  the future filesystem-backed mapping refactor. The old SQLite-backed mapping
  persistence, repositories, and ORM models have been removed.
- Legacy demo data previously kept under `eap_bot/app.db`, `eap_bot/projects/`,
  and `eap_bot/vectorstores/` has been removed from the active code package.
