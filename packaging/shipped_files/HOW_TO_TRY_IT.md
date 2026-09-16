# HiCore EAP as a command-line program — how to try it

This is the equipment automation backend as a program that runs on your own PC. It does
everything the hosted service at `151.185.41.194:8012` does — projects, documents, extraction,
mapping, scripts, reports — with no server and no network port.

Every endpoint lives in **one file, `eap_bot\eap_cli.py`**: one function per endpoint, and a
table at the top mapping each method and path to its function. That file calls the backend's
existing code rather than repeating it, so it stays correct when the backend changes.

**Nothing to install.** Python and every library are inside this folder. Unzip it anywhere and run.

Requirements: 64-bit Windows. About 500 MB of disk. Internet is only needed for the AI features.

**It comes with real projects.** The `data` folder holds the four projects that were on the
hosted service on 15 September 2026, copied as they were — documents, extractions and search
indexes included:

| ID | Project | Tool | Documents | Status variables | Data variables | Events | Alarms | Remote commands |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | KLA | CVD | 1 | 0 | 0 | 0 | 0 | 0 |
| 2 | String | ETCH | 2 | 34 | 44 | 56 | 21 | 6 |
| 3 | Hicore | CVD | 3 | 27 | 33 | 42 | 6 | 16 |
| 4 | Str1 | LITHO | 2 | 34 | 44 | 56 | 21 | 6 |

The summary endpoint `GetProjectDetails` reports different figures for the same projects
(Hicore: 41 status variables, 41 data variables, 22 remote commands). The hosted service gives
exactly those figures too, so that is how the two endpoints count, not something lost in copying.

---

## 1. The quickest look

Double-click **`demo.cmd`**.

It starts the backend, sends several requests, prints each answer with how long it took, then
stops it. It creates a demo project and deletes it again, so the four included projects are
left as they were. You should see something like:

```text
backend ready in 4.9s

  is it alive                  200   0.00s  {'status': 'ok'}
  system summary               200   0.01s  {'TotalProjects': 4, ...}
  list all projects            200   0.01s  {'ProjectInfo': [{'ProjectID': 1, ...
  open Hicore                  200   0.25s  {'ProjectID': 3, 'ProjectName': 'Hicore', ...
  create a project             201   0.03s  {'ProjectID': 5, 'ProjectName': 'Demo ...
  upload a manual (PDF)        200   1.41s  {'Status': 'uploaded', 'DocumentID': ...
  a project that is missing    404   0.01s  {'detail': "Project '99999' was not found"}
  delete the project           200   0.02s  {'Status': 'deleted', ...}
```

The first line matters: the backend takes about **5 seconds to start**, and after that each
request takes **hundredths of a second**. That is why an application starts it once and keeps
it open, rather than starting it for every click.

The very first run after unzipping takes longer — around 10 seconds — because Windows checks
each of the newly written files the first time it reads them. Later runs settle to about 5
seconds. Nothing is wrong if the first one feels slow.

## 2. Sending single requests yourself

Open PowerShell in this folder (in File Explorer: right-click an empty spot → **Open in
Terminal**) and use **`eap_cli.cmd`**. PowerShell needs `.\` in front of it; in Command Prompt
it works with or without.

```text
.\eap_cli.cmd GET /GetSystemSummary
.\eap_cli.cmd GET /GetAllProjects
.\eap_cli.cmd GET /LoadProject/3
.\eap_cli.cmd GET /GetProjectDetails/3
.\eap_cli.cmd --list
```

`--list` prints all 37 endpoints. `LoadProject/3` returns the Hicore project with its full
extraction from its three documents.

Each prints the answer as JSON, and sets an exit code — 0 worked, 1 the backend answered with
an error, 2 the command itself was wrong:

```json
{
  "status": 200,
  "body": { "ProjectInfo": [ ... ] }
}
```

This starts a fresh copy for each command, so every one costs those 5 seconds of startup. It
is meant for looking around; section 5 is what an application does instead.

### Sending a body (POST and PUT)

**Easiest, and the same in every shell: put the body in a file** and pass it with `@`. Two are
ready in `sample\`:

```text
.\eap_cli.cmd POST /CreateProject @sample\create_project.json
```

Open `sample\create_project.json` in Notepad to change the name or code.

**Typing the JSON directly** works too, but each shell treats quotes differently:

| Shell | Example |
| --- | --- |
| PowerShell — single quotes around the body | `.\eap_cli.cmd POST /CreateProject '{\"ProjectName\": \"Demo\", \"VendorName\": \"HiCore\", \"ProjectCode\": \"D-1\"}'` |
| Command Prompt — double quotes | `eap_cli.cmd POST /CreateProject "{\"ProjectName\": \"Demo\", \"VendorName\": \"HiCore\", \"ProjectCode\": \"D-1\"}"` |

In PowerShell, double quotes around the body do not work: PowerShell rewrites the inner quotes
before the backend sees them. If you get "the request body is not valid JSON", that is what
happened — use a file or single quotes.

### Uploading a file

```text
.\eap_cli.cmd POST /UploadDocument/3 --form "document_type=GEM Manual" --file "file=sample\ETCH_Z500_GEM_Spec_Demo.pdf"
```

Only the answer is shown. The backend's own log lines — startup steps, and notices from the
libraries it loads — go to `data\logs\console.log`. To see them on screen as well, run
`$env:EAP_VERBOSE=1` in PowerShell (or `set EAP_VERBOSE=1` in Command Prompt) first.

## 3. Turning on the AI features

Analysis, questions and auto-mapping call Groq. Without a key everything else still works and
those requests return an error.

Open `eap_cli.cmd` or `demo.cmd` in Notepad and fill in the line:

```text
set GROQ_API_KEY=your-key-here
```

Then, for example:

```text
.\eap_cli.cmd POST /Ask/3 @sample\ask_question.json
.\eap_cli.cmd GET /GetQuestions/3
```

The first asks a question about the Hicore project's documents and returns the answer with the
passages it was drawn from; edit `sample\ask_question.json` to ask something else.

Note: the free Groq tier allows 8,000 tokens per minute, and analysing a manual sends far more
than that, so analysis can be slow or fail until the account moves to a paid tier.

## 4. Where things are kept

| What | Where |
| --- | --- |
| Projects, documents, extractions, reports | `data\projects` in this folder |
| Logs | `data\logs\backend.log`, plus `data\logs\console.log` for what is kept off the screen |
| The program itself | `runtime` and `eap_bot` — nothing is written into them |

The `.cmd` files point the backend at `data` so the included projects show up. Anything you
create or change lands there too; unzip again for a fresh copy.

**An installed application works differently:** it keeps data in
`%LOCALAPPDATA%\HiCore\BraceLink` and passes that location when it starts the backend. The
folder contains no API key and no settings file; the application passes those in too.

## 5. How BraceLink will use it

The same file, started once and kept open:

```text
runtime\eap_cli.exe -E eap_bot\eap_cli.py --serve
```

It reports `{"type": "ready", "version": "1.0"}` when it can take requests. Then one line of
JSON per request, one line per answer:

```text
BraceLink -> {"id": "42", "method": "GET", "path": "/LoadProject/12"}
backend   -> {"id": "42", "status": 200, "body": {"ProjectID": 12, ...}}
```

Eight requests can be in flight at once, so a long analysis does not block the rest of the app.
Answers can come back in a different order, so match them by `id`. Closing the backend's input
stops it; it also stops by itself if BraceLink closes or crashes.

`demo.py` in this folder is a working example of that conversation in about 60 lines of code.

## 6. All 37 endpoints

The paths and answers are identical to the hosted service, so nothing else in BraceLink changes.
Run `.\eap_cli.cmd --list` to see this list from the program itself.

**Projects:** `/CreateProject`, `/GetAllProjects`, `/LoadProject/{id}`, `/UpdateProject/{id}`,
`/DeleteProject/{id}`, `/ReAnalyzeProject/{id}`, `/GetProjectDetails/{id}`, `/GetSystemSummary`,
`/GetKnowledgeCategory/{id}`, `/Ask/{id}`

**Documents:** `/UploadDocument/{id}`, `/Analyze/{id}/{doc}`, `/Analyze/{id}/{doc}/report`,
`/AnalyzeProject/{id}`, `/GetVariable/{id}/{doc}`, `/DeleteDocument/{id}/{doc}`,
`/UpdateExtraction/{id}`, `/GenerateReports/{id}`, `/UpdateReports/{id}`, `/GetQuestions/{id}`

**Mapping:** `/UpdateMapping/{id}`, `/AutoMap?project_id={id}`

**MES:** `/GetMesFamilies`, `/UpdateMesFamilies`, `/GetMesTemplates/{family}`,
`/GetMesTemplateInfo/{family}/{template}`, `/AddMesTemplateInfo/{family}`,
`/UpdateMesTemplateInfo/{family}/{template}`

**Scripts and results:** `/GenerateTestScripts/{id}`, `/UpdateToolCharacterizationScript/{id}`,
`/GenerateSMLScripts/{id}`, `/UploadTestResult`, `/GetToolResults/{id}?tool_id={tool}`

**Smart automation:** `/GenerateSmartAutomationCode/{id}`, `/UpdateSmartAutomationCode/{id}`,
`/GenerateOverallReport/{id}`

**Service check:** `/health`

## 7. If something does not work

| What you see | What it means |
| --- | --- |
| Double-clicking `eap_cli.cmd` only shows a message | That is expected: it needs a method and a path after it. Double-click `demo.cmd` for a tour that runs by itself, or open a terminal here and type `.\eap_cli.cmd GET /GetAllProjects` |
| `'eap_cli.cmd' is not recognized` | Type `.\eap_cli.cmd` instead. PowerShell always needs the `.\`, and some locked-down PCs require it in Command Prompt too |
| `the request body is not valid JSON` | The shell changed the quotes. Pass the body as a file (`@sample\create_project.json`), or in PowerShell use single quotes around it |
| `the backend could not start` | Check `data\logs\backend.log` |
| Requests about AI fail | No `GROQ_API_KEY` set, or the free tier's rate limit was reached |
| Antivirus blocks it | The folder contains a Python runtime; it may need to be allowed on locked-down machines |
