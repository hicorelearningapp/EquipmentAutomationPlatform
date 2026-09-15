import json
import re
from reportlab.lib.pagesizes import landscape, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

def generate_pdf():
    pdf_path = "api_endpoints.pdf"
    doc = SimpleDocTemplate(pdf_path, pagesize=landscape(A4), rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20)
    
    styles = getSampleStyleSheet()
    bold_style = ParagraphStyle('BoldStyle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10)
    desc_style = ParagraphStyle('DescStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=9, textColor=colors.darkslategray)
    header_style = ParagraphStyle('HeaderStyle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=12, textColor=colors.whitesmoke)
    code_style = ParagraphStyle('CodeStyle', parent=styles['Normal'], fontName='Courier', fontSize=8, leading=10, wordWrap='CJK')

    data = [
        [Paragraph("#", header_style), Paragraph("Endpoint", header_style), Paragraph("Description", header_style), Paragraph("Input JSON Structure / Parameters", header_style), Paragraph("Output JSON Structure", header_style)]
    ]

    endpoints = [
        # PROJECT ROUTES
        {
            "endpoint": "POST /CreateProject",
            "desc": "Creates a new project with basic metadata.",
            "input": '{\n  "ProjectName": "string",\n  "VendorName": "string",\n  "ProjectCode": "string",\n  "ProjectDescription": "string (optional)",\n  "Tool": "None | MOCVD | CVD | LITHO | ETCH | ION_IMPLANTER"\n}',
            "output": '{\n  "ProjectID": 0,\n  "ProjectName": "string",\n  "VendorName": "string",\n  "ProjectCode": "string",\n  "ProjectDescription": "string",\n  "Tool": "string",\n  "CreatedAt": "2023-01-01T00:00:00",\n  "LastUpdatedOn": "2023-01-01T00:00:00",\n  "Status": "string",\n  "ProjectVersion": "1.0"\n}'
        },
        {
            "endpoint": "GET /GetAllProjects",
            "desc": "Retrieves a list of all existing projects.",
            "input": "None (No body or parameters)",
            "output": '{\n  "ProjectInfo": [\n    {\n      "ProjectID": 0,\n      "ProjectName": "string",\n      "VendorName": "string",\n      "ProjectCode": "string",\n      "ProjectDescription": "string",\n      "Tool": "string",\n      "CreatedAt": "2023-01-01T00:00:00",\n      "LastUpdatedOn": "2023-01-01T00:00:00",\n      "Status": "string",\n      "ProjectVersion": "1.0"\n    }\n  ]\n}'
        },
        {
            "endpoint": "GET /LoadProject/{project_id}",
            "desc": "Loads full project data including documents and extractions.",
            "input": "Path Parameter: \nproject_id (int)",
            "output": '{\n  "ProjectID": 0,\n  "ProjectName": "string",\n  "VendorName": "string",\n  "ProjectCode": "string",\n  "ProjectDescription": "string",\n  "Tool": "string",\n  "CreatedAt": "2023-01-01T00:00:00",\n  "LastUpdatedOn": "2023-01-01T00:00:00",\n  "Status": "string",\n  "ProjectVersion": "1.0",\n  "Documents": [\n    {\n      "DocumentID": "string",\n      "DocumentType": "User Manuals",\n      "FileName": "string",\n      "FileSize": 0.0,\n      "Pages": 0,\n      "UploadDate": "2023-01-01T00:00:00",\n      "Status": "completed"\n    }\n  ],\n  "Extractions": {\n    "StatusVariables": [...],\n    "DataVariables": [...],\n    "Events": [...],\n    "Alarms": [...],\n    "RemoteCommands": [...],\n    "States": [...],\n    "StateTransitions": [...],\n    "Reports": [...]\n  },\n  "Mappings": {},\n  "SmlTemplate": {},\n  "Questions": []\n}'
        },
        {
            "endpoint": "PUT /UpdateProject/{project_id}",
            "desc": "Updates metadata of an existing project.",
            "input": 'Path Parameter: \nproject_id (int)\n\nBody:\n{\n  "ProjectName": "string (optional)",\n  "ProjectDescription": "string (optional)",\n  "VendorName": "string (optional)",\n  "ProjectCode": "string (optional)",\n  "Tool": "ToolType (optional)",\n  "ProjectVersion": "string (optional)"\n}',
            "output": '{\n  "ProjectID": 0,\n  "ProjectName": "string",\n  "VendorName": "string",\n  "ProjectCode": "string",\n  "ProjectDescription": "string",\n  "Tool": "string",\n  "CreatedAt": "2023-01-01T00:00:00",\n  "LastUpdatedOn": "2023-01-01T00:00:00",\n  "Status": "string",\n  "ProjectVersion": "1.0"\n}'
        },
        {
            "endpoint": "DELETE /DeleteProject/{project_id}",
            "desc": "Deletes a project and all its associated data.",
            "input": "Path Parameter: \nproject_id (int)",
            "output": '{\n  "ProjectName": "string",\n  "ProjectID": 0,\n  "Status": "deleted"\n}'
        },
        {
            "endpoint": "GET /Analyze/{project_id}/{document_id}",
            "desc": "Starts or retrieves extraction for a specific document.",
            "input": "Path Parameters: \nproject_id (int)\ndocument_id (str)",
            "output": '{\n  "ProjectID": 0,\n  "ExtractionID": "string",\n  "ConfidenceScore": 0.0,\n  "ExtractionStatus": "completed",\n  "StatusVariables": [...],\n  "DataVariables": [...],\n  "Events": [...],\n  "Alarms": [...],\n  "RemoteCommands": [...],\n  "States": [...],\n  "StateTransitions": [...],\n  "Reports": [...]\n}'
        },
        {
            "endpoint": "GET /AnalyzeProject/{project_id}",
            "desc": "Aggregates and analyzes the entire project batch.",
            "input": "Path Parameter: \nproject_id (int)",
            "output": "Returns Extraction Response\n(Same structure as GET /Analyze)"
        },
        {
            "endpoint": "POST /ReAnalyzeProject/{project_id}",
            "desc": "Forces re-analysis of all documents in a project.",
            "input": "Path Parameter: \nproject_id (int)",
            "output": "Returns ProjectDetail \n(Same output structure as GET /LoadProject/{project_id})"
        },
        {
            "endpoint": "GET /GetKnowledgeCategory/{project_id}",
            "desc": "Lists available document categories.",
            "input": "Path Parameter: \nproject_id (int)",
            "output": '[\n  "User Manuals",\n  "GEM Manual",\n  "Variable Files",\n  "Log Files",\n  "Alarm Files",\n  "SML Scripts"\n]'
        },
        {
            "endpoint": "POST /Ask/{project_id}",
            "desc": "Queries the project's knowledge base via LLM.",
            "input": 'Path Parameter: \nproject_id (int)\n\nBody:\n{\n  "Question": "string",\n  "DocumentCategory": "string (optional)"\n}',
            "output": '{\n  "ProjectID": 0,\n  "DocumentID": "string",\n  "DocumentCategory": "string",\n  "Answer": "string",\n  "Source": "string",\n  "Context": ["string"],\n  "Citations": ["string"]\n}'
        },
        {
            "endpoint": "GET /GetProjectDetails/{project_id}",
            "desc": "Gets statistics and summary for a single project.",
            "input": "Path Parameter: \nproject_id (int)",
            "output": '{\n  "Id": 0,\n  "ProjectName": "string",\n  "ProjectCode": "string",\n  "ProjectDescription": "string",\n  "VendorName": "string",\n  "Tool": "string",\n  "ProjectVersion": "string",\n  "CreatedAt": "2023-01-01T00:00:00",\n  "DocumentCount": 0,\n  "SVCount": 0,\n  "DVCount": 0,\n  "RCCount": 0,\n  "SmlScriptCount": 0,\n  "ReportCount": 0,\n  "AlarmCount": 0,\n  "EventCount": 0\n}'
        },
        {
            "endpoint": "GET /GetSystemSummary",
            "desc": "Retrieves system-wide project statistics.",
            "input": "None (No body or parameters)",
            "output": '{\n  "TotalProjects": 0,\n  "TotalSmlScripts": 0,\n  "TotalConnectedTools": 0,\n  "TotalScriptsTested": 0\n}'
        },

        # EQUIPMENT ROUTES
        {
            "endpoint": "POST /UploadDocument/{project_id}",
            "desc": "Uploads a file for analysis in a project.",
            "input": "Path Parameter: \nproject_id (int)\n\nForm Data:\n- file: UploadFile\n- document_type: DocumentCategory",
            "output": '{\n  "DocumentID": "string",\n  "DocumentType": "string",\n  "FileName": "string",\n  "FileSize": 0.0,\n  "Pages": 0,\n  "UploadDate": "2023-01-01T00:00:00",\n  "Status": "uploaded"\n}'
        },
        {
            "endpoint": "GET /Analyze/{project_id}/{document_id}/report",
            "desc": "Downloads the JSON report for a document.",
            "input": "Path Parameters: \nproject_id (int)\ndocument_id (str)",
            "output": "Binary File Download\n(application/json)"
        },
        {
            "endpoint": "GET /GetVariable/{project_id}/{document_id}",
            "desc": "Retrieves extracted variables for a document.",
            "input": "Path Parameters: \nproject_id (int)\ndocument_id (str)\n\nQuery Parameter:\ncategories (str, optional)",
            "output": '[\n  {\n    "SVID": 0,\n    "Name": "string",\n    "DataType": "string",\n    "Value": "string",\n    ...\n  }\n]'
        },
        {
            "endpoint": "DELETE /DeleteDocument/{project_id}/{document_id}",
            "desc": "Removes a document from the project.",
            "input": "Path Parameters: \nproject_id (int)\ndocument_id (str)",
            "output": '{\n  "Status": "success",\n  "Message": "Document {document_id} deleted"\n}'
        },
        {
            "endpoint": "POST /UpdateExtraction/{project_id}",
            "desc": "Manually overrides extraction results for a project.",
            "input": 'Path Parameter: \nproject_id (int)\n\nBody (UpdateExtractionRequest):\n{\n  "ProjectID": 0,\n  "ExtractionID": "string",\n  "ConfidenceScore": 0.0,\n  "ExtractionStatus": "completed",\n  "StatusVariables": [...],\n  "DataVariables": [...],\n  "Events": [...],\n  "Alarms": [...],\n  "RemoteCommands": [...],\n  "States": [...],\n  "StateTransitions": [...],\n  "Reports": [...]\n}',
            "output": '{\n  "Status": "success",\n  "Message": "Extraction updated successfully"\n}'
        },
        {
            "endpoint": "POST /GenerateReports/{project_id}",
            "desc": "Generates synthetic reports based on CEIDs.",
            "input": 'Path Parameter: \nproject_id (int)\n\nBody (GenerateReportsRequest):\n{\n  "ceids": [101, 102]\n}',
            "output": "Returns Extraction Response\n(Same structure as GET /Analyze)"
        },
        {
            "endpoint": "PUT /UpdateReports/{project_id}",
            "desc": "Updates the definitions of synthetic reports.",
            "input": 'Path Parameter: \nproject_id (int)\n\nBody:\n{\n  "Reports": [\n    {\n      "RPTID": 1,\n      "Name": "string",\n      "LinkedVIDs": [1, 2],\n      ...\n    }\n  ]\n}',
            "output": "Returns Extraction Response\n(Same structure as GET /Analyze)"
        },
        {
            "endpoint": "GET /GetQuestions/{project_id}",
            "desc": "Retrieves AI-generated questions for a project.",
            "input": "Path Parameter: \nproject_id (int)",
            "output": '{\n  "Questions": [\n    {\n      "Topic": "string",\n      "Question": "string"\n    }\n  ]\n}'
        },
        # MAPPING ROUTES
        {
            "endpoint": "PUT /UpdateMapping/{project_id}",
            "desc": "Saves an approved mapping of MES tags to Equipment entities.",
            "input": 'Path Parameter: \nproject_id (int)\n\nBody:\n{\n  "project_id": 0,\n  "family": "string",\n  "template": "string",\n  "Mappings": [\n    {\n      "MESField": "string",\n      "EquipmentFieldName": "string",\n      "EntityType": "variable|event|alarm"\n    }\n  ]\n}',
            "output": '{\n  "ProjectID": 0,\n  "Status": "success",\n  "Message": "Mapping saved to path/to/file"\n}'
        },
        {
            "endpoint": "POST /AutoMap",
            "desc": "Automatically maps unresolved MES tags to equipment entities.",
            "input": 'Body:\n{\n  "family": "string",\n  "template": "string",\n  "Variables": [...],\n  "Events": [...],\n  "Alarms": [...]\n}',
            "output": "Returns mapped template dictionary\n(Same structure as input body)"
        },
        # TOOL CHARACTERIZATION ROUTES
        {
            "endpoint": "POST /GenerateTestScripts/{project_id}",
            "desc": "Generates test scripts (SML) from templates.",
            "input": 'Path Parameter: \nproject_id (int)\n\nBody:\n{\n  "filename": "string"\n}',
            "output": '{\n  "script": "string (raw SML text)"\n}'
        },
        {
            "endpoint": "POST /UpdateToolCharacterizationScript/{project_id}",
            "desc": "Updates and saves an SML test script.",
            "input": 'Path Parameter: \nproject_id (int)\n\nBody:\n{\n  "key": "string",\n  "script": "string (raw SML text)"\n}',
            "output": '{\n  "Status": "success",\n  "Message": "string",\n  "FilePath": "string"\n}'
        },
        {
            "endpoint": "POST /GenerateSMLScripts/{project_id}",
            "desc": "Generates all required SML test scripts for a project.",
            "input": "Path Parameter: \nproject_id (int)",
            "output": '{\n  "Status": "success",\n  "Scripts": [\n    {\n      "FileName": "string",\n      "SML": "string"\n    }\n  ]\n}'
        },
        {
            "endpoint": "POST /UploadTestResult",
            "desc": "Uploads test execution logs or JSON results.",
            "input": "Form Data:\n- project_id (int)\n- tool_id (str)\n- files (List[UploadFile])",
            "output": '{\n  "Status": "success",\n  "Message": "string",\n  "Paths": ["string"]\n}'
        },
        {
            "endpoint": "GET /GetToolResults/{project_id}",
            "desc": "Retrieves test execution results for a specific tool.",
            "input": "Path Parameter: \nproject_id (int)\n\nQuery Parameter:\ntool_id (str)",
            "output": '{\n  "ToolResults": [...]\n}'
        },
        # SMART AUTOMATION ROUTES
        {
            "endpoint": "POST /GenerateSmartAutomationCode/{project_id}",
            "desc": "Generates C# constants for smart automation from the equipment spec.",
            "input": 'Path Parameter: \nproject_id (int)\n\nBody:\n{\n  "key": "string"\n}',
            "output": '{\n  "Status": "success",\n  "Code": "string (C# source code)",\n  "FilePath": "string"\n}'
        },
        {
            "endpoint": "POST /UpdateSmartAutomationCode/{project_id}",
            "desc": "Updates and saves smart automation C# code.",
            "input": 'Path Parameter: \nproject_id (int)\n\nBody:\n{\n  "key": "string",\n  "source_code": "string"\n}',
            "output": '{\n  "Status": "success",\n  "Message": "string",\n  "FilePath": "string"\n}'
        },
        {
            "endpoint": "POST /GenerateOverallReport/{project_id}",
            "desc": "Generates a final overall summary report for the project.",
            "input": "Path Parameter: \nproject_id (int)",
            "output": '{\n  "Status": "success",\n  "Report": {\n    "ProjectID": 0,\n    "ProjectName": "string",\n    "GeneratedAt": "2023-01-01T00:00:00",\n    "OverallStatus": "string",\n    "DocumentCount": 0,\n    "ReportSummary": "string"\n  }\n}'
        },

        # MES FAMILY ROUTES
        {
            "endpoint": "GET /GetMesFamilies",
            "desc": "Lists all configured MES families.",
            "input": "None (No body or parameters)",
            "output": '[\n  {\n    "FamilyID": 0,\n    "Family": "string",\n    "DefaultProtocol": "string",\n    "RequiresAck": true,\n    "Description": "string"\n  }\n]'
        },
        {
            "endpoint": "POST /UpdateMesFamilies",
            "desc": "Updates or creates new MES families.",
            "input": 'Body:\n[\n  {\n    "FamilyID": 0,\n    "Family": "string",\n    "DefaultProtocol": "string",\n    "RequiresAck": true,\n    "Description": "string"\n  }\n]',
            "output": '{\n  "Status": "success",\n  "Message": "MES families updated successfully",\n  "Families": [\n    {\n      "FamilyID": 0,\n      "Family": "string",\n      ...\n    }\n  ]\n}'
        },
        {
            "endpoint": "GET /GetMesTemplates/{mes_family}",
            "desc": "Lists JSON templates available in an MES family.",
            "input": "Path Parameter: \nmes_family (str)",
            "output": '[\n  "STANDARD_EVENT_MODEL.json",\n  "ANOTHER_TEMPLATE.json"\n]'
        },
        {
            "endpoint": "GET /GetMesTemplateInfo/{mes_family}/{template}",
            "desc": "Retrieves the JSON contents of a template.",
            "input": "Path Parameters: \nmes_family (str)\ntemplate (str)",
            "output": '{\n  "TemplateName": "string",\n  "MESFamily": "string",\n  "Version": "1.0",\n  "Events": [],\n  "Alarms": [],\n  "Variables": [],\n  "Payloads": [],\n  "Transactions": [],\n  "ValidationRules": [],\n  "AutoMapping": {},\n  "Logging": {}\n}'
        },
        {
            "endpoint": "POST /AddMesTemplateInfo/{mes_family}",
            "desc": "Uploads a new JSON template to an MES family.",
            "input": "Path Parameter: \nmes_family (str)\n\nForm Data:\n- file: UploadFile (.json)",
            "output": '{\n  "Status": "success",\n  "Message": "Template \'{file.filename}\' added successfully to family \'{canonical_name}\'"\n}'
        },
        {
            "endpoint": "PUT /UpdateMesTemplateInfo/{mes_family}/{template}",
            "desc": "Updates an existing MES template with new data.",
            "input": "Path Parameters: \nmes_family (str)\ntemplate (str)\n\nForm Data:\n- file: UploadFile (.json)",
            "output": '{\n  "Status": "success",\n  "Message": "Template \'{template}\' updated successfully in family \'{canonical_name}\'",\n  "Version": "1.1"\n}'
        }
    ]

    def make_pretty(text):
        return text.replace(' ', '&nbsp;').replace('\n', '<br/>')

    for idx, item in enumerate(endpoints, 1):
        input_text = make_pretty(item["input"])
        output_text = make_pretty(item["output"])
        
        endpoint_clean = re.sub(r'^(GET|POST|PUT|DELETE)\s+', '', item["endpoint"])
        row = [
            Paragraph(str(idx), bold_style),
            Paragraph(endpoint_clean, bold_style),
            Paragraph(item["desc"], desc_style),
            Paragraph(input_text, code_style),
            Paragraph(output_text, code_style)
        ]
        data.append(row)

    # 5 columns: Index, Endpoint, Description, Input, Output
    # Total width ~780 for A4 landscape
    table = Table(data, colWidths=[30, 110, 130, 240, 270], repeatRows=1)
    
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#333333")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor("#f9f9f9")),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor("#dddddd")),
        ('PADDING', (0, 0), (-1, -1), 8),
    ]))

    for i in range(1, len(data)):
        if i % 2 == 0:
            table.setStyle(TableStyle([('BACKGROUND', (0, i), (-1, i), colors.HexColor("#ffffff"))]))

    elements = []
    
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], alignment=1)
    elements.append(Paragraph("API Endpoints Reference", title_style))
    elements.append(Spacer(1, 15))
    elements.append(table)
    
    doc.build(elements)
    print(f"PDF generated successfully at {pdf_path}")

if __name__ == '__main__':
    generate_pdf()
