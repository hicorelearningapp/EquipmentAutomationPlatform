from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


OUTPUT_PATH = Path(__file__).with_name("ETCH_Z500_GEM_Spec_Demo.pdf")
DOC_NO = "ND-ETCHZ500-GEM-ICD-001 Rev A"


def _styles():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="TitleCenter",
            parent=styles["Title"],
            alignment=TA_CENTER,
            fontSize=24,
            leading=30,
            spaceAfter=18,
            textColor=colors.HexColor("#1f3a5f"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="SubtitleCenter",
            parent=styles["Normal"],
            alignment=TA_CENTER,
            fontSize=12,
            leading=16,
            textColor=colors.HexColor("#4b5563"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="Chapter",
            parent=styles["Heading1"],
            fontSize=16,
            leading=20,
            spaceBefore=4,
            spaceAfter=10,
            textColor=colors.HexColor("#1f3a5f"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="Small",
            parent=styles["Normal"],
            fontSize=8,
            leading=10,
        )
    )
    return styles


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#4b5563"))
    canvas.drawString(0.55 * inch, 0.35 * inch, DOC_NO)
    canvas.drawRightString(7.95 * inch, 0.35 * inch, f"Page {doc.page}")
    canvas.restoreState()


def _table(data, col_widths=None, font_size=7):
    tbl = Table(data, colWidths=col_widths, repeatRows=1)
    style = TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3a5f")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), font_size),
            ("LEADING", (0, 0), (-1, -1), font_size + 2),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
    )
    tbl.setStyle(style)
    return tbl


def _para_rows(rows, styles):
    return [[Paragraph(str(cell), styles["Small"]) for cell in row] for row in rows]


def build_pdf(output_path=OUTPUT_PATH):
    styles = _styles()
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        rightMargin=0.45 * inch,
        leftMargin=0.45 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.55 * inch,
        title="ETCH-Z500 GEM Interface Specification",
        author="NanoDyne Systems",
    )

    story = []

    story.extend(
        [
            Spacer(1, 1.1 * inch),
            Paragraph("ETCH-Z500", styles["TitleCenter"]),
            Paragraph("Plasma Etch Tool SECS/GEM Interface Specification", styles["SubtitleCenter"]),
            Spacer(1, 0.35 * inch),
            Paragraph("NanoDyne Systems", styles["SubtitleCenter"]),
            Paragraph(DOC_NO, styles["SubtitleCenter"]),
            Spacer(1, 0.4 * inch),
            _table(
                [
                    ["Equipment Model", "ETCH-Z500"],
                    ["Manufacturer", "NanoDyne Systems"],
                    ["Interface", "SEMI E5 SECS-II and SEMI E30 GEM"],
                    ["Host Link", "HSMS-SS active/passive TCP/IP"],
                    ["Release Date", "2026-06-07"],
                ],
                [2.2 * inch, 4.4 * inch],
                font_size=9,
            ),
            PageBreak(),
        ]
    )

    story.extend(
        [
            Paragraph("1. Interface Overview", styles["Chapter"]),
            Paragraph(
                "The ETCH-Z500 is a single-wafer plasma etch platform for dielectric and silicon etch processes. "
                "This document defines the GEM host interface used for equipment monitoring, event collection, "
                "remote operation, alarm handling, and process result reporting.",
                styles["BodyText"],
            ),
            Spacer(1, 0.12 * inch),
            _table(
                [
                    ["Item", "Value"],
                    ["Equipment ID", "ETCH-Z500-01"],
                    ["Default Device ID", "0"],
                    ["T3 Timeout", "45 sec"],
                    ["T5 Timeout", "10 sec"],
                    ["T6 Timeout", "5 sec"],
                    ["T7 Timeout", "10 sec"],
                    ["T8 Timeout", "5 sec"],
                    ["Control States", "OFFLINE, LOCAL, REMOTE"],
                    ["Supported Streams", "S1, S2, S5, S6, S7, S10"],
                ],
                [2.0 * inch, 4.8 * inch],
            ),
            Spacer(1, 0.2 * inch),
            Paragraph("2. Host Communications", styles["Chapter"]),
            Paragraph(
                "The tool supports HSMS single-session operation. The host may establish communications with S1F13/S1F14, "
                "request online state, subscribe reports to collection events, download recipes, and issue remote commands "
                "when the equipment is in REMOTE control.",
                styles["BodyText"],
            ),
            PageBreak(),
        ]
    )

    sv_rows = [
        ["SVID", "Name", "Type", "Unit", "Description"],
        [1001, "SystemStatus", "STRING", "-", "IDLE, PROCESSING, FAULT, MAINTENANCE"],
        [1002, "ControlState", "U1", "-", "GEM control state 1-5"],
        [1003, "ChamberPressure", "FLOAT", "mTorr", "Process chamber pressure"],
        [1004, "ChamberTemperature", "FLOAT", "deg C", "Chamber wall temperature"],
        [1005, "RFPower_Forward", "FLOAT", "W", "Forward RF power to plasma"],
        [1006, "RFPower_Reflected", "FLOAT", "W", "Reflected RF power"],
        [1007, "BiasVoltage", "FLOAT", "V", "DC bias voltage on chuck"],
        [1008, "GasFlow_CF4", "FLOAT", "sccm", "CF4 etch gas flow rate"],
        [1009, "GasFlow_O2", "FLOAT", "sccm", "O2 additive gas flow rate"],
        [1010, "GasFlow_Ar", "FLOAT", "sccm", "Argon carrier gas flow rate"],
        [1011, "WaferPresent", "BOOLEAN", "-", "TRUE if wafer on chuck"],
        [1012, "WaferID", "STRING", "-", "Current wafer ID from OCR"],
        [1013, "EMOStatus", "BOOLEAN", "-", "Emergency Master Off state"],
        [1014, "PumpStatus", "STRING", "-", "Pump state: OFF/STARTING/RUNNING/FAULT"],
    ]
    story.extend(
        [
            Paragraph("3. Status Variables", styles["Chapter"]),
            Paragraph("Status variables are read using S1F3 and reported through linked event reports.", styles["BodyText"]),
            Spacer(1, 0.08 * inch),
            _table(_para_rows(sv_rows, styles), [0.55 * inch, 1.45 * inch, 0.65 * inch, 0.55 * inch, 3.65 * inch]),
            PageBreak(),
        ]
    )

    dv_rows = [
        ["DVID", "Name", "Type", "Unit", "Description"],
        [2001, "RecipeID", "STRING", "-", "Active recipe name"],
        [2002, "LotID", "STRING", "-", "Current lot identifier"],
        [2003, "WaferID_Processed", "STRING", "-", "Wafer ID last processed"],
        [2004, "EtchDepth", "FLOAT", "nm", "Measured etch depth post-process"],
        [2005, "EtchRate", "FLOAT", "nm/min", "Calculated etch rate"],
        [2006, "EtchTime_Actual", "FLOAT", "sec", "Actual elapsed etch duration"],
        [2007, "Uniformity", "FLOAT", "%", "Within-wafer etch uniformity"],
        [2008, "ProcessResult", "STRING", "-", "PASS / FAIL / ABORTED"],
    ]
    story.extend(
        [
            Paragraph("4. Data Variables", styles["Chapter"]),
            _table(_para_rows(dv_rows, styles), [0.55 * inch, 1.45 * inch, 0.65 * inch, 0.65 * inch, 3.55 * inch]),
            Spacer(1, 0.2 * inch),
            Paragraph("5. Event Report Guidance", styles["Chapter"]),
            Paragraph(
                "The host should create one report for process start, one report for process end, and one alarm context report. "
                "Report IDs are host assigned and linked to the CEIDs in section 6 with S2F35/S2F37.",
                styles["BodyText"],
            ),
            PageBreak(),
        ]
    )

    ce_rows = [
        ["CEID", "Name", "Linked VIDs", "Trigger"],
        [3001, "ProcessStart", "1001,1003,1004,2001,2002", "Etch step begins"],
        [3002, "ProcessEnd", "2004,2005,2006,2008", "Etch step ends"],
        [3003, "ProcessAbort", "1001,2008", "Process aborted"],
        [3004, "PlasmaIgnition", "1005,1006", "RF plasma ignited"],
        [3005, "PlasmaExtinguish", "1005", "RF plasma off"],
        [3006, "WaferLoaded", "1011,1012", "Wafer placed on chuck"],
        [3007, "WaferUnloaded", "1011,2008", "Wafer removed from chuck"],
        [3008, "AlarmSet", "1001", "Any alarm became active"],
    ]
    story.extend(
        [
            Paragraph("6. Collection Events", styles["Chapter"]),
            _table(_para_rows(ce_rows, styles), [0.55 * inch, 1.45 * inch, 2.4 * inch, 2.45 * inch]),
            PageBreak(),
        ]
    )

    alarm_rows = [
        ["AlarmID", "Name", "Severity", "Linked SVID", "Description"],
        [4001, "OverPressure", "critical", "1003", "Chamber pressure exceeds limit"],
        [4002, "PlasmaFailure", "critical", "1005,1006", "Plasma failed to ignite"],
        [4003, "EMO_Activated", "critical", "1013", "Emergency stop activated"],
        [4004, "PressureInstability", "warning", "1003", "Pressure fluctuating >5%"],
        [4005, "RF_HighReflection", "warning", "1006", "Reflected power >10% of forward"],
        [4006, "GasFlowDeviation", "warning", "1008", "CF4 flow deviation >5% from setpoint"],
    ]
    rcmd_rows = [
        ["RCMD", "Description", "Parameters"],
        ["START_PROCESS", "Start etch process", "RECIPE_ID, WAFER_ID"],
        ["ABORT_PROCESS", "Abort active process", "-"],
        ["PAUSE_PROCESS", "Pause at end of current step", "-"],
        ["RESUME_PROCESS", "Resume paused process", "-"],
        ["ENTER_MAINTENANCE", "Enter maintenance mode", "-"],
        ["EXIT_MAINTENANCE", "Exit maintenance mode", "-"],
    ]
    story.extend(
        [
            Paragraph("7. Alarms", styles["Chapter"]),
            _table(_para_rows(alarm_rows, styles), [0.65 * inch, 1.35 * inch, 0.8 * inch, 0.8 * inch, 3.25 * inch]),
            Spacer(1, 0.2 * inch),
            Paragraph("8. Remote Commands", styles["Chapter"]),
            _table(_para_rows(rcmd_rows, styles), [1.6 * inch, 3.1 * inch, 2.15 * inch]),
            PageBreak(),
        ]
    )

    state_rows = [
        ["From State", "To State", "Trigger"],
        ["IDLE", "PUMPING", "START_PROCESS accepted"],
        ["PUMPING", "PURGE", "Base pressure reached"],
        ["PURGE", "PROCESSING", "Gas stabilization complete"],
        ["PROCESSING", "COMPLETED", "EtchTime_Actual reached"],
        ["COMPLETED", "IDLE", "WaferUnloaded"],
        ["PROCESSING", "FAULT", "Critical alarm set"],
        ["PURGE", "FAULT", "Pressure control failure"],
        ["FAULT", "IDLE", "Alarm cleared and reset acknowledged"],
    ]
    story.extend(
        [
            Paragraph("9. Equipment State Machine", styles["Chapter"]),
            Paragraph(
                "Nominal process flow is IDLE -> PUMPING -> PURGE -> PROCESSING -> COMPLETED -> IDLE. "
                "FAULT is reachable from PROCESSING and PURGE. Recovery requires operator acknowledgement and host-visible alarm clear.",
                styles["BodyText"],
            ),
            Spacer(1, 0.1 * inch),
            _table(_para_rows(state_rows, styles), [1.5 * inch, 1.5 * inch, 3.85 * inch]),
            Spacer(1, 0.2 * inch),
            Paragraph("10. MES Tag Mapping Notes", styles["Chapter"]),
            Paragraph(
                "Recommended MES tags include ChamberPressure, RFPower_Forward, RFPower_Reflected, RecipeID, "
                "LotID, WaferID_Processed, EtchDepth, EtchRate, Uniformity, ProcessResult, ProcessStart, "
                "ProcessEnd, AlarmSet, OverPressure, PlasmaFailure, and EMO_Activated.",
                styles["BodyText"],
            ),
            PageBreak(),
        ]
    )

    story.extend(
        [
            Paragraph("11. Example SECS/GEM Transactions", styles["Chapter"]),
            _table(
                _para_rows(
                    [
                        ["Scenario", "Primary Message", "Expected Reply"],
                        ["Establish communications", "S1F13", "S1F14 COMMACK=0"],
                        ["Read selected variables", "S1F3 <1003,1005,2001>", "S1F4 with values"],
                        ["Enable collection events", "S2F37 CEED=TRUE", "S2F38 ACKC2=0"],
                        ["Start process", "S2F41 RCMD=START_PROCESS", "S2F42 HCACK=0"],
                        ["Alarm notification", "S5F1 ALID=4001", "S5F2 ACKC5=0"],
                    ],
                    styles,
                ),
                [1.9 * inch, 2.35 * inch, 2.6 * inch],
            ),
            Spacer(1, 0.25 * inch),
            Paragraph("12. Revision History", styles["Chapter"]),
            _table(
                [["Revision", "Date", "Description"], ["A", "2026-06-07", "Initial demo interface specification"]],
                [0.8 * inch, 1.2 * inch, 4.85 * inch],
                font_size=8,
            ),
        ]
    )

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return output_path


if __name__ == "__main__":
    path = build_pdf()
    print(path)
