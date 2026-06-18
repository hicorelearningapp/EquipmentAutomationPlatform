import logging
from pathlib import Path
from typing import Any

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

from source.schemas.secsgem import EquipmentSpec

logger = logging.getLogger(__name__)

class ReportGenerator:
    """Generates the Summary Report in PDF format matching 'PDF Saving format.pdf'."""

    def __init__(self) -> None:
        self.styles = getSampleStyleSheet()
        self.title_style = ParagraphStyle(
            'TitleStyle',
            parent=self.styles['Heading1'],
            fontName='Helvetica-Bold',
            fontSize=16,
            alignment=1, # Center
            spaceAfter=20
        )
        self.h1_style = ParagraphStyle(
            'H1Style',
            parent=self.styles['Heading2'],
            fontName='Helvetica-Bold',
            fontSize=12,
            spaceBefore=15,
            spaceAfter=10
        )
        self.normal_style = self.styles['Normal']

    def _add_heading(self, text: str, elements: list) -> None:
        elements.append(Paragraph(text, self.h1_style))

    def _add_paragraph(self, text: str, elements: list, bullet: bool = False) -> None:
        style = self.normal_style
        # Basic xml escape to prevent ReportLab crash with < or >
        text = str(text).replace('<', '&lt;').replace('>', '&gt;')
        if bullet:
            text = f"• {text}"
        elements.append(Paragraph(text, style))
        elements.append(Spacer(1, 5))

    def _add_table(self, headers: list[str], rows: list[list[str]], elements: list) -> None:
        if not rows:
            self._add_paragraph("No data available.", elements)
            return

        table_data = []
        
        # Headers
        header_row = [Paragraph(f"<b>{h}</b>", self.normal_style) for h in headers]
        table_data.append(header_row)

        # Rows
        for row in rows:
            table_row = []
            for cell in row:
                cell_text = str(cell) if cell is not None else ""
                cell_text = cell_text.replace('<', '&lt;').replace('>', '&gt;')
                # Convert newlines to break tags for reportlab
                cell_text = cell_text.replace('\n', '<br/>')
                table_row.append(Paragraph(cell_text, self.normal_style))
            table_data.append(table_row)

        # Determine column widths roughly, or let ReportLab calculate
        table = Table(table_data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
        ]))
        
        elements.append(table)
        elements.append(Spacer(1, 10))

    def generate_report(self, spec: EquipmentSpec, output_path: Path, project_metadata: Any = None) -> None:
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=letter,
            rightMargin=30,
            leftMargin=30,
            topMargin=30,
            bottomMargin=30
        )
        elements = []
        
        # Title
        elements.append(Paragraph('SECS/GEM Interface Manual Preparation Process', self.title_style))
        
        summary = spec.Summary

        # 1. Equipment Information
        self._add_heading('1. Equipment Information', elements)
        self._add_paragraph("Collect and document the basic equipment details:", elements)
        p_id = str(project_metadata.ProjectID) if project_metadata else ""
        p_name = project_metadata.ProjectName if project_metadata else ""
        p_tool = project_metadata.Tool if project_metadata else ""
        p_vendor = project_metadata.VendorName if project_metadata else ""

        equip_rows = [
            ["Project ID", p_id],
            ["Project Name", p_name],
            ["Equipment Name", summary.EquipmentName if summary else spec.ToolType or ""],
            ["Vendor Name", p_vendor],
            ["Tool Type", p_tool],
            ["Protocol", spec.Protocol or "SECS/GEM"],
            ["Model", spec.Model or ""],
            ["200mm/300mm", summary.WaferSize if summary else ""],
            ["Software Revision", summary.SoftwareRevision if summary else ""],
            ["Tool ID (Equipment)", summary.ToolID if summary else spec.ToolID or ""]
        ]
        self._add_table(["Item", "Description"], equip_rows, elements)

        # 2. Standards Supported
        self._add_heading('2. Standards Supported', elements)
        self._add_paragraph("Document all communication standards supported by the equipment.", elements)
        std_rows = []
        if summary and summary.StandardsSupported:
            for std in summary.StandardsSupported:
                std_rows.append([std.Standard, std.Version or ""])
        self._add_table(["Standard", "Version"], std_rows, elements)

        # 3. GEM Compliance Statement Table
        self._add_heading('3. GEM Compliance Statement Table', elements)
        self._add_paragraph("Provide a detailed GEM compliance statement including:", elements)
        gem_rows = []
        if summary and summary.GEMCompliance:
            for item in summary.GEMCompliance:
                if hasattr(item, "Feature"):
                    gem_rows.append([item.Feature or "", item.Implemented or ""])
                else:
                    # Fallback if old data format
                    gem_rows.append([str(item), ""])
            self._add_table(["Feature", "Implemented"], gem_rows, elements)
        else:
            for item in ["Communication Capabilities", "Control Capabilities", "Data Collection Features", "Alarm Management"]:
                self._add_paragraph(item, elements, bullet=True)

        # 4. HSMS Communication Configuration
        self._add_heading('4. HSMS Communication Configuration', elements)
        self._add_paragraph("Connection Parameters", elements)
        hsms_rows = []
        if summary and summary.HSMSConfiguration:
            hsms = summary.HSMSConfiguration
            hsms_rows = [
                ["Device ID", hsms.DeviceID or ""],
                ["IP Address", hsms.IPAddress or ""],
                ["Port Number", hsms.PortNumber or ""],
                ["Baud Rate (if applicable)", hsms.BaudRate or ""],
                ["Timeout", hsms.Timeout or ""]
            ]
        self._add_table(["Parameter", "Value"], hsms_rows, elements)

        # 5. Supported Stream and Functions
        self._add_heading('5. Supported Stream and Functions', elements)
        self._add_paragraph("Document all implemented Stream/Function pairs.", elements)
        sf_rows = []
        if summary and summary.StreamFunctions:
            for sf in summary.StreamFunctions:
                sf_rows.append([sf.Stream, sf.Function, sf.Description])
        self._add_table(["Stream", "Function", "Description"], sf_rows, elements)

        # 6. Communication State Model
        self._add_heading('6. Communication State Model', elements)
        self._add_paragraph("Provide communication state transition table.", elements)
        self._add_paragraph("Communication States", elements)
        cs_rows = []
        if summary and summary.CommunicationStates:
            for cs in summary.CommunicationStates:
                cs_rows.append([cs.State, cs.Description])
        self._add_table(["State", "Description"], cs_rows, elements)

        # 7. Control State Model
        self._add_heading('7. Control State Model', elements)
        self._add_paragraph("Control States", elements)
        ctrl_rows = []
        if summary and summary.ControlStates:
            for cs in summary.ControlStates:
                ctrl_rows.append([cs.State, cs.Description])
        self._add_table(["State", "Description"], ctrl_rows, elements)

        # 8. Remote Command Definition
        self._add_heading('8. Remote Command Definition (S2F41 or S2F49)', elements)
        self._add_paragraph("Remote Command Table", elements)
        rcmd_rows = []
        for cmd in spec.RemoteCommands:
            params = ", ".join([p.Name for p in cmd.Parameters]) if cmd.Parameters else "None"
            rcmd_rows.append([cmd.RCMD, cmd.Description or "", params])
        self._add_table(["Command Name", "Description", "Parameters"], rcmd_rows, elements)

        # 9. Error Message Dictionary
        self._add_heading('9. Error Message Dictionary', elements)
        self._add_table(["Error Code", "Error Message", "Description"], [], elements)

        # 10. Data Dictionary
        self._add_heading('10. Data Dictionary', elements)
        
        self._add_paragraph("Collection Events (CEID)", elements, bullet=True)
        ceid_rows = []
        for ev in spec.Events:
            vids = ", ".join(map(str, ev.LinkedVIDs)) if ev.LinkedVIDs else ""
            ceid_rows.append([str(ev.CEID), ev.EventName, ev.Description or "", vids])
        self._add_table(["CEID", "Event Name", "Description", "Linked Variables"], ceid_rows, elements)
        
        self._add_paragraph("Status Variables (SVID)", elements, bullet=True)
        svid_rows = []
        for sv in spec.StatusVariables:
            svid_rows.append([str(sv.SVID), sv.Name, sv.DataType or "", sv.Description or ""])
        self._add_table(["SVID", "Variable Name", "Data Type", "Description"], svid_rows, elements)

        self._add_paragraph("Data Variables (DVID)", elements, bullet=True)
        dvid_rows = []
        for dv in spec.DataVariables:
            dvid_rows.append([str(dv.DvID), dv.Name, dv.ValueType or "", dv.Unit or ""])
        self._add_table(["DVID", "Variable Name", "Data Type", "Description"], dvid_rows, elements)

        self._add_paragraph("Equipment Constants (ECID)", elements, bullet=True)
        self._add_table(["ECID", "Constant Name", "Data Type", "Default Value", "Description"], [], elements)

        self._add_paragraph("Alarm Definitions", elements, bullet=True)
        alarm_rows = []
        for al in spec.Alarms:
            alarm_rows.append([str(al.AlarmID), al.AlarmName, al.Severity, al.Description or ""])
        self._add_table(["Alarm ID", "Alarm Name", "Severity", "Description"], alarm_rows, elements)

        # 11. Data Collection from Base Log
        self._add_heading('11. Data Collection from Base Log', elements)
        actions = [
            "Convert base communication logs into SML format.",
            "Execute GEM testing and validate functionality.",
            "Prepare the GEM characterization document.",
            "Generate a command reference report from SML messages in table format.",
            "Analyse and document Event Reports.",
            "Analyse and document Remote Commands.",
            "Analyse and document Trace Data Collection features."
        ]
        for i, act in enumerate(actions, 1):
            self._add_paragraph(f"{i}. {act}", elements)

        # 12. SmartAutomation.Go-Start Coding
        self._add_heading('12. SmartAutomation.Go-Start Coding', elements)

        # Build document
        try:
            doc.build(elements)
            logger.info(f"Summary Report generated at {output_path}")
        except Exception as e:
            logger.error(f"Failed to build PDF report: {e}")
