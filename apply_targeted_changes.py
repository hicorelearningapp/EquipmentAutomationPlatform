#!/usr/bin/env python3
"""
apply_targeted_changes.py
=========================
Applies four surgical changes to the EAP Bot codebase:

  1. GetAllProjects  — project list numbered starting from 1 (Index field)
  2. equipment_routes — remove GET /Analyze/{id}/{doc}/report (download report)
  3. equipment_routes — split GenerateReports (suggest-only, no save)
                        add    AddReports     (persist to project_batch.json)
  4. test_documents_endpoints — remove Group 4 download-report test functions

USAGE
-----
  Preview only (dry-run, nothing written):
      python apply_targeted_changes.py

  Apply for real:
      python apply_targeted_changes.py --apply

WHERE TO RUN
------------
  Place this file anywhere on your machine.
  Set CODEBASE_ROOT (below) to the absolute path of your eap_bot folder.
  Run from any terminal — no virtual environment needed, only stdlib.

CONFIGURE
---------
  Edit the CODEBASE_ROOT line to match your machine.
"""

import argparse
import re
import sys
from pathlib import Path

# ── SET THIS TO YOUR eap_bot DIRECTORY ───────────────────────────────────────
CODEBASE_ROOT = Path("E:/Github/EquipmentAutomationPlatforms/eap_bot")
# ─────────────────────────────────────────────────────────────────────────────

_OK   = "  [OK] "
_FAIL = "  [!!] "
_INFO = "  [--] "


# ─────────────────────────────────────────────────────────────────────────────
# New code blocks (defined as constants so the logic section stays readable)
# ─────────────────────────────────────────────────────────────────────────────

_NEW_GENERATE_REPORTS = '''\
    def generate_reports(self, project_id: int, request: GenerateReportsRequest = Body(default_factory=GenerateReportsRequest)):
        """Suggest reports for the given CEIDs.  Does NOT persist anything.

        Review the returned SuggestedReports, then call
        POST /AddReports/{project_id} to actually save the ones you want.
        """
        from source.schemas.secsgem import EquipmentSpec
        try:
            self.storage.get_project(project_id)  # raises 404 if project missing
            try:
                spec_json = self.storage.read_spec_json(project_id, "project_batch")
                spec_obj = EquipmentSpec.model_validate_json(spec_json)
            except Exception:
                _, spec_obj = container.project_service.aggregate_project_data(project_id)

            if request.ceids:
                target_events = [e for e in spec_obj.Events if e.CEID in request.ceids]
                original_events = spec_obj.Events
                spec_obj.Events = target_events
                new_reports = container.report_service.generate_synthetic_reports(spec_obj)
                spec_obj.Events = original_events
                # Show existing non-clashing reports alongside the new suggestions
                # so the caller sees the full picture before deciding what to add.
                new_rptids = {r.RPTID for r in new_reports}
                kept = [r for r in spec_obj.Reports if r.RPTID not in new_rptids]
                suggested = kept + new_reports
            else:
                suggested = container.report_service.generate_synthetic_reports(spec_obj)

            return {
                "ProjectID": project_id,
                "SuggestedReports": [r.model_dump() for r in suggested],
            }
        except (InvalidSlugError, ProjectNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc

    def add_reports(self, project_id: int, request: AddReportsRequest = Body(...)):
        """Persist approved reports to project_batch.json and re-link events.

        Call this after reviewing the suggestions from POST /GenerateReports/{project_id}.
        Incoming reports replace any existing reports with the same RPTID; all others
        are kept.  Event-to-report links are recomputed via greedy set cover.
        """
        from source.schemas.secsgem import EquipmentSpec
        try:
            self.storage.increment_project_version(project_id)
            json_path = self.storage.spec_json_path(project_id, "project_batch")
            try:
                spec_json = self.storage.read_spec_json(project_id, "project_batch")
                spec_obj = EquipmentSpec.model_validate_json(spec_json)
            except Exception:
                _, spec_obj = container.project_service.aggregate_project_data(project_id)

            # Merge: incoming reports replace those with matching RPTIDs, keep the rest
            incoming_rptids = {r.RPTID for r in request.reports}
            kept_reports = [r for r in spec_obj.Reports if r.RPTID not in incoming_rptids]
            spec_obj.Reports = kept_reports + request.reports

            # Re-link events → reports via greedy set cover on LinkedVIDs
            for event in spec_obj.Events:
                if not event.LinkedVIDs:
                    event.LinkedReports = []
                    continue

                uncovered: set = set(event.LinkedVIDs)
                chosen_rptids: set = set()

                while uncovered:
                    best_report = None
                    best_cover_count = 0
                    best_extra_count = float('inf')

                    for report in spec_obj.Reports:
                        if report.RPTID in chosen_rptids:
                            continue
                        rpt_vids = set(report.LinkedVIDs)
                        covered = uncovered.intersection(rpt_vids)
                        extra = rpt_vids - set(event.LinkedVIDs)
                        cover_count = len(covered)
                        extra_count = len(extra)
                        if cover_count > best_cover_count:
                            best_cover_count = cover_count
                            best_extra_count = extra_count
                            best_report = report
                        elif cover_count == best_cover_count and cover_count > 0:
                            if extra_count < best_extra_count:
                                best_extra_count = extra_count
                                best_report = report

                    if best_report is None:
                        break
                    chosen_rptids.add(best_report.RPTID)
                    uncovered -= set(best_report.LinkedVIDs)

                event.LinkedReports = sorted(list(chosen_rptids))

            self.storage.save_spec_json(json_path, spec_obj)
            return container.document_service._build_extraction_response(
                project_id, "project_batch", spec_obj
            )
        except (InvalidSlugError, ProjectNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc\
'''


# ─────────────────────────────────────────────────────────────────────────────
# Patch helpers
# ─────────────────────────────────────────────────────────────────────────────

def _literal_patch(content: str, old: str, new: str, description: str, dry_run: bool):
    """Replace a unique literal string.  Fails loudly if 0 or >1 matches."""
    count = content.count(old)
    if count == 0:
        print(f"{_FAIL} NOT FOUND  — {description}")
        return content, False
    if count > 1:
        print(f"{_FAIL} AMBIGUOUS ({count} occurrences) — {description}")
        return content, False
    label = "WOULD APPLY" if dry_run else "APPLIED    "
    print(f"{_OK} {label} — {description}")
    if dry_run:
        return content, True
    return content.replace(old, new, 1), True


def _regex_patch(content: str, pattern: str, replacement: str, description: str, dry_run: bool):
    """Replace a unique regex match (DOTALL).  Fails loudly if 0 or >1 matches."""
    matches = list(re.finditer(pattern, content, re.DOTALL))
    if len(matches) == 0:
        print(f"{_FAIL} NOT FOUND  — {description}")
        return content, False
    if len(matches) > 1:
        print(f"{_FAIL} AMBIGUOUS ({len(matches)} matches) — {description}")
        return content, False
    label = "WOULD APPLY" if dry_run else "APPLIED    "
    print(f"{_OK} {label} — {description}")
    if dry_run:
        return content, True
    return re.sub(pattern, replacement, content, count=1, flags=re.DOTALL), True


def patch_file(rel_path: str, patches: list, dry_run: bool) -> bool:
    """Apply a list of patch dicts to one file.  Returns True if all succeed."""
    path = (CODEBASE_ROOT / rel_path.replace("/", "\\")).resolve()
    if not path.exists():
        print(f"\n{_FAIL} FILE NOT FOUND: {path}")
        return False

    print(f"\n{'[DRY-RUN]' if dry_run else '[WRITING]'} {rel_path}")
    content = path.read_text(encoding="utf-8")
    original_content = content
    all_ok = True

    for p in patches:
        if p.get("regex"):
            content, ok = _regex_patch(
                content, p["pattern"], p["replacement"], p["description"], dry_run
            )
        else:
            content, ok = _literal_patch(
                content, p["old"], p["new"], p["description"], dry_run
            )
        all_ok = all_ok and ok

    if not dry_run:
        if content != original_content:
            path.write_text(content, encoding="utf-8")
            print(f"{_INFO} Saved: {path}")
        else:
            print(f"{_INFO} File unchanged (patches already applied or all failed)")

    return all_ok


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply targeted EAP Bot changes (dry-run by default)."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Write changes to disk (default is preview/dry-run only)",
    )
    args = parser.parse_args()
    dry_run = not args.apply

    if not CODEBASE_ROOT.exists():
        print(f"ERROR: CODEBASE_ROOT not found: {CODEBASE_ROOT}")
        print("       Edit the CODEBASE_ROOT line at the top of this script.")
        sys.exit(1)

    results = []

    # ── FILE 1: source/schemas/project.py ────────────────────────────────────
    # Add Index: Optional[int] to ProjectOut so list_projects can number items.
    results.append(patch_file(
        "source/schemas/project.py",
        [
            {
                "description": "Add Index: Optional[int] field to ProjectOut",
                "old": (
                    'class ProjectOut(BaseModel):\n'
                    '    ProjectID: int = Field(alias="project_id")'
                ),
                "new": (
                    'class ProjectOut(BaseModel):\n'
                    '    Index: Optional[int] = Field(default=None)\n'
                    '    ProjectID: int = Field(alias="project_id")'
                ),
            },
        ],
        dry_run,
    ))

    # ── FILE 2: source/schemas/report.py ─────────────────────────────────────
    # Add AddReportsRequest class (used by the new add_reports endpoint).
    # results.append(patch_file(
    #     "source/schemas/report.py",
    #     [
    #         {
    #             "description": "Add AddReportsRequest class at end of report.py",
    #             "old": (
    #                 'class ReportSuggestionResponse(BaseModel):\n'
    #                 '    ProjectID: int\n'
    #                 '    DocumentID: str\n'
    #                 '    Reports: list[ReportDefinition] = Field(default_factory=list)\n'
    #                 '    Strategy: str = ""  # "event_centric" or "shared"\n'
    #                 '    OverallConfidence: float = 0.0'
    #             ),
    #             "new": (
    #                 'class ReportSuggestionResponse(BaseModel):\n'
    #                 '    ProjectID: int\n'
    #                 '    DocumentID: str\n'
    #                 '    Reports: list[ReportDefinition] = Field(default_factory=list)\n'
    #                 '    Strategy: str = ""  # "event_centric" or "shared"\n'
    #                 '    OverallConfidence: float = 0.0\n'
    #                 '\n'
    #                 '\n'
    #                 'class AddReportsRequest(BaseModel):\n'
    #                 '    """Request body for POST /AddReports/{project_id}.\n'
    #                 '\n'
    #                 '    Contains the confirmed list of reports to persist to\n'
    #                 '    project_batch.json.  Build this from the SuggestedReports\n'
    #                 '    returned by POST /GenerateReports/{project_id}.\n'
    #                 '    """\n'
    #                 '\n'
    #                 '    reports: list[ReportDefinition] = Field(\n'
    #                 '        default_factory=list,\n'
    #                 '        description="Approved report definitions to save into the project.",\n'
    #                 '    )'
    #             ),
    #         },
    #     ],
    #     dry_run,
    # ))

    # ── FILE 3: source/routers/project_routes.py ─────────────────────────────
    # Enumerate projects starting from 1 in list_projects.
    # results.append(patch_file(
    #     "source/routers/project_routes.py",
    #     [
    #         {
    #             "description": "Number projects 1-based (Index) in list_projects",
    #             "old": (
    #                 '    def list_projects(self):\n'
    #                 '        try:\n'
    #                 '            projects = self.storage.list_projects()\n'
    #                 '            return {"ProjectInfo": projects}\n'
    #                 '        except StorageError as exc:\n'
    #                 '            raise HTTPException(500, str(exc)) from exc'
    #             ),
    #             "new": (
    #                 '    def list_projects(self):\n'
    #                 '        try:\n'
    #                 '            projects = self.storage.list_projects()\n'
    #                 '            for i, p in enumerate(projects, start=1):\n'
    #                 '                p.Index = i\n'
    #                 '            return {"ProjectInfo": projects}\n'
    #                 '        except StorageError as exc:\n'
    #                 '            raise HTTPException(500, str(exc)) from exc'
    #             ),
    #         },
    #     ],
    #     dry_run,
    # ))

    # ── FILE 4: source/routers/equipment_routes.py ───────────────────────────
    # All four sub-changes are applied sequentially on the same content buffer
    # inside one patch_file call, so each patch sees the result of the previous.
    results.append(patch_file(
        "source/routers/equipment_routes.py",
        [
            # 4-a: import AddReportsRequest
            {
                "description": "Import AddReportsRequest from source.schemas.report",
                "old": 'from source.schemas.project import DocumentCategory, GenerateReportsRequest',
                "new": (
                    'from source.schemas.project import DocumentCategory, GenerateReportsRequest\n'
                    'from source.schemas.report import AddReportsRequest'
                ),
            },

            # 4-b: remove the download_report route registration line
            {
                "description": "Remove /report route from register_routes",
                "old": (
                    '        self.router.get("/Analyze/{project_id}/{document_id}/report",'
                    ' tags=["documents"])(self.download_report)\n'
                    '        self.router.get("/GetVariable/{project_id}/{document_id}",'
                    ' tags=["documents"])(self.get_variable)'
                ),
                "new": (
                    '        self.router.get("/GetVariable/{project_id}/{document_id}",'
                    ' tags=["documents"])(self.get_variable)'
                ),
            },

            # 4-c: add /AddReports route before /UpdateReports
            {
                "description": "Register /AddReports/{project_id} endpoint",
                "old": (
                    '        self.router.post("/GenerateReports/{project_id}",'
                    ' tags=["documents"])(self.generate_reports)\n'
                    '        self.router.put("/UpdateReports/{project_id}",'
                    ' tags=["documents"])(self.update_reports)'
                ),
                "new": (
                    '        self.router.post("/GenerateReports/{project_id}",'
                    ' tags=["documents"])(self.generate_reports)\n'
                    '        self.router.post("/AddReports/{project_id}",'
                    ' tags=["documents"])(self.add_reports)\n'
                    '        self.router.put("/UpdateReports/{project_id}",'
                    ' tags=["documents"])(self.update_reports)'
                ),
            },

            # 4-d: remove the download_report method entirely
            # Regex from "def download_report(" to just before "def get_variable("
            {
                "description": "Remove download_report method body",
                "regex": True,
                "pattern": (
                    r'\n    def download_report\(self, project_id: int, document_id: str\):.*?'
                    r'\n    def get_variable\(self'
                ),
                "replacement": '\n    def get_variable(self',
            },

            # 4-e: replace generate_reports (suggest-only) + inject add_reports
            # Regex: from "def generate_reports(" up to (not including) "def update_reports("
            {
                "description": "Replace generate_reports body (suggest-only) + inject add_reports",
                "regex": True,
                "pattern": (
                    r'    def generate_reports\(self,.*?'
                    r'(?=\n    def update_reports)'
                ),
                "replacement": _NEW_GENERATE_REPORTS,
            },
        ],
        dry_run,
    ))

    # ── FILE 5: test/test_documents_endpoints.py ─────────────────────────────
    # Remove the three download-report test functions (Group 4).
    # Uses regex to match from the Group 4 comment header to just before Group 5.
    results.append(patch_file(
        "test/test_documents_endpoints.py",
        [
            {
                "description": "Remove Group 4 (download_report) test functions",
                "regex": True,
                # Match any comment line containing "Group 4" then everything
                # up to (but not including) any comment line containing "Group 5".
                "pattern": (
                    r'\n# [^\n]*Group 4[^\n]*\n'       # e.g.  # ── Group 4 ──
                    r'.*?'                              # all three test functions
                    r'(?=\n# [^\n]*Group 5)'            # stop before Group 5 header
                ),
                "replacement": "",
            },
        ],
        dry_run,
    ))

    # ── Summary ──────────────────────────────────────────────────────────────
    passed = sum(results)
    total  = len(results)
    print("\n" + "=" * 62)
    if all(results):
        if dry_run:
            print(f"DRY-RUN COMPLETE — {passed}/{total} files would be patched.")
            print("Run with --apply to write the changes.")
        else:
            print(f"DONE — {passed}/{total} files patched successfully.")
            print("Restart your FastAPI server to pick up the changes.")
    else:
        failed = total - passed
        print(f"WARNING — {failed}/{total} file(s) had patch failures.")
        print("Review the [!!] lines above.  Nothing broken was written.")
        if dry_run:
            print("Fix the mismatches before running --apply.")
    print("=" * 62)


if __name__ == "__main__":
    main()
