import openpyxl
import os

excel_file = "BraceLink Testcases (1).xlsx"
sheet_name = "newly updated testcase"

# New test cases to append
new_cases = [
    [
        "TC ID - 501",
        "Verify the C# Code Generation successfully creates compilable equipment driver code based on the completed MES Mapping.",
        "1. Complete MES Mapping for a document.\n2. Click the Generate Code button.\n3. Review the generated C# code.",
        "1. The code should be generated without errors.\n2. The code should reflect the defined mapping correctly.\n3. The code should compile successfully.",
        ""
    ],
    [
        "TC ID - 502",
        "Verify that attempting to generate C# code with incomplete mandatory MES variable mappings shows a validation error.",
        "1. Leave mandatory MES mapping fields empty.\n2. Attempt to generate C# code.",
        "1. The system should block code generation.\n2. A clear validation error should be displayed highlighting missing fields.",
        ""
    ],
    [
        "TC ID - 503",
        "Verify that generated code accurately reflects any manual overrides made in the Smart Mapping grid.",
        "1. Auto Map a document.\n2. Manually override a mapped connection.\n3. Generate C# code and review it.",
        "1. The generated code should reflect the manual override rather than the original auto-mapped value.",
        ""
    ],
    [
        "TC ID - 504",
        "Verify the system's behavior when the AI API keys are invalid, missing, or rate-limited.",
        "1. Remove or invalidate API keys in the backend configuration.\n2. Attempt to Analyze a document.",
        "1. The system should gracefully handle the failure.\n2. The UI should display a clear error message instead of hanging indefinitely.",
        ""
    ],
    [
        "TC ID - 505",
        "Verify the extraction behavior when an irrelevant or corrupted PDF is uploaded.",
        "1. Upload a non-SECS/GEM PDF (e.g., a cooking recipe).\n2. Run the Analysis process.",
        "1. The system should process without crashing.\n2. The extraction should return empty results rather than hallucinating fake SECS/GEM variables.",
        ""
    ],
    [
        "TC ID - 506",
        "Verify that the UI handles timeouts gracefully for massively large PDFs.",
        "1. Upload a massive PDF document (>1000 pages).\n2. Click Analyze and wait.",
        "1. If the background process exceeds limits, the UI should handle the timeout gracefully.\n2. Status should update to \"Failed\" or \"Timeout\" without crashing the app.",
        ""
    ],
    [
        "TC ID - 507",
        "Verify that analyzing multiple documents simultaneously across different projects does not cause data bleeding or crashes.",
        "1. Open two projects in separate tabs.\n2. Start analysis on both simultaneously.",
        "1. Both background processes should run in parallel in isolated workspaces.\n2. Data from one project should not bleed into the other.",
        ""
    ],
    [
        "TC ID - 508",
        "Verify that navigating away from the Extraction tab does not cancel a running analysis.",
        "1. Start an analysis.\n2. Navigate to another project or tab.\n3. Return to the original project.",
        "1. The analysis should continue running in the background.\n2. The UI should accurately reflect the ongoing status upon returning.",
        ""
    ]
]

try:
    print(f"Opening workbook: {excel_file}")
    wb = openpyxl.load_workbook(excel_file)
    
    if sheet_name in wb.sheetnames:
        sheet = wb[sheet_name]
        print(f"Found sheet: {sheet_name}. Appending rows...")
        for row in new_cases:
            sheet.append(row)
            
        wb.save(excel_file)
        print("Successfully appended new test cases to the Excel file.")
    else:
        print(f"Error: Sheet '{sheet_name}' not found.")

except Exception as e:
    print(f"An error occurred: {e}")
