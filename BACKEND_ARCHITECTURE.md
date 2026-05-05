# EAP SECS/GEM Backend Architecture Overview

## Summary

This project is a backend-only proof of concept for extracting SECS/GEM integration data from semiconductor equipment PDF manuals.

The original bot scaffolding has been repurposed into `eap_bot`, a FastAPI service that can:

- Accept semiconductor equipment PDFs through an upload API.
- Extract structured SECS/GEM data using Groq Llama.
- Validate the extracted data with Pydantic and custom cross-reference checks.
- Persist extracted specs in SQLite.
- Index PDF text into FAISS using local HuggingFace embeddings.
- Answer questions using either structured JSON lookup or RAG over indexed PDF chunks.
- Return/download integration-ready JSON for each uploaded equipment document.

The Streamlit UI is intentionally not included yet. This package is the backend implementation.

## What Was Built

The backend converts equipment PDFs such as CVD, Plasma Etch, and Photolithography manuals into a structured `EquipmentSpec` JSON object.

The extracted JSON includes:

- Tool identity: `tool_id`, `tool_type`, `model`, protocol, connection details.
- Variables: status variables and data variables with VIDs, units, access, descriptions, and confidence.
- Collection events: CEIDs, names, linked VIDs, descriptions, and report flags.
- Alarms: alarm IDs, severity, linked variables, and descriptions.
- Remote commands: RCMD names, descriptions, and parameters.
- Equipment states: state IDs, names, and descriptions.
- State transitions: source state, target state, trigger event, trigger command, or manual transition.
- Validation report: duplicate IDs, unresolved links, missing sections, invalid transitions, and warnings.

## High-Level Flow

```text
PDF upload
  -> save uploaded PDF to uploads/
  -> extract raw text with pypdf
  -> send text to Groq Llama structured-output prompt
  -> parse JSON response
  -> validate against Pydantic EquipmentSpec schema
  -> run custom validator for cross-reference issues
  -> save spec, raw text, and validation report to SQLite
  -> split raw text into chunks
  -> embed chunks with HuggingFace MiniLM
  -> save/search chunks in FAISS
  -> return spec JSON and validation report from API
```

For Q&A:

```text
Question
  -> first try deterministic JSON lookup for known spec questions
  -> if no JSON pattern matches, search FAISS chunks for that specific tool
  -> send retrieved context to Groq
  -> return answer with source = json or rag
```

## Main Directory Structure

```text
eap_bot/
  app/
    main.py
    config.py
    db.py
    crud.py
    schemas/
      secsgem.py
    extractors/
      equipment_extractor.py
    validators/
      spec_validator.py
    routers/
      equipment_routes.py
    services/
      qa_service.py
    utils/
      pdf_reader.py
      embedder.py
    models/
      models.py
  requirements.txt
  .env.example
```

## Important Files

### `app/main.py`

Creates the FastAPI app, initializes database tables, registers the equipment router, and exposes `/health`.

### `app/config.py`

Loads configuration from `.env`.

Important settings:

- `GROQ_API_KEY`
- `GROQ_MODEL`
- `DATABASE_URL`
- `UPLOAD_DIR`
- `VECTORSTORE_ROOT`
- `CHUNK_SIZE`
- `CHUNK_OVERLAP`
- `MAX_UPLOAD_SIZE`

### `app/schemas/secsgem.py`

Defines the Pydantic v2 schema for the extracted SECS/GEM output.

The main model is `EquipmentSpec`. It contains variables, events, alarms, remote commands, states, transitions, and connection metadata.

It also defines `ValidationIssue` and `ValidationReport`.

### `app/extractors/equipment_extractor.py`

Handles the LLM extraction step.

It builds a strict prompt containing the `EquipmentSpec` JSON schema, sends the PDF text to Groq Llama in JSON mode, parses the response, sanitizes invalid transitions, and validates the result into an `EquipmentSpec`.

### `app/validators/spec_validator.py`

Runs deterministic validation after LLM extraction.

Checks include:

- Duplicate IDs.
- Event linked VIDs that do not exist.
- Alarm linked VIDs that do not exist.
- State transitions referencing missing states.
- Transition triggers referencing missing events or commands.
- Variable unit inconsistencies.
- Missing critical sections such as variables or events.

### `app/models/models.py`

Defines the SQLite table model:

```text
equipment_specs
```

Each row stores:

- Internal ID.
- Tool ID.
- Tool type.
- Source filename.
- Raw extracted PDF text.
- Extracted JSON.
- Validation JSON.
- Created timestamp.

### `app/crud.py`

Contains database helper functions:

- `save_spec`
- `get_spec`
- `list_specs`

### `app/routers/equipment_routes.py`

Defines all equipment API endpoints:

- `POST /equipment/upload`
- `GET /equipment`
- `GET /equipment/{spec_id}`
- `GET /equipment/{spec_id}/json`
- `POST /equipment/{spec_id}/ask`

This file orchestrates upload, extraction, validation, persistence, FAISS indexing, JSON download, and Q&A.

### `app/services/qa_service.py`

Implements the Q&A behavior.

It first tries to answer common questions directly from the extracted JSON, such as:

- Which variables are linked to an event?
- What state follows a given state?
- List events.
- List variables.
- List alarms.
- List commands.
- List critical/warning/info alarms.

If the question does not match a known JSON pattern, it falls back to RAG using FAISS chunks filtered by `tool_id`.

### `app/utils/embedder.py`

Handles text normalization, chunking, HuggingFace embeddings, FAISS persistence, and filtered vector search.

Embeddings use:

```text
sentence-transformers/all-MiniLM-L6-v2
```

This runs locally on CPU and produces 384-dimensional vectors.

### `app/utils/pdf_reader.py`

Extracts text from uploaded PDFs using `pypdf`.

## API Reference

### Health Check

```http
GET /health
```

Expected response:

```json
{"status":"ok"}
```

### Upload Equipment PDF

```http
POST /equipment/upload
```

Multipart form field:

```text
file=<PDF file>
```

Returns:

- Internal spec ID.
- Extracted `EquipmentSpec`.
- Validation report.

### List Uploaded Specs

```http
GET /equipment
```

Returns summary rows for all saved equipment specs.

### Get One Spec

```http
GET /equipment/{spec_id}
```

Returns the extracted spec and validation report for one saved document.

### Download Spec JSON

```http
GET /equipment/{spec_id}/json
```

Returns the raw extracted JSON as an `application/json` download.

### Ask a Question

```http
POST /equipment/{spec_id}/ask
```

Request body:

```json
{
  "query": "Which variables are linked to ProcessStart?"
}
```

Response:

```json
{
  "answer": "...",
  "source": "json"
}
```

The `source` value is:

- `json` when the answer came directly from structured extracted data.
- `rag` when the answer came from FAISS retrieval and Groq context answering.

## Runtime-Generated Files

These files and folders do not need to be sent in the source package. They are created at runtime:

```text
eap_bot/app.db
eap_bot/uploads/
eap_bot/vectorstores/
eap_bot/vectorstores/index.faiss
eap_bot/vectorstores/index.pkl
```

Do not send:

```text
eap_bot/.venv/
eap_bot/.env
eap_bot/app.db
eap_bot/uploads/
eap_bot/vectorstores/
```

The `.env` file contains the real Groq API key and should be shared separately if needed.

## Setup Instructions

From inside the package:

```powershell
cd eap_bot

python -m venv .venv
.venv\Scripts\activate

pip install -r requirements.txt

copy .env.example .env
```

Then edit `.env` and set:

```env
GROQ_API_KEY=<shared Groq API key>
```

Start the server:

```powershell
uvicorn app.main:app --reload --port 8000
```

The backend should now be available at:

```text
http://localhost:8000
```

## Testing Instructions

Health check:

```powershell
curl http://localhost:8000/health
```

Upload CVD sample PDF:

```powershell
curl -F "file=@../Sample Documents/Chemical Vapor Deposition.pdf" http://localhost:8000/equipment/upload
```

List uploaded specs:

```powershell
curl http://localhost:8000/equipment
```

Ask a JSON-backed question:

```powershell
curl -X POST http://localhost:8000/equipment/1/ask `
  -H "Content-Type: application/json" `
  -d "{\"query\":\"Which variables are linked to ProcessStart?\"}"
```

Ask a RAG-backed question:

```powershell
curl -X POST http://localhost:8000/equipment/1/ask `
  -H "Content-Type: application/json" `
  -d "{\"query\":\"What is plasma deposition?\"}"
```

Download extracted JSON:

```powershell
curl http://localhost:8000/equipment/1/json
```

## Sample Files for Demo

Recommended files to include with the backend package:

```text
Sample Documents/
  Chemical Vapor Deposition.pdf
  Plasma Etching System.pdf
  Photolithography System.pdf

Sample outputs/
  cvd_resp.json
  etch_resp.json
  litho_resp.json
```

The `Sample outputs` files are reference outputs from previous successful extraction runs. They are useful for quickly reviewing the expected shape of the extracted JSON.

## Expected Demo Behavior

For `Chemical Vapor Deposition.pdf`, upload should return an extracted CVD spec with:

- Variables such as `V1001 ChamberTemperature`, `V1002 ChamberPressure`, and `V2001 RecipeID`.
- Events such as `E101 ProcessStart` and `E102 ProcessEnd`.
- Alarms such as `A201 HighTemperature`.
- Remote commands such as `START`, `STOP`, `PAUSE`, and `RESUME`.
- States such as `Idle`, `Processing`, `Completed`, and `Error`.

Example question:

```text
Which variables are linked to ProcessStart?
```

Expected answer source:

```text
json
```

Expected answer should mention:

```text
V1001, V1002, V2001
```

## Notes and Known Caveats

- First run may take extra time because the HuggingFace embedding model is downloaded/loaded.
- The Groq API key is required for live extraction and RAG answers.
- LLM extraction can occasionally vary slightly between runs.
- Validation warnings are expected when the source document or LLM output has ambiguous links.
- The UI is not included yet; this is backend-only.
- The old syllabus/PYQ domain code is not part of the active backend flow.


