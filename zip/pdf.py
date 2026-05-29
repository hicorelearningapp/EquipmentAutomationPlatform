"""
generate_cvd_gem_manual.py
==========================
Generates a full SECS/GEM Interface Specification PDF for a CVD Furnace system.
~40 pages, rich variable tables, state machine, message detail, alarm procedures.
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate
from reportlab.lib.units import inch

# ── Colour palette ────────────────────────────────────────────────────────────
NAVY      = colors.HexColor("#0A1628")
DARK_BLUE = colors.HexColor("#1B3A6B")
MID_BLUE  = colors.HexColor("#2E5FA3")
LIGHT_BLUE= colors.HexColor("#D6E4F7")
PALE_GREY = colors.HexColor("#F4F6FA")
BORDER    = colors.HexColor("#B0BDD6")
WHITE     = colors.white
BLACK     = colors.black
RED_DARK  = colors.HexColor("#8B0000")
ORANGE    = colors.HexColor("#C45A00")
GREEN_DARK= colors.HexColor("#1A5C2A")

PAGE_W, PAGE_H = A4
MARGIN = 2.0 * cm

# ── Styles ────────────────────────────────────────────────────────────────────
styles = getSampleStyleSheet()

def S(name, **kw):
    return ParagraphStyle(name, **kw)

TITLE_STYLE   = S("DocTitle",   fontSize=26, textColor=WHITE,  leading=32, alignment=TA_CENTER, fontName="Helvetica-Bold")
SUBTITLE_STYLE= S("DocSub",    fontSize=13, textColor=LIGHT_BLUE, leading=18, alignment=TA_CENTER, fontName="Helvetica")
H1            = S("H1",         fontSize=15, textColor=DARK_BLUE, leading=20, spaceBefore=18, spaceAfter=6,  fontName="Helvetica-Bold", borderPad=4)
H2            = S("H2",         fontSize=12, textColor=MID_BLUE,  leading=16, spaceBefore=12, spaceAfter=4,  fontName="Helvetica-Bold")
H3            = S("H3",         fontSize=10, textColor=DARK_BLUE, leading=14, spaceBefore=8,  spaceAfter=3,  fontName="Helvetica-BoldOblique")
BODY          = S("Body",       fontSize=9,  textColor=BLACK,    leading=13, spaceBefore=3,  spaceAfter=3,  fontName="Helvetica")
BODY_J        = S("BodyJ",      fontSize=9,  textColor=BLACK,    leading=13, spaceBefore=3,  spaceAfter=3,  fontName="Helvetica", alignment=TA_JUSTIFY)
NOTE          = S("Note",       fontSize=8,  textColor=colors.HexColor("#444444"), leading=11, fontName="Helvetica-Oblique", leftIndent=12)
CODE          = S("Code",       fontSize=7.5,textColor=colors.HexColor("#1A1A1A"), leading=11, fontName="Courier", backColor=PALE_GREY, leftIndent=8, rightIndent=8)
TH            = S("TH",         fontSize=8,  textColor=WHITE,    leading=11, fontName="Helvetica-Bold", alignment=TA_CENTER)
TD            = S("TD",         fontSize=8,  textColor=BLACK,    leading=11, fontName="Helvetica")
TD_C          = S("TDC",        fontSize=8,  textColor=BLACK,    leading=11, fontName="Helvetica", alignment=TA_CENTER)
TD_SMALL      = S("TDS",        fontSize=7.5,textColor=BLACK,    leading=10, fontName="Helvetica")
CAPTION       = S("Caption",    fontSize=8,  textColor=MID_BLUE, leading=10, alignment=TA_CENTER, fontName="Helvetica-Oblique", spaceAfter=6)
WARN          = S("Warn",       fontSize=8,  textColor=RED_DARK, leading=11, fontName="Helvetica-Bold")

# ── Table helpers ─────────────────────────────────────────────────────────────

def header_row(cells):
    return [Paragraph(c, TH) for c in cells]

def data_row(cells, style=TD):
    return [Paragraph(str(c), style) for c in cells]

def data_row_mixed(cells):
    """First cell left-aligned, rest centred."""
    out = [Paragraph(str(cells[0]), TD)]
    for c in cells[1:]:
        out.append(Paragraph(str(c), TD_C))
    return out

BASE_TABLE_STYLE = TableStyle([
    ("BACKGROUND",   (0,0), (-1,0), DARK_BLUE),
    ("TEXTCOLOR",    (0,0), (-1,0), WHITE),
    ("ROWBACKGROUNDS",(0,1),(-1,-1),[WHITE, PALE_GREY]),
    ("GRID",         (0,0), (-1,-1), 0.4, BORDER),
    ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
    ("TOPPADDING",   (0,0), (-1,-1), 4),
    ("BOTTOMPADDING",(0,0), (-1,-1), 4),
    ("LEFTPADDING",  (0,0), (-1,-1), 5),
    ("RIGHTPADDING", (0,0), (-1,-1), 5),
])

def make_table(header, rows, col_widths, row_fn=data_row_mixed):
    data = [header_row(header)] + [row_fn(r) for r in rows]
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(BASE_TABLE_STYLE)
    return t

# ── Cover page ────────────────────────────────────────────────────────────────

def cover_page(story):
    story.append(Spacer(1, 3*cm))
    # Coloured title block
    cover_data = [[Paragraph("CVD FURNACE SYSTEM", TITLE_STYLE)],
                  [Paragraph("SECS/GEM Interface Specification", SUBTITLE_STYLE)],
                  [Spacer(1, 0.3*cm)],
                  [Paragraph("Model: CVD-F800 — Dual-Chamber Thermal CVD", SUBTITLE_STYLE)],
                  [Spacer(1, 0.3*cm)],
                  [Paragraph("Document No.: CVD-F800-GEM-ICD-001  |  Revision: C  |  2024-11", SUBTITLE_STYLE)],
                  ]
    cover_tbl = Table(cover_data, colWidths=[PAGE_W - 2*MARGIN])
    cover_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0),(-1,-1), NAVY),
        ("TOPPADDING",  (0,0),(-1,-1), 16),
        ("BOTTOMPADDING",(0,0),(-1,-1), 16),
        ("LEFTPADDING", (0,0),(-1,-1), 20),
        ("RIGHTPADDING",(0,0),(-1,-1), 20),
        ("BOX",         (0,0),(-1,-1), 1.5, MID_BLUE),
    ]))
    story.append(cover_tbl)
    story.append(Spacer(1, 1.5*cm))

    # Meta table
    meta = [
        ["Equipment Type",  "Chemical Vapor Deposition (Thermal CVD)"],
        ["Tool ID",         "CVD-F800-FAB001"],
        ["Manufacturer",    "FabTech Systems Inc."],
        ["Protocol",        "SECS-I / HSMS / SECS-II (SEMI E37)"],
        ["GEM Standard",    "SEMI E30 — Generic Equipment Model"],
        ["Communication",   "HSMS-SS, Active Mode, Port 5018"],
        ["Document Class",  "Interface Control Document (ICD)"],
        ["Approver",        "Systems Integration Group"],
        ["Status",          "Released — Production Use"],
    ]
    mt = Table([[Paragraph(k, H3), Paragraph(v, BODY)] for k,v in meta],
               colWidths=[5*cm, PAGE_W - 2*MARGIN - 5.5*cm])
    mt.setStyle(TableStyle([
        ("ROWBACKGROUNDS",(0,0),(-1,-1),[PALE_GREY, WHITE]),
        ("GRID",(0,0),(-1,-1),0.4,BORDER),
        ("TOPPADDING",(0,0),(-1,-1),5),
        ("BOTTOMPADDING",(0,0),(-1,-1),5),
        ("LEFTPADDING",(0,0),(-1,-1),8),
        ("RIGHTPADDING",(0,0),(-1,-1),8),
    ]))
    story.append(mt)
    story.append(Spacer(1, 1*cm))
    story.append(Paragraph(
        "CONFIDENTIAL — This document contains proprietary information of FabTech Systems Inc. "
        "Distribution is restricted to authorised personnel only.",
        NOTE))
    story.append(PageBreak())

# ── Table of Contents ─────────────────────────────────────────────────────────

def toc_page(story):
    story.append(Paragraph("Table of Contents", H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=MID_BLUE))
    story.append(Spacer(1, 0.4*cm))
    toc = [
        ("Chapter 1", "Introduction", "3"),
        ("  1.1", "Purpose and Scope", "3"),
        ("  1.2", "GEM Compliance Summary", "3"),
        ("  1.3", "Terminology and Abbreviations", "4"),
        ("  1.4", "Referenced Standards", "4"),
        ("Chapter 2", "Equipment Configuration", "5"),
        ("  2.1", "Physical and Electrical Setup", "5"),
        ("  2.2", "HSMS Communication Parameters", "5"),
        ("  2.3", "Device Configuration", "5"),
        ("Chapter 3", "Equipment Identification", "6"),
        ("  3.1", "Tool Identity Block", "6"),
        ("  3.2", "Dual-Chamber Architecture", "6"),
        ("Chapter 4", "Status Variables (SV)", "7"),
        ("  4.1", "Global System Variables", "7"),
        ("  4.2", "Chamber A Variables", "8"),
        ("  4.3", "Chamber B Variables", "9"),
        ("  4.4", "Gas Delivery System Variables", "10"),
        ("  4.5", "RF and Power Variables", "11"),
        ("Chapter 5", "Data Variables (DV)", "12"),
        ("  5.1", "Recipe and Process Variables", "12"),
        ("  5.2", "Metrology and Result Variables", "13"),
        ("Chapter 6", "Collection Events (CEID)", "14"),
        ("  6.1", "Process Lifecycle Events", "14"),
        ("  6.2", "Wafer Handling Events", "15"),
        ("  6.3", "System and Maintenance Events", "15"),
        ("Chapter 7", "Reports (RPTID)", "16"),
        ("  7.1", "Standard Linked Reports", "16"),
        ("  7.2", "Report-Event Link Table", "17"),
        ("Chapter 8", "Alarm Definitions", "18"),
        ("  8.1", "Critical Alarms", "18"),
        ("  8.2", "Warning Alarms", "19"),
        ("  8.3", "Alarm Response Procedures", "19"),
        ("Chapter 9", "Remote Commands (RCMD)", "21"),
        ("  9.1", "Process Control Commands", "21"),
        ("  9.2", "Maintenance Commands", "22"),
        ("Chapter 10", "Equipment State Machine", "23"),
        ("  10.1", "State Definitions", "23"),
        ("  10.2", "Transition Table", "24"),
        ("Chapter 11", "Message Summary", "25"),
        ("  11.1", "Host-to-Equipment Messages", "25"),
        ("  11.2", "Equipment-to-Host Messages", "26"),
        ("Chapter 12", "Message Detail", "27"),
        ("  12.1", "S1 — Equipment Status", "27"),
        ("  12.2", "S2 — Equipment Control", "28"),
        ("  12.3", "S5 — Alarm Management", "29"),
        ("  12.4", "S6 — Data Collection", "30"),
        ("  12.5", "S7 — Process Program Management", "31"),
        ("  12.6", "S9 — System Errors", "32"),
        ("Appendix A", "GEM Compliance Matrix", "33"),
        ("Appendix B", "Variable Cross-Reference Index", "34"),
        ("Appendix C", "Alarm Response Procedures", "35"),
        ("Appendix D", "Operational Scenarios", "36"),
    ]
    toc_data = [[Paragraph(num, BODY), Paragraph(title, BODY),
                 Paragraph(pg, S("pg", fontSize=9, alignment=TA_RIGHT, fontName="Helvetica"))]
                for num, title, pg in toc]
    tt = Table(toc_data, colWidths=[2.5*cm, 11.5*cm, 1.5*cm])
    tt.setStyle(TableStyle([
        ("LINEBELOW",(0,-1),(-1,-1),0.5,BORDER),
        ("TOPPADDING",(0,0),(-1,-1),2),
        ("BOTTOMPADDING",(0,0),(-1,-1),2),
    ]))
    story.append(tt)
    story.append(PageBreak())

# ── Chapter 1 — Introduction ──────────────────────────────────────────────────

def chapter1(story):
    story.append(Paragraph("Chapter 1 — Introduction", H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=MID_BLUE))

    story.append(Paragraph("1.1  Purpose and Scope", H2))
    story.append(Paragraph(
        "This document defines the SECS/GEM host-to-equipment interface for the CVD-F800 "
        "Dual-Chamber Thermal Chemical Vapor Deposition system. It specifies all Status Variables (SV), "
        "Data Variables (DV), Collection Events (CEID), Alarms, Remote Commands (RCMD), Reports (RPTID), "
        "and state machine transitions required for full GEM compliance under SEMI E30. "
        "Host systems integrating this equipment shall use this document as the authoritative reference "
        "for all message exchanges, variable polling, event subscriptions, and alarm management.", BODY_J))

    story.append(Paragraph("1.2  GEM Compliance Summary", H2))
    story.append(Paragraph(
        "The CVD-F800 implements the complete set of required and selected optional GEM capabilities "
        "as listed below. All SEMI E30 mandatory capabilities are implemented.", BODY))

    gem_cap = [
        ["GEM Capability", "Type", "Status", "Notes"],
        ["Establish Communications", "Required", "Implemented", "S1F13/F14"],
        ["Process Program Management", "Required", "Implemented", "S7F3/F5/F25/F27"],
        ["Equipment Self-Description", "Required", "Implemented", "S1F1/F2, S1F3/F4"],
        ["Alarm Management", "Required", "Implemented", "S5F1–F8"],
        ["Event Notification", "Required", "Implemented", "S6F11/F12"],
        ["Online Identification", "Required", "Implemented", "S1F1/F2"],
        ["Error Messages", "Required", "Implemented", "S9Fx"],
        ["Control", "Required", "Implemented", "S2F41/F42"],
        ["Variable Data Collection", "Optional", "Implemented", "S2F23, S6F1–F4"],
        ["Limits Monitoring", "Optional", "Implemented", "S2F45–F48"],
        ["Spooling", "Optional", "Implemented", "S2F43/F44"],
        ["Recipe Management Enhanced", "Optional", "Implemented", "S7F17–F26"],
        ["Equipment Terminal Services", "Optional", "Implemented", "S10F1–F4"],
        ["Clock", "Optional", "Implemented", "S2F17/F18"],
    ]
    t = Table([[Paragraph(c, TH if i==0 else TD) for c in row] if i==0
               else [Paragraph(str(c), TD_C if j>0 else TD) for j,c in enumerate(row)]
               for i, row in enumerate(gem_cap)],
              colWidths=[6*cm, 3*cm, 3*cm, PAGE_W-2*MARGIN-12.5*cm],
              repeatRows=1)
    t.setStyle(BASE_TABLE_STYLE)
    story.append(t)
    story.append(Spacer(1, 0.3*cm))

    story.append(Paragraph("1.3  Terminology and Abbreviations", H2))
    terms = [
        ["Term / Abbreviation", "Definition"],
        ["CEID", "Collection Event ID — numeric identifier for a reportable equipment event"],
        ["DV / DVID", "Data Variable / Data Variable ID — process result or calculated value"],
        ["GEM", "Generic Equipment Model (SEMI E30) — standard behavioural model for equipment"],
        ["HSMS", "High-Speed Message Services (SEMI E37) — TCP/IP transport for SECS-II"],
        ["MFC", "Mass Flow Controller — device controlling gas flow rates"],
        ["RCMD", "Remote Command — host-initiated equipment action"],
        ["RPT / RPTID", "Report / Report ID — a named set of variables linked to a collection event"],
        ["SECS-II", "SEMI Equipment Communications Standard part 2 (SEMI E5) — message format"],
        ["SV / SVID", "Status Variable / Status Variable ID — real-time equipment parameter"],
        ["VID", "Variable ID — generic term for SVID or DVID"],
        ["WIWNU", "Within-Wafer Non-Uniformity — film thickness variation metric"],
        ["LPCVD", "Low-Pressure Chemical Vapor Deposition"],
        ["PECVD", "Plasma-Enhanced Chemical Vapor Deposition"],
        ["MFC", "Mass Flow Controller"],
    ]
    term_tbl = Table([[Paragraph(r[0], TH if i==0 else BODY),
                       Paragraph(r[1], TH if i==0 else BODY)]
                      for i, r in enumerate(terms)],
                     colWidths=[4.5*cm, PAGE_W-2*MARGIN-5*cm], repeatRows=1)
    term_tbl.setStyle(BASE_TABLE_STYLE)
    story.append(term_tbl)

    story.append(Paragraph("1.4  Referenced Standards", H2))
    refs = [
        ["SEMI E5",  "SECS-II: SEMI Equipment Communications Standard part 2"],
        ["SEMI E30", "Generic Equipment Model (GEM)"],
        ["SEMI E37", "High-Speed Message Services (HSMS)"],
        ["SEMI E10", "Metrics for Equipment Performance"],
        ["SEMI E40", "Standard for Processing Management"],
        ["SEMI E58", "Automated Reliability, Availability, and Maintainability (ARAMS)"],
        ["SEMI E116","Equipment Performance Tracking"],
    ]
    rt = Table([[Paragraph(r[0], TD_C), Paragraph(r[1], BODY)] for r in refs],
               colWidths=[2.5*cm, PAGE_W-2*MARGIN-3*cm])
    rt.setStyle(BASE_TABLE_STYLE)
    story.append(rt)
    story.append(PageBreak())

# ── Chapter 2 — Equipment Configuration ──────────────────────────────────────

def chapter2(story):
    story.append(Paragraph("Chapter 2 — Equipment Configuration", H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=MID_BLUE))

    story.append(Paragraph("2.1  Physical and Electrical Setup", H2))
    story.append(Paragraph(
        "The CVD-F800 connects to the host factory network via a dedicated 1 Gbps Ethernet interface. "
        "The equipment controller runs an embedded Linux OS and exposes the SECS/GEM interface through "
        "a single HSMS-SS passive listener. All communication is on VLAN 30 (Equipment Network). "
        "A separate service port (VLAN 50) is reserved for maintenance and is not part of the GEM interface.", BODY_J))

    story.append(Paragraph("2.2  HSMS Communication Parameters", H2))
    hsms = [
        ["Parameter",          "Value",            "Notes"],
        ["Transport",          "HSMS-SS",          "Single Session"],
        ["Mode",               "Passive",          "Equipment listens; host connects"],
        ["IP Address",         "10.30.14.22",      "Static — VLAN 30"],
        ["Port",               "5018",             "Default GEM port assignment"],
        ["T3 Reply Timeout",   "45 s",             "Per SEMI E37"],
        ["T5 Connect Timeout", "10 s",             "Per SEMI E37"],
        ["T6 Control Timeout", "5 s",              "Per SEMI E37"],
        ["T7 Not Selected",    "10 s",             "Per SEMI E37"],
        ["T8 Network Timeout", "5 s",              "Per SEMI E37"],
        ["Max Open Transactions","127",            "Simultaneous outstanding S/F pairs"],
        ["Checksum",           "Disabled",         "HSMS uses TCP integrity"],
    ]
    story.append(make_table(hsms[0], hsms[1:], [5*cm, 4*cm, PAGE_W-2*MARGIN-9.5*cm]))

    story.append(Paragraph("2.3  Device Configuration", H2))
    story.append(Paragraph(
        "The CVD-F800 is configured as a single logical device (DeviceID = 1). "
        "Both process chambers (Chamber A and Chamber B) share one SECS/GEM device ID. "
        "Chamber-specific variables are differentiated by VID range as follows:", BODY))
    dev = [
        ["VID Range",      "Subsystem",                "Description"],
        ["1000 – 1099",    "Global / System",          "Tool-wide status and control variables"],
        ["1100 – 1199",    "Chamber A",                "All process variables for Chamber A"],
        ["1200 – 1299",    "Chamber B",                "All process variables for Chamber B"],
        ["1300 – 1349",    "Gas Delivery System",      "MFC flows, valve states, purge status"],
        ["1350 – 1399",    "RF and Power Systems",     "RF power, bias, impedance matching"],
        ["2000 – 2099",    "Data Variables",           "Recipe parameters and process results"],
        ["3000 – 3099",    "Collection Events",        "Process and system events"],
        ["3100 – 3199",    "Reports (RPTIDs)",         "Named variable sets for event linking"],
        ["4000 – 4099",    "Alarms",                   "Equipment alarm codes"],
        ["5000 – 5099",    "Equipment Constants",      "User-configurable setpoints"],
    ]
    story.append(make_table(dev[0], dev[1:], [3.5*cm, 4.5*cm, PAGE_W-2*MARGIN-8.5*cm]))
    story.append(PageBreak())

# ── Chapter 3 — Equipment Identification ─────────────────────────────────────

def chapter3(story):
    story.append(Paragraph("Chapter 3 — Equipment Identification", H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=MID_BLUE))

    story.append(Paragraph("3.1  Tool Identity Block", H2))
    ident = [
        ["Field",           "Value"],
        ["Tool ID",         "CVD-F800-FAB001"],
        ["Tool Type",       "Thermal CVD Furnace"],
        ["Model",           "CVD-F800"],
        ["Manufacturer",    "FabTech Systems Inc."],
        ["Serial Number",   "FT-CVD-2024-0042"],
        ["Firmware Version","v4.7.3"],
        ["GEM Version",     "SEMI E30-0618"],
        ["Installation Site","Fab-Alpha / Bay 7 / Row C"],
        ["Chamber Count",   "2 (Chamber A and Chamber B — independent process capability)"],
        ["Wafer Diameter",  "300 mm"],
        ["Process Types",   "LPCVD, PECVD, Thermal Oxidation, Nitride Deposition"],
    ]
    it = Table([[Paragraph(r[0], H3), Paragraph(r[1], BODY)] for r in ident],
               colWidths=[4.5*cm, PAGE_W-2*MARGIN-5*cm])
    it.setStyle(TableStyle([
        ("ROWBACKGROUNDS",(0,0),(-1,-1),[PALE_GREY, WHITE]),
        ("GRID",(0,0),(-1,-1),0.4,BORDER),
        ("TOPPADDING",(0,0),(-1,-1),5),
        ("BOTTOMPADDING",(0,0),(-1,-1),5),
        ("LEFTPADDING",(0,0),(-1,-1),8),
        ("RIGHTPADDING",(0,0),(-1,-1),8),
    ]))
    story.append(it)

    story.append(Paragraph("3.2  Dual-Chamber Architecture", H2))
    story.append(Paragraph(
        "The CVD-F800 employs two independently controlled process chambers sharing a common wafer "
        "handling robot and gas delivery manifold. Each chamber has its own temperature controller "
        "(5-zone heater stack), pressure controller, RF generator, and gas injection ring. "
        "Chambers may run different recipes simultaneously. The shared robot services both chambers "
        "and reports its status through the global SV range (VID 1000–1099). "
        "Chamber-specific interlocks ensure that a fault in Chamber A does not abort an active "
        "process in Chamber B unless a shared resource (gas manifold, exhaust) is affected.", BODY_J))
    story.append(PageBreak())

# ── Chapter 4 — Status Variables ─────────────────────────────────────────────

def chapter4(story):
    story.append(Paragraph("Chapter 4 — Status Variables (SV)", H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=MID_BLUE))
    story.append(Paragraph(
        "Status Variables are real-time equipment parameters that the host may read at any time "
        "using S1F3/F4 (request selected equipment status) or S1F5/F6 (request formatted status). "
        "All SVIDs are read-only unless noted otherwise. Values are refreshed by the equipment "
        "controller at the update rates shown.", BODY_J))

    story.append(Paragraph("4.1  Global System Variables (VID 1000–1099)", H2))
    sv_global = [
        ["SVID", "Name",              "Type",   "Unit",  "Range",         "Update Rate", "Description"],
        [1001, "SystemStatus",        "STRING", "—",     "See note",      "1 s",         "Overall equipment status string: IDLE, PROCESSING, FAULT, MAINTENANCE"],
        [1002, "ControlState",        "U1",     "—",     "1–5",           "1 s",         "GEM control state: 1=OFF-LINE, 2=ATTEMPT ON-LINE, 3=HOST INITIATED, 4=EQUIPMENT INITIATED, 5=ON-LINE"],
        [1003, "RobotStatus",         "STRING", "—",     "—",             "1 s",         "Wafer handling robot state: IDLE, TRANSFERRING, FAULT, TEACHING"],
        [1004, "RobotPosition",       "STRING", "—",     "—",             "500 ms",      "Robot end-effector current position: HOME, LOAD_PORT, CHA_INPUT, CHB_INPUT, etc."],
        [1005, "LoadPortStatus_1",    "STRING", "—",     "—",             "500 ms",      "Load port 1 state: EMPTY, CASSETTE_PRESENT, MAPPING, READY"],
        [1006, "LoadPortStatus_2",    "STRING", "—",     "—",             "500 ms",      "Load port 2 state: EMPTY, CASSETTE_PRESENT, MAPPING, READY"],
        [1007, "ActiveWaferCount",    "U2",     "—",     "0–25",          "1 s",         "Total number of wafers currently inside the equipment (both chambers + robot)"],
        [1008, "EquipmentTime",       "STRING", "—",     "ISO 8601",      "1 s",         "Equipment real-time clock in format YYYYMMDDHHmmss"],
        [1009, "PumpStatus",          "STRING", "—",     "—",             "1 s",         "Dry pump and turbopump state: OFF, STARTING, RUNNING, FAULT"],
        [1010, "ExhaustFlowStatus",   "BOOLEAN","—",     "0/1",           "2 s",         "TRUE if exhaust abatement system airflow is within acceptable limits"],
        [1011, "EMOStatus",           "BOOLEAN","—",     "0/1",           "1 s",         "Emergency Master Off state: TRUE = EMO activated"],
        [1012, "MaintenanceMode",     "BOOLEAN","—",     "0/1",           "1 s",         "TRUE if equipment is in a maintenance mode that inhibits normal processing"],
    ]
    story.append(make_table(sv_global[0], sv_global[1:],
        [1.2*cm, 3.5*cm, 1.5*cm, 1.2*cm, 2.5*cm, 2*cm, PAGE_W-2*MARGIN-12.4*cm]))
    story.append(Spacer(1, 0.3*cm))

    story.append(Paragraph("4.2  Chamber A Process Variables (VID 1100–1149)", H2))
    sv_cha = [
        ["SVID", "Name",                    "Type",  "Unit",   "Range",        "Update", "Description"],
        [1101, "ChamberA_Temperature_Zone1","FLOAT", "degC",   "0–1200",       "500 ms", "Temperature of heater Zone 1 (bottom) in Chamber A"],
        [1102, "ChamberA_Temperature_Zone2","FLOAT", "degC",   "0–1200",       "500 ms", "Temperature of heater Zone 2 (lower-mid) in Chamber A"],
        [1103, "ChamberA_Temperature_Zone3","FLOAT", "degC",   "0–1200",       "500 ms", "Temperature of heater Zone 3 (centre) in Chamber A"],
        [1104, "ChamberA_Temperature_Zone4","FLOAT", "degC",   "0–1200",       "500 ms", "Temperature of heater Zone 4 (upper-mid) in Chamber A"],
        [1105, "ChamberA_Temperature_Zone5","FLOAT", "degC",   "0–1200",       "500 ms", "Temperature of heater Zone 5 (top) in Chamber A"],
        [1106, "ChamberA_TempSetpoint",     "FLOAT", "degC",   "0–1200",       "2 s",    "Active recipe temperature setpoint for Chamber A (R/W)"],
        [1107, "ChamberA_Pressure",         "FLOAT", "mTorr",  "0–760000",     "500 ms", "Chamber A process pressure measured by capacitance manometer"],
        [1108, "ChamberA_PressureSetpoint", "FLOAT", "mTorr",  "0–760000",     "2 s",    "Active recipe pressure setpoint for Chamber A (R/W)"],
        [1109, "ChamberA_ProcessState",     "STRING","—",      "—",            "1 s",    "Chamber A sub-state: IDLE, PURGE, RAMP, SOAK, DEPOSIT, COOL, VENT, FAULT"],
        [1110, "ChamberA_WaferPresent",     "BOOLEAN","—",     "0/1",          "500 ms", "TRUE if a wafer is detected on Chamber A susceptor"],
        [1111, "ChamberA_WaferID",          "STRING","—",      "—",            "5 s",    "Wafer ID string read from OCR/barcode of wafer currently in Chamber A"],
        [1112, "ChamberA_RecipeActive",     "STRING","—",      "—",            "5 s",    "Name of the process recipe currently executing in Chamber A"],
        [1113, "ChamberA_CycleCount",       "U4",    "—",      "0–4294967295", "5 s",    "Total process cycle count since last maintenance reset for Chamber A"],
        [1114, "ChamberA_ThrottleValvePos", "FLOAT", "%",      "0–100",        "500 ms", "Throttle valve position (0 = closed, 100 = fully open) for Chamber A pressure control"],
        [1115, "ChamberA_HeaterPower_Avg",  "FLOAT", "W",      "0–30000",      "2 s",    "Average heater power across all 5 zones in Chamber A"],
    ]
    story.append(make_table(sv_cha[0], sv_cha[1:],
        [1.2*cm, 4.5*cm, 1.3*cm, 1.5*cm, 2.5*cm, 1.8*cm, PAGE_W-2*MARGIN-12.8*cm]))
    story.append(Spacer(1, 0.3*cm))

    story.append(Paragraph("4.3  Chamber B Process Variables (VID 1200–1249)", H2))
    story.append(Paragraph(
        "Chamber B exposes an identical set of status variables to Chamber A, "
        "offset by 100 VIDs. The table below is the complete Chamber B SV list.", BODY))
    sv_chb = [
        ["SVID", "Name",                    "Type",  "Unit",   "Range",        "Update", "Description"],
        [1201, "ChamberB_Temperature_Zone1","FLOAT", "degC",   "0–1200",       "500 ms", "Temperature of heater Zone 1 (bottom) in Chamber B"],
        [1202, "ChamberB_Temperature_Zone2","FLOAT", "degC",   "0–1200",       "500 ms", "Temperature of heater Zone 2 (lower-mid) in Chamber B"],
        [1203, "ChamberB_Temperature_Zone3","FLOAT", "degC",   "0–1200",       "500 ms", "Temperature of heater Zone 3 (centre) in Chamber B"],
        [1204, "ChamberB_Temperature_Zone4","FLOAT", "degC",   "0–1200",       "500 ms", "Temperature of heater Zone 4 (upper-mid) in Chamber B"],
        [1205, "ChamberB_Temperature_Zone5","FLOAT", "degC",   "0–1200",       "500 ms", "Temperature of heater Zone 5 (top) in Chamber B"],
        [1206, "ChamberB_TempSetpoint",     "FLOAT", "degC",   "0–1200",       "2 s",    "Active recipe temperature setpoint for Chamber B (R/W)"],
        [1207, "ChamberB_Pressure",         "FLOAT", "mTorr",  "0–760000",     "500 ms", "Chamber B process pressure measured by capacitance manometer"],
        [1208, "ChamberB_PressureSetpoint", "FLOAT", "mTorr",  "0–760000",     "2 s",    "Active recipe pressure setpoint for Chamber B (R/W)"],
        [1209, "ChamberB_ProcessState",     "STRING","—",      "—",            "1 s",    "Chamber B sub-state: IDLE, PURGE, RAMP, SOAK, DEPOSIT, COOL, VENT, FAULT"],
        [1210, "ChamberB_WaferPresent",     "BOOLEAN","—",     "0/1",          "500 ms", "TRUE if a wafer is detected on Chamber B susceptor"],
        [1211, "ChamberB_WaferID",          "STRING","—",      "—",            "5 s",    "Wafer ID string of wafer currently in Chamber B"],
        [1212, "ChamberB_RecipeActive",     "STRING","—",      "—",            "5 s",    "Name of the process recipe currently executing in Chamber B"],
        [1213, "ChamberB_CycleCount",       "U4",    "—",      "0–4294967295", "5 s",    "Total process cycle count since last maintenance reset for Chamber B"],
        [1214, "ChamberB_ThrottleValvePos", "FLOAT", "%",      "0–100",        "500 ms", "Throttle valve position for Chamber B pressure control"],
        [1215, "ChamberB_HeaterPower_Avg",  "FLOAT", "W",      "0–30000",      "2 s",    "Average heater power across all 5 zones in Chamber B"],
    ]
    story.append(make_table(sv_chb[0], sv_chb[1:],
        [1.2*cm, 4.5*cm, 1.3*cm, 1.5*cm, 2.5*cm, 1.8*cm, PAGE_W-2*MARGIN-12.8*cm]))
    story.append(PageBreak())

    story.append(Paragraph("4.4  Gas Delivery System Variables (VID 1300–1349)", H2))
    sv_gas = [
        ["SVID", "Name",                "Type",  "Unit",  "Range",    "Update", "Description"],
        [1301, "MFC1_Flow_SiH4",        "FLOAT", "sccm",  "0–500",    "500 ms", "Silane (SiH4) mass flow controller actual flow rate"],
        [1302, "MFC1_Setpoint_SiH4",    "FLOAT", "sccm",  "0–500",    "2 s",    "Silane MFC flow setpoint (R/W)"],
        [1303, "MFC2_Flow_NH3",         "FLOAT", "sccm",  "0–2000",   "500 ms", "Ammonia (NH3) mass flow controller actual flow rate"],
        [1304, "MFC2_Setpoint_NH3",     "FLOAT", "sccm",  "0–2000",   "2 s",    "Ammonia MFC flow setpoint (R/W)"],
        [1305, "MFC3_Flow_N2O",         "FLOAT", "sccm",  "0–1000",   "500 ms", "Nitrous oxide (N2O) mass flow controller actual flow rate"],
        [1306, "MFC3_Setpoint_N2O",     "FLOAT", "sccm",  "0–1000",   "2 s",    "N2O MFC flow setpoint (R/W)"],
        [1307, "MFC4_Flow_N2",          "FLOAT", "sccm",  "0–5000",   "500 ms", "Nitrogen (N2) purge gas mass flow controller actual flow rate"],
        [1308, "MFC5_Flow_Ar",          "FLOAT", "sccm",  "0–2000",   "500 ms", "Argon (Ar) carrier gas mass flow controller actual flow rate"],
        [1309, "MFC6_Flow_H2",          "FLOAT", "sccm",  "0–1000",   "500 ms", "Hydrogen (H2) mass flow controller actual flow rate — requires H2 safety interlock"],
        [1310, "PurgeValve_A_State",    "BOOLEAN","—",    "0/1",      "1 s",    "TRUE if Chamber A purge valve is open"],
        [1311, "PurgeValve_B_State",    "BOOLEAN","—",    "0/1",      "1 s",    "TRUE if Chamber B purge valve is open"],
        [1312, "ProcessValve_A_State",  "BOOLEAN","—",    "0/1",      "1 s",    "TRUE if Chamber A process gas injection valve is open"],
        [1313, "ProcessValve_B_State",  "BOOLEAN","—",    "0/1",      "1 s",    "TRUE if Chamber B process gas injection valve is open"],
        [1314, "GasCabinet_Pressure",   "FLOAT", "psi",   "0–200",    "2 s",    "Supply pressure reading at gas cabinet outlet manifold"],
        [1315, "GasLeak_Detector",      "BOOLEAN","—",    "0/1",      "1 s",    "TRUE if any gas leak detector in the gas cabinet bay is triggered"],
    ]
    story.append(make_table(sv_gas[0], sv_gas[1:],
        [1.2*cm, 4*cm, 1.3*cm, 1.3*cm, 2*cm, 1.8*cm, PAGE_W-2*MARGIN-11.6*cm]))
    story.append(Spacer(1, 0.3*cm))

    story.append(Paragraph("4.5  RF and Power System Variables (VID 1350–1399)", H2))
    sv_rf = [
        ["SVID", "Name",                "Type",  "Unit",  "Range",    "Update", "Description"],
        [1351, "RF_ForwardPower_A",     "FLOAT", "W",     "0–3000",   "500 ms", "RF generator forward power delivered to Chamber A plasma"],
        [1352, "RF_ReflectedPower_A",   "FLOAT", "W",     "0–500",    "500 ms", "RF reflected power from Chamber A (should be <5% of forward power)"],
        [1353, "RF_Frequency_A",        "FLOAT", "MHz",   "13.56",    "5 s",    "RF generator frequency for Chamber A (fixed at 13.56 MHz for standard recipes)"],
        [1354, "RF_MatchNetwork_A",     "STRING","—",     "—",        "2 s",    "Impedance match network status for Chamber A: IDLE, TUNING, MATCHED, FAULT"],
        [1355, "RF_ForwardPower_B",     "FLOAT", "W",     "0–3000",   "500 ms", "RF generator forward power delivered to Chamber B plasma"],
        [1356, "RF_ReflectedPower_B",   "FLOAT", "W",     "0–500",    "500 ms", "RF reflected power from Chamber B"],
        [1357, "RF_MatchNetwork_B",     "STRING","—",     "—",        "2 s",    "Impedance match network status for Chamber B"],
        [1358, "BiasVoltage_A",         "FLOAT", "V",     "0–1000",   "500 ms", "DC bias voltage on Chamber A susceptor/electrode"],
        [1359, "BiasVoltage_B",         "FLOAT", "V",     "0–1000",   "500 ms", "DC bias voltage on Chamber B susceptor/electrode"],
        [1360, "PowerSupply_24V_Status","BOOLEAN","—",    "0/1",      "2 s",    "TRUE if 24 V DC instrument power supply is within tolerance"],
        [1361, "PowerSupply_48V_Status","BOOLEAN","—",    "0/1",      "2 s",    "TRUE if 48 V DC servo power supply is within tolerance"],
    ]
    story.append(make_table(sv_rf[0], sv_rf[1:],
        [1.2*cm, 4.2*cm, 1.3*cm, 1.3*cm, 2*cm, 1.8*cm, PAGE_W-2*MARGIN-11.8*cm]))
    story.append(PageBreak())

# ── Chapter 5 — Data Variables ────────────────────────────────────────────────

def chapter5(story):
    story.append(Paragraph("Chapter 5 — Data Variables (DV)", H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=MID_BLUE))
    story.append(Paragraph(
        "Data Variables represent process parameters, recipe settings, and metrology results. "
        "They are typically read after a process event (e.g., at ProcessEnd) using S6F1/F2 "
        "or as part of a linked report delivered with S6F11. Unlike Status Variables, DVs "
        "may have undefined values outside of an active process step.", BODY_J))

    story.append(Paragraph("5.1  Recipe and Process Data Variables (VID 2000–2049)", H2))
    dv_recipe = [
        ["DVID", "Name",                    "Type",   "Unit",      "Description"],
        [2001, "RecipeID",                  "STRING", "—",         "Identifier of the active process recipe loaded in the controller"],
        [2002, "RecipeVersion",             "STRING", "—",         "Version string of the active recipe (e.g. '2.1.4')"],
        [2003, "LotID",                     "STRING", "—",         "Lot identifier associated with the current processing batch"],
        [2004, "WaferID_ChamberA",          "STRING", "—",         "Wafer ID of the wafer most recently processed in Chamber A"],
        [2005, "WaferID_ChamberB",          "STRING", "—",         "Wafer ID of the wafer most recently processed in Chamber B"],
        [2006, "SlotNumber",                "U1",     "—",         "Cassette slot number of the wafer being or last processed (1–25)"],
        [2007, "ProcessTemperatureTarget",  "FLOAT",  "degC",      "Recipe-specified process temperature setpoint for the current run"],
        [2008, "ProcessPressureTarget",     "FLOAT",  "mTorr",     "Recipe-specified process pressure setpoint for the current run"],
        [2009, "DepositionTimeTarget",      "FLOAT",  "sec",       "Recipe-specified deposition duration setpoint"],
        [2010, "RFPowerTarget",             "FLOAT",  "W",         "Recipe-specified RF power setpoint for plasma-assisted steps"],
        [2011, "SiH4_FlowTarget",           "FLOAT",  "sccm",      "Recipe-specified silane flow rate setpoint"],
        [2012, "NH3_FlowTarget",            "FLOAT",  "sccm",      "Recipe-specified ammonia flow rate setpoint"],
        [2013, "N2O_FlowTarget",            "FLOAT",  "sccm",      "Recipe-specified nitrous oxide flow rate setpoint"],
        [2014, "N2_PurgeFlowTarget",        "FLOAT",  "sccm",      "Recipe-specified nitrogen purge flow rate setpoint"],
        [2015, "RampRate_Target",           "FLOAT",  "degC/min",  "Recipe-specified temperature ramp rate"],
        [2016, "SoakTime_Target",           "FLOAT",  "sec",       "Recipe-specified temperature soak (stabilisation) duration"],
    ]
    story.append(make_table(dv_recipe[0], dv_recipe[1:],
        [1.2*cm, 4.5*cm, 1.8*cm, 2.5*cm, PAGE_W-2*MARGIN-10*cm]))

    story.append(Paragraph("5.2  Metrology and Process Result Variables (VID 2050–2099)", H2))
    dv_result = [
        ["DVID", "Name",                    "Type",   "Unit",      "Description"],
        [2051, "FilmThickness_Avg",         "FLOAT",  "nm",        "Average film thickness measured across the wafer (post-process)"],
        [2052, "FilmThickness_Min",         "FLOAT",  "nm",        "Minimum film thickness measured at any in-situ monitor point"],
        [2053, "FilmThickness_Max",         "FLOAT",  "nm",        "Maximum film thickness measured at any in-situ monitor point"],
        [2054, "WIWNU",                     "FLOAT",  "%",         "Within-Wafer Non-Uniformity of film thickness (1-sigma)"],
        [2055, "DepositionRate",            "FLOAT",  "nm/min",    "Measured deposition rate calculated from thickness and time"],
        [2056, "ActualDepositionTime",      "FLOAT",  "sec",       "Actual elapsed process time during deposition step"],
        [2057, "ActualTemperature_Avg",     "FLOAT",  "degC",      "Average temperature across all 5 zones during deposition step"],
        [2058, "ActualPressure_Avg",        "FLOAT",  "mTorr",     "Average chamber pressure during deposition step"],
        [2059, "ActualRFPower_Avg",         "FLOAT",  "W",         "Average RF forward power during deposition step"],
        [2060, "RefractivIndex",            "FLOAT",  "—",         "Film refractive index measured by in-situ ellipsometry (if equipped)"],
        [2061, "StressValue",               "FLOAT",  "MPa",       "Film stress value (positive = tensile, negative = compressive)"],
        [2062, "TotalGasConsumed_SiH4",     "FLOAT",  "sccm-min",  "Integrated silane consumption for the completed process run"],
        [2063, "TotalGasConsumed_NH3",      "FLOAT",  "sccm-min",  "Integrated ammonia consumption for the completed process run"],
        [2064, "ProcessResult",             "STRING", "—",         "Overall process outcome: PASS, FAIL, ABORTED, INCOMPLETE"],
        [2065, "AbortReason",               "STRING", "—",         "Plain-text reason for abort (empty string if ProcessResult != ABORTED)"],
        [2066, "ChamberID_Used",            "STRING", "—",         "Which chamber processed this wafer: ChamberA or ChamberB"],
        [2067, "WaferTemperatureUniformity","FLOAT",  "%",         "Wafer surface temperature uniformity measured by pyrometer array"],
    ]
    story.append(make_table(dv_result[0], dv_result[1:],
        [1.2*cm, 4.5*cm, 1.8*cm, 2.5*cm, PAGE_W-2*MARGIN-10*cm]))
    story.append(PageBreak())

# ── Chapter 6 — Collection Events ────────────────────────────────────────────

def chapter6(story):
    story.append(Paragraph("Chapter 6 — Collection Events (CEID)", H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=MID_BLUE))
    story.append(Paragraph(
        "Collection Events are named points in the equipment's process or control flow at which "
        "the equipment notifies the host and delivers a set of associated variable values. "
        "Events are reported via S6F11 (Event Report Send). The host enables event reporting "
        "using S2F37 (Enable/Disable Event Report).", BODY_J))

    story.append(Paragraph("6.1  Process Lifecycle Events (CEID 3001–3029)", H2))
    ev_process = [
        ["CEID", "Event Name",               "Linked VIDs",                  "Trigger Condition"],
        [3001, "ProcessStart_ChamberA",      "1101,1107,2001,2004,2007",     "Deposition step begins in Chamber A"],
        [3002, "ProcessEnd_ChamberA",        "2051,2054,2055,2056,2064",     "Deposition step ends (pass or fail) in Chamber A"],
        [3003, "ProcessAbort_ChamberA",      "2065,2066,1109",               "Process aborted by operator, host, or fault in Chamber A"],
        [3004, "RampStart_ChamberA",         "1101,1102,1103,1104,1105",     "Temperature ramp begins in Chamber A"],
        [3005, "SoakComplete_ChamberA",      "1101,1103,1105,1107",          "Temperature soak period completed within tolerance in Chamber A"],
        [3006, "ProcessStart_ChamberB",      "1201,1207,2001,2005,2007",     "Deposition step begins in Chamber B"],
        [3007, "ProcessEnd_ChamberB",        "2051,2054,2055,2056,2064",     "Deposition step ends (pass or fail) in Chamber B"],
        [3008, "ProcessAbort_ChamberB",      "2065,2066,1209",               "Process aborted in Chamber B"],
        [3009, "RampStart_ChamberB",         "1201,1202,1203,1204,1205",     "Temperature ramp begins in Chamber B"],
        [3010, "SoakComplete_ChamberB",      "1201,1203,1205,1207",          "Temperature soak period completed in Chamber B"],
        [3011, "PurgeStart_ChamberA",        "1307,1310",                    "N2 purge cycle started in Chamber A"],
        [3012, "PurgeComplete_ChamberA",     "1107,1307",                    "N2 purge cycle completed in Chamber A"],
        [3013, "PurgeStart_ChamberB",        "1307,1311",                    "N2 purge cycle started in Chamber B"],
        [3014, "PurgeComplete_ChamberB",     "1207,1307",                    "N2 purge cycle completed in Chamber B"],
        [3015, "PlasmaIgnition_ChamberA",    "1351,1352,1354",               "RF plasma successfully ignited in Chamber A"],
        [3016, "PlasmaExtinguish_ChamberA",  "1351,1354",                    "RF plasma turned off in Chamber A"],
        [3017, "PlasmaIgnition_ChamberB",    "1355,1356,1357",               "RF plasma successfully ignited in Chamber B"],
        [3018, "PlasmaExtinguish_ChamberB",  "1355,1357",                    "RF plasma turned off in Chamber B"],
    ]
    story.append(make_table(ev_process[0], ev_process[1:],
        [1.3*cm, 4.5*cm, 4.5*cm, PAGE_W-2*MARGIN-10.8*cm]))

    story.append(Paragraph("6.2  Wafer Handling Events (CEID 3030–3059)", H2))
    ev_wafer = [
        ["CEID", "Event Name",               "Linked VIDs",       "Trigger Condition"],
        [3031, "WaferLoaded_ChamberA",       "1110,1111,2004",    "Wafer successfully placed on Chamber A susceptor by robot"],
        [3032, "WaferUnloaded_ChamberA",     "1110,2004,2064",    "Wafer removed from Chamber A susceptor by robot after process"],
        [3033, "WaferLoaded_ChamberB",       "1210,1211,2005",    "Wafer successfully placed on Chamber B susceptor by robot"],
        [3034, "WaferUnloaded_ChamberB",     "1210,2005,2064",    "Wafer removed from Chamber B susceptor by robot after process"],
        [3035, "CassetteLoaded_Port1",       "1005,1007",         "Cassette placed and mapped on Load Port 1"],
        [3036, "CassetteUnloaded_Port1",     "1005",              "Cassette removed from Load Port 1"],
        [3037, "CassetteLoaded_Port2",       "1006,1007",         "Cassette placed and mapped on Load Port 2"],
        [3038, "CassetteUnloaded_Port2",     "1006",              "Cassette removed from Load Port 2"],
        [3039, "RobotFault",                 "1003,1004",         "Robot encountered an error during a transfer move"],
        [3040, "SlotMapComplete_Port1",      "1005",              "Wafer slot mapping scan completed on Load Port 1"],
        [3041, "SlotMapComplete_Port2",      "1006",              "Wafer slot mapping scan completed on Load Port 2"],
    ]
    story.append(make_table(ev_wafer[0], ev_wafer[1:],
        [1.3*cm, 4.5*cm, 3.5*cm, PAGE_W-2*MARGIN-9.8*cm]))

    story.append(Paragraph("6.3  System and Maintenance Events (CEID 3060–3099)", H2))
    ev_sys = [
        ["CEID", "Event Name",               "Linked VIDs",       "Trigger Condition"],
        [3061, "ControlStateChange",         "1002",              "GEM control state changed (e.g., OFFLINE to ONLINE)"],
        [3062, "RecipeLoaded",               "2001,2002",         "A new process recipe loaded into the active recipe slot"],
        [3063, "RecipeDeleted",              "2001",              "A process recipe deleted from the equipment controller"],
        [3064, "MaintenanceModeEntered",     "1012",              "Equipment entered maintenance mode (inhibits normal processing)"],
        [3065, "MaintenanceModeExited",      "1012",              "Equipment exited maintenance mode"],
        [3066, "PumpdownStart",              "1009",              "Vacuum pump-down sequence started in either chamber"],
        [3067, "PumpdownComplete",           "1009,1107,1207",    "Chamber pressure reached base vacuum level for processing"],
        [3068, "VentStart",                  "1109",              "Chamber vent sequence started"],
        [3069, "VentComplete",               "1107",              "Chamber reached atmospheric pressure after vent"],
        [3070, "AlarmSet",                   "1001",              "Any alarm condition became active"],
        [3071, "AlarmCleared",               "1001",              "Any alarm condition was cleared"],
        [3072, "EquipmentClockSync",         "1008",              "Equipment real-time clock synchronised with host"],
        [3073, "PreventiveMaintenanceDue",   "1013",              "Scheduled PM interval counter reached threshold"],
    ]
    story.append(make_table(ev_sys[0], ev_sys[1:],
        [1.3*cm, 4.5*cm, 3.5*cm, PAGE_W-2*MARGIN-9.8*cm]))
    story.append(PageBreak())

# ── Chapter 7 — Reports ───────────────────────────────────────────────────────

def chapter7(story):
    story.append(Paragraph("Chapter 7 — Reports (RPTID)", H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=MID_BLUE))
    story.append(Paragraph(
        "Reports define named collections of variables that are delivered to the host when a "
        "linked Collection Event fires. The host configures report-event links using S2F33 "
        "(Define Report) and S2F35 (Link Event Report). Default links are established at "
        "equipment startup and persist until the host redefines them.", BODY_J))

    story.append(Paragraph("7.1  Standard Linked Reports", H2))
    rpts = [
        ["RPTID", "Report Name",             "Linked VIDs",                             "Description"],
        [3101, "RPT_ProcessStart_ChamberA",  "1101,1103,1107,2001,2004,2007,2008",      "Variables captured at process start in Chamber A — recipe, temp, pressure, wafer ID"],
        [3102, "RPT_ProcessEnd_ChamberA",    "2051,2052,2053,2054,2055,2056,2064,2065", "Film metrology and process outcome at end of Chamber A run"],
        [3103, "RPT_ProcessStart_ChamberB",  "1201,1203,1207,2001,2005,2007,2008",      "Variables captured at process start in Chamber B"],
        [3104, "RPT_ProcessEnd_ChamberB",    "2051,2052,2053,2054,2055,2056,2064,2065", "Film metrology and process outcome at end of Chamber B run"],
        [3105, "RPT_WaferLoad",              "1110,1111,2004,1003,1008",                "Wafer ID, robot state, and timestamp at wafer load event"],
        [3106, "RPT_WaferUnload",            "1110,2004,2064,1008",                     "Wafer ID, result, and timestamp at wafer unload event"],
        [3107, "RPT_AlarmEvent",             "1001,1008",                               "Equipment status string and timestamp delivered with every alarm set event"],
        [3108, "RPT_GasStatus",              "1301,1303,1305,1307,1308,1314,1315",      "All MFC actual flows and gas cabinet status — delivered at ProcessStart"],
        [3109, "RPT_RFStatus",               "1351,1352,1354,1355,1356,1357",           "RF forward/reflected power and match status for both chambers"],
        [3110, "RPT_ChamberA_TempProfile",   "1101,1102,1103,1104,1105,1115",           "All 5 zone temperatures and average power — delivered at SoakComplete_ChamberA"],
        [3111, "RPT_ChamberB_TempProfile",   "1201,1202,1203,1204,1205,1215",           "All 5 zone temperatures and average power — delivered at SoakComplete_ChamberB"],
        [3112, "RPT_MaintenanceEvent",       "1012,1013,1008,1002",                     "Maintenance mode status, PM counter, timestamp, control state"],
        [3113, "RPT_ControlStateChange",     "1002,1008",                               "New control state value and timestamp"],
        [3114, "RPT_RecipeManagement",       "2001,2002,1008",                          "Recipe ID, version, and timestamp — delivered at RecipeLoaded or RecipeDeleted"],
        [3115, "RPT_ProcessAbort",           "2065,2066,1109,1209,1008",                "Abort reason, chamber ID, chamber states, and timestamp at abort event"],
    ]
    story.append(make_table(rpts[0], rpts[1:],
        [1.5*cm, 4.5*cm, 5*cm, PAGE_W-2*MARGIN-11*cm]))

    story.append(Paragraph("7.2  Report–Event Link Table", H2))
    story.append(Paragraph(
        "The following table defines the default CEID-to-RPTID links. "
        "The host may redefine these at any time using S2F33/S2F35.", BODY))
    links = [
        ["CEID",  "Event Name",              "RPTID",       "Report Name"],
        [3001, "ProcessStart_ChamberA",      "3101,3108",   "RPT_ProcessStart_ChamberA, RPT_GasStatus"],
        [3002, "ProcessEnd_ChamberA",        "3102",        "RPT_ProcessEnd_ChamberA"],
        [3003, "ProcessAbort_ChamberA",      "3115",        "RPT_ProcessAbort"],
        [3005, "SoakComplete_ChamberA",      "3110",        "RPT_ChamberA_TempProfile"],
        [3006, "ProcessStart_ChamberB",      "3103,3108",   "RPT_ProcessStart_ChamberB, RPT_GasStatus"],
        [3007, "ProcessEnd_ChamberB",        "3104",        "RPT_ProcessEnd_ChamberB"],
        [3008, "ProcessAbort_ChamberB",      "3115",        "RPT_ProcessAbort"],
        [3010, "SoakComplete_ChamberB",      "3111",        "RPT_ChamberB_TempProfile"],
        [3031, "WaferLoaded_ChamberA",       "3105",        "RPT_WaferLoad"],
        [3032, "WaferUnloaded_ChamberA",     "3106",        "RPT_WaferUnload"],
        [3033, "WaferLoaded_ChamberB",       "3105",        "RPT_WaferLoad"],
        [3034, "WaferUnloaded_ChamberB",     "3106",        "RPT_WaferUnload"],
        [3061, "ControlStateChange",         "3113",        "RPT_ControlStateChange"],
        [3062, "RecipeLoaded",               "3114",        "RPT_RecipeManagement"],
        [3064, "MaintenanceModeEntered",     "3112",        "RPT_MaintenanceEvent"],
        [3070, "AlarmSet",                   "3107",        "RPT_AlarmEvent"],
    ]
    story.append(make_table(links[0], links[1:],
        [1.3*cm, 4.5*cm, 2.5*cm, PAGE_W-2*MARGIN-8.8*cm]))
    story.append(PageBreak())

# ── Chapter 8 — Alarms ────────────────────────────────────────────────────────

def chapter8(story):
    story.append(Paragraph("Chapter 8 — Alarm Definitions", H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=MID_BLUE))
    story.append(Paragraph(
        "Alarms are abnormal equipment conditions reported to the host via S5F1 (Alarm Report Send). "
        "Critical alarms result in immediate process abort. Warning alarms are logged and reported "
        "but do not abort the process unless the condition persists beyond the defined tolerance window. "
        "All alarms may be individually enabled or disabled by the host using S5F3.", BODY_J))

    story.append(Paragraph("8.1  Critical Alarms (Severity: CRITICAL)", H2))
    alm_crit = [
        ["Alarm ID", "Name",                      "Code", "Linked SVID",  "Description"],
        [4001, "ChamberA_OverTemperature",        "0x01", "1101–1105",    "Any Chamber A heater zone exceeds 1200 degC (hard limit)"],
        [4002, "ChamberA_PressureOverlimit",      "0x02", "1107",         "Chamber A pressure exceeds process limit by >15% for >5 s"],
        [4003, "ChamberA_PlasmaFailure",          "0x03", "1351,1352",    "RF plasma failed to ignite within 30 s, or extinguished unexpectedly"],
        [4004, "ChamberA_PumpFault",              "0x04", "1009",         "Dry pump or turbopump fault detected on Chamber A roughing line"],
        [4005, "ChamberA_GasLeak",                "0x05", "1315",         "Gas leak detector triggered in Chamber A gas delivery bay"],
        [4006, "ChamberB_OverTemperature",        "0x11", "1201–1205",    "Any Chamber B heater zone exceeds 1200 degC (hard limit)"],
        [4007, "ChamberB_PressureOverlimit",      "0x12", "1207",         "Chamber B pressure exceeds process limit by >15% for >5 s"],
        [4008, "ChamberB_PlasmaFailure",          "0x13", "1355,1356",    "RF plasma failed to ignite or extinguished unexpectedly in Chamber B"],
        [4009, "ChamberB_PumpFault",              "0x14", "1009",         "Dry pump or turbopump fault detected on Chamber B roughing line"],
        [4010, "ChamberB_GasLeak",                "0x15", "1315",         "Gas leak detector triggered in Chamber B gas delivery bay"],
        [4011, "Robot_CollisionFault",            "0x20", "1003",         "Robot detected an obstruction or collision during wafer transfer"],
        [4012, "Robot_WaferDrop",                 "0x21", "1003,1004",    "Wafer drop sensor activated during robot transfer"],
        [4013, "EMO_Activated",                   "0x30", "1011",         "Emergency Master Off button pressed — all processes halted immediately"],
        [4014, "H2_LeakDetected",                 "0x31", "1309,1315",    "Hydrogen (H2) gas leak detected — flammable gas safety interlock"],
        [4015, "PowerFault_MainAC",               "0x32", "1360,1361",    "Main AC power supply phase loss or voltage out of tolerance"],
    ]
    story.append(make_table(alm_crit[0], alm_crit[1:],
        [1.5*cm, 4.5*cm, 1.3*cm, 2.5*cm, PAGE_W-2*MARGIN-9.8*cm]))

    story.append(Paragraph("8.2  Warning Alarms (Severity: WARNING)", H2))
    alm_warn = [
        ["Alarm ID", "Name",                      "Code", "Linked SVID",  "Description"],
        [4051, "ChamberA_TempDeviation_Zone1",    "0x41", "1101",         "Zone 1 temperature deviates >10 degC from setpoint for >60 s"],
        [4052, "ChamberA_TempDeviation_Zone3",    "0x42", "1103",         "Zone 3 (centre) temperature deviation exceeds tolerance"],
        [4053, "ChamberA_PressureInstability",    "0x43", "1107",         "Chamber A pressure fluctuating >5% around setpoint during deposition"],
        [4054, "ChamberA_RF_HighReflection",      "0x44", "1352",         "RF reflected power in Chamber A exceeds 10% of forward power"],
        [4055, "ChamberA_MFC_Deviation_SiH4",     "0x45", "1301",         "SiH4 MFC actual flow deviates >5% from setpoint for >10 s"],
        [4056, "ChamberA_MFC_Deviation_NH3",      "0x46", "1303",         "NH3 MFC actual flow deviates >5% from setpoint for >10 s"],
        [4057, "ChamberB_TempDeviation_Zone3",    "0x51", "1203",         "Chamber B Zone 3 temperature deviation exceeds tolerance"],
        [4058, "ChamberB_PressureInstability",    "0x52", "1207",         "Chamber B pressure fluctuating during deposition"],
        [4059, "ChamberB_RF_HighReflection",      "0x53", "1356",         "RF reflected power in Chamber B exceeds 10% of forward power"],
        [4060, "GasCabinet_LowPressure",          "0x60", "1314",         "Gas supply pressure at cabinet outlet below minimum (50 psi)"],
        [4061, "Robot_SlowResponse",              "0x61", "1003",         "Robot move time exceeded expected duration by >20%"],
        [4062, "PM_CounterThreshold",             "0x70", "1013",         "Preventive maintenance interval counter reached 80% of target"],
        [4063, "WaferCount_Mismatch",             "0x71", "1007",         "Wafer count in equipment does not match host-tracked slot map"],
        [4064, "FilmThickness_OutOfSpec",         "0x80", "2051,2054",    "Post-process measured film thickness outside recipe specification window"],
        [4065, "WIWNU_OutOfSpec",                 "0x81", "2054",         "Within-wafer non-uniformity exceeds recipe specification limit"],
    ]
    story.append(make_table(alm_warn[0], alm_warn[1:],
        [1.5*cm, 4.5*cm, 1.3*cm, 2.5*cm, PAGE_W-2*MARGIN-9.8*cm]))

    story.append(Paragraph("8.3  Alarm Response Procedures", H2))
    story.append(Paragraph(
        "The following table summarises recommended host-side responses to critical alarms. "
        "Detailed step-by-step procedures are provided in Appendix C.", BODY))
    alarm_resp = [
        ["Alarm",                   "Immediate Response",                   "Recovery Action"],
        ["ChamberA/B_OverTemperature", "Send ABORT_PROCESS RCMD. Do not open chamber.", "Wait for cool-down. Check thermocouple wiring. Inspect heater element."],
        ["PlasmaFailure",           "Log alarm, check RF match network status.", "Retry ignition. If 3 consecutive failures: schedule RF generator PM."],
        ["GasLeak / H2_Leak",       "Evacuate zone. Activate facility gas shutoff.", "Do not re-enter until leak confirmed cleared by facilities team."],
        ["EMO_Activated",           "All processes halt automatically.",    "Identify EMO trigger. Clear condition. Perform safety check before restart."],
        ["Robot_CollisionFault",    "Send robot to HOME position.",         "Inspect for obstruction. Check wafer presence sensors."],
    ]
    rt = Table([[Paragraph(r[0], TH if i==0 else BODY),
                 Paragraph(r[1], TH if i==0 else BODY),
                 Paragraph(r[2], TH if i==0 else BODY)]
                for i, r in enumerate(alarm_resp)],
               colWidths=[4*cm, 5.5*cm, PAGE_W-2*MARGIN-10*cm], repeatRows=1)
    rt.setStyle(BASE_TABLE_STYLE)
    story.append(rt)
    story.append(PageBreak())

# ── Chapter 9 — Remote Commands ───────────────────────────────────────────────

def chapter9(story):
    story.append(Paragraph("Chapter 9 — Remote Commands (RCMD)", H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=MID_BLUE))
    story.append(Paragraph(
        "Remote Commands allow the host to initiate equipment actions using S2F41 (Host Command Send). "
        "The equipment acknowledges each command with S2F42. Commands that affect process state will "
        "generate corresponding Collection Events upon completion. Parameters are passed as a list of "
        "CPNAME/CPVAL pairs in the S2F41 body.", BODY_J))

    story.append(Paragraph("9.1  Process Control Commands", H2))
    rcmd_proc = [
        ["RCMD",             "Description",                                  "Parameters",                     "Resulting Event"],
        ["START_PROCESS",    "Begin a process run on specified chamber with named recipe.",
                             "CHAMBER_ID, RECIPE_ID, WAFER_ID",             "ProcessStart_ChamberA/B"],
        ["ABORT_PROCESS",    "Immediately abort the active process on the specified chamber.",
                             "CHAMBER_ID",                                   "ProcessAbort_ChamberA/B"],
        ["PAUSE_PROCESS",    "Pause the process at the end of the current step. Gas flows maintained.",
                             "CHAMBER_ID",                                   "None (status update only)"],
        ["RESUME_PROCESS",   "Resume a paused process from the step it was paused at.",
                             "CHAMBER_ID",                                   "None (status update only)"],
        ["LOAD_RECIPE",      "Load a named recipe from the recipe library into the active slot.",
                             "RECIPE_ID",                                    "RecipeLoaded"],
        ["DELETE_RECIPE",    "Delete a named recipe from the controller recipe library.",
                             "RECIPE_ID",                                    "RecipeDeleted"],
        ["START_PURGE",      "Start a timed N2 purge cycle on the specified chamber.",
                             "CHAMBER_ID, PURGE_DURATION_SEC",              "PurgeStart, PurgeComplete"],
        ["PUMP_DOWN",        "Initiate vacuum pump-down sequence on specified chamber.",
                             "CHAMBER_ID",                                   "PumpdownStart, PumpdownComplete"],
        ["VENT_CHAMBER",     "Vent specified chamber to atmosphere (N2 vent). Requires chamber idle.",
                             "CHAMBER_ID",                                   "VentStart, VentComplete"],
    ]
    story.append(make_table(rcmd_proc[0], rcmd_proc[1:],
        [3.5*cm, 5*cm, 3.5*cm, PAGE_W-2*MARGIN-12*cm]))

    story.append(Paragraph("9.2  Maintenance and Configuration Commands", H2))
    rcmd_maint = [
        ["RCMD",             "Description",                                  "Parameters",              "Resulting Event"],
        ["ENTER_MAINTENANCE","Put equipment into maintenance mode. Inhibits all process starts.",
                             "None",                                         "MaintenanceModeEntered"],
        ["EXIT_MAINTENANCE", "Exit maintenance mode and return equipment to normal operational state.",
                             "None",                                         "MaintenanceModeExited"],
        ["RESET_FAULT",      "Attempt to clear a fault condition and return to IDLE state.",
                             "FAULT_CODE",                                   "None (status update)"],
        ["SET_CLOCK",        "Synchronise equipment real-time clock with host-provided timestamp.",
                             "TIMESTAMP (YYYYMMDDHHmmss)",                  "EquipmentClockSync"],
        ["RESET_PM_COUNTER", "Reset the preventive maintenance cycle counter for a subsystem.",
                             "SUBSYSTEM_ID",                                 "None"],
        ["SET_GAS_FLOW",     "Override MFC setpoint for the specified gas channel.",
                             "GAS_CHANNEL_ID, FLOW_SCCM",                   "None (SV update only)"],
        ["SEND_TERMINAL_MSG","Send a message to the equipment operator terminal display.",
                             "MESSAGE_TEXT (max 256 chars)",                 "None"],
    ]
    story.append(make_table(rcmd_maint[0], rcmd_maint[1:],
        [3.5*cm, 5*cm, 3.5*cm, PAGE_W-2*MARGIN-12*cm]))
    story.append(PageBreak())

# ── Chapter 10 — State Machine ────────────────────────────────────────────────

def chapter10(story):
    story.append(Paragraph("Chapter 10 — Equipment State Machine", H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=MID_BLUE))

    story.append(Paragraph("10.1  State Definitions", H2))
    story.append(Paragraph(
        "Each process chamber maintains an independent sub-state. The global equipment state "
        "is the composite of both chambers. The GEM Control State (SV 1002) is a separate "
        "orthogonal state machine defined by SEMI E30.", BODY_J))
    states = [
        ["State",        "Applies To",     "Description"],
        ["IDLE",         "Chamber A/B",    "Chamber is at atmospheric pressure, at ambient temperature, and ready to accept a new process request."],
        ["PUMPING",      "Chamber A/B",    "Vacuum pump-down in progress. Pressure is decreasing towards base vacuum."],
        ["PURGE",        "Chamber A/B",    "N2 purge gas flowing. Chamber is being cleaned of residual gases prior to process."],
        ["RAMP",         "Chamber A/B",    "Heaters ramping temperature towards the process setpoint at the programmed ramp rate."],
        ["SOAK",         "Chamber A/B",    "Temperature within tolerance of setpoint. Waiting for thermal stabilisation period to expire."],
        ["DEPOSIT",      "Chamber A/B",    "Active deposition step. Process gases flowing, RF on (for PECVD recipes), wafer being processed."],
        ["COOL",         "Chamber A/B",    "Heaters off or set to low temperature. Chamber cooling before wafer unload."],
        ["VENT",         "Chamber A/B",    "N2 vent in progress. Pressure rising to atmospheric for safe wafer unload."],
        ["COMPLETED",    "Chamber A/B",    "Process run finished successfully. Wafer ready for unload by robot."],
        ["FAULT",        "Chamber A/B",    "A critical alarm has stopped the process. Chamber not available until fault is cleared."],
        ["MAINTENANCE",  "Global",         "Equipment-wide maintenance mode. Both chambers inhibited."],
    ]
    story.append(make_table(states[0], states[1:], [3*cm, 3*cm, PAGE_W-2*MARGIN-6.5*cm]))

    story.append(Paragraph("10.2  State Transition Table", H2))
    transitions = [
        ["From State",  "To State",    "Trigger",                               "Chamber"],
        ["IDLE",        "PUMPING",     "START_PROCESS RCMD or PUMP_DOWN RCMD",  "A or B"],
        ["PUMPING",     "PURGE",       "Base vacuum reached (pressure < 10 mTorr)", "A or B"],
        ["PURGE",       "RAMP",        "PurgeComplete event (purge timer expired)", "A or B"],
        ["RAMP",        "SOAK",        "All 5 zones within ±5 degC of setpoint",   "A or B"],
        ["SOAK",        "DEPOSIT",     "SoakComplete event (soak timer expired)",   "A or B"],
        ["DEPOSIT",     "COOL",        "ProcessEnd event (dose timer or endpoint)",  "A or B"],
        ["COOL",        "VENT",        "Chamber temperature < 200 degC (safe threshold)", "A or B"],
        ["VENT",        "COMPLETED",   "Pressure reached atmospheric (>720 Torr)", "A or B"],
        ["COMPLETED",   "IDLE",        "WaferUnloaded event (robot removes wafer)", "A or B"],
        ["DEPOSIT",     "FAULT",       "Any critical alarm (4001–4015)",           "A or B"],
        ["RAMP",        "FAULT",       "Any critical alarm (4001–4015)",           "A or B"],
        ["SOAK",        "FAULT",       "Any critical alarm (4001–4015)",           "A or B"],
        ["ANY",         "IDLE",        "ABORT_PROCESS RCMD followed by RESET_FAULT RCMD", "A or B"],
        ["ANY",         "MAINTENANCE", "ENTER_MAINTENANCE RCMD (from IDLE state only)", "Global"],
        ["MAINTENANCE", "IDLE",        "EXIT_MAINTENANCE RCMD",                   "Global"],
    ]
    story.append(make_table(transitions[0], transitions[1:],
        [3*cm, 3*cm, 6.5*cm, PAGE_W-2*MARGIN-13*cm]))
    story.append(PageBreak())

# ── Chapter 11 — Message Summary ─────────────────────────────────────────────

def chapter11(story):
    story.append(Paragraph("Chapter 11 — Message Summary", H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=MID_BLUE))

    story.append(Paragraph("11.1  Host-to-Equipment Messages", H2))
    h2e = [
        ["Stream/Function", "Message Name",               "Direction",   "Purpose"],
        ["S1F1",  "Are You There Request",                "H→E",         "Connectivity check; equipment replies S1F2"],
        ["S1F3",  "Selected Equipment Status Request",    "H→E",         "Request values for a list of SVIDs"],
        ["S1F5",  "Formatted Status Request",             "H→E",         "Request formatted status (StatusID-based)"],
        ["S1F13", "Establish Communications Request",     "H→E",         "Initiate SECS/GEM session establishment"],
        ["S2F17", "Date and Time Request",                "H→E",         "Request equipment current clock value"],
        ["S2F23", "Trace Initialize Send",                "H→E",         "Configure periodic variable trace collection"],
        ["S2F33", "Define Report",                        "H→E",         "Create or redefine a report (RPTID + VID list)"],
        ["S2F35", "Link Event Report",                    "H→E",         "Link a CEID to one or more RPTIDs"],
        ["S2F37", "Enable/Disable Event Report",          "H→E",         "Enable or disable event reporting for CEIDs"],
        ["S2F41", "Host Command Send",                    "H→E",         "Execute a Remote Command (RCMD)"],
        ["S2F45", "Define Variable Limit Attributes",     "H→E",         "Set upper/lower limits for a variable"],
        ["S2F47", "Variable Limit Attribute Request",     "H→E",         "Query current limit settings for a variable"],
        ["S5F3",  "Enable/Disable Alarm Send",            "H→E",         "Enable or disable specific alarm IDs"],
        ["S5F5",  "List Alarms Request",                  "H→E",         "Request list of all defined alarms and states"],
        ["S7F3",  "Process Program Send",                 "H→E",         "Upload a process recipe to equipment"],
        ["S7F5",  "Process Program Request",              "H→E",         "Download a process recipe from equipment"],
        ["S7F17", "Delete Process Program Send",          "H→E",         "Delete a named recipe from equipment storage"],
        ["S7F19", "Current EPPD Request",                 "H→E",         "Request list of all stored recipe names"],
        ["S7F25", "Enhanced Upload Process Program Send", "H→E",         "Upload recipe with extended parameters (E40)"],
        ["S10F1", "Terminal Request",                     "H→E",         "Display a text message on the operator terminal"],
    ]
    story.append(make_table(h2e[0], h2e[1:],
        [2.5*cm, 5.5*cm, 1.8*cm, PAGE_W-2*MARGIN-9.8*cm]))

    story.append(Paragraph("11.2  Equipment-to-Host Messages", H2))
    e2h = [
        ["Stream/Function", "Message Name",               "Direction",   "Purpose"],
        ["S1F2",  "On-Line Data",                         "E→H",         "Reply to S1F1 — confirms equipment is communicating"],
        ["S1F4",  "Selected Equipment Status Data",       "E→H",         "Returns SVID values requested by S1F3"],
        ["S1F14", "Establish Communications Acknowledge", "E→H",         "Acknowledges S1F13 session establishment"],
        ["S2F18", "Date and Time Data",                   "E→H",         "Returns current equipment clock value"],
        ["S2F42", "Host Command Acknowledge",             "E→H",         "Acknowledge Remote Command; HCACK code in body"],
        ["S2F46", "Variable Limit Attribute Acknowledge", "E→H",         "Confirm limit attribute change"],
        ["S5F1",  "Alarm Report Send",                    "E→H",         "Report an alarm set or cleared condition"],
        ["S5F6",  "List Alarms Data",                     "E→H",         "Return list of all alarms in response to S5F5"],
        ["S6F1",  "Trace Data Send",                      "E→H",         "Periodic trace data for variables set up by S2F23"],
        ["S6F11", "Event Report Send",                    "E→H",         "Report a collection event with linked variable data"],
        ["S6F13", "Annotated Event Report Send",          "E→H",         "Event report with variable names included"],
        ["S7F4",  "Process Program Acknowledge",          "E→H",         "Acknowledge receipt of uploaded recipe"],
        ["S7F6",  "Process Program Data",                 "E→H",         "Return recipe data in response to S7F5"],
        ["S7F20", "Current EPPD Data",                    "E→H",         "Return list of all stored recipe names"],
        ["S9F1",  "Unrecognised Device ID",               "E→H",         "Error: S/F sent with unrecognised device ID"],
        ["S9F3",  "Unrecognised Stream Type",             "E→H",         "Error: unrecognised SECS-II stream number"],
        ["S9F5",  "Unrecognised Function Type",           "E→H",         "Error: unrecognised SECS-II function number"],
        ["S9F7",  "Illegal Data",                         "E→H",         "Error: data in message body was malformed"],
        ["S9F9",  "Transaction Timer Timeout",            "E→H",         "Error: reply to primary message not sent in time"],
        ["S9F11", "Data Too Long",                        "E→H",         "Error: message body exceeded maximum allowed length"],
    ]
    story.append(make_table(e2h[0], e2h[1:],
        [2.5*cm, 5.5*cm, 1.8*cm, PAGE_W-2*MARGIN-9.8*cm]))
    story.append(PageBreak())

# ── Chapter 12 — Message Detail ───────────────────────────────────────────────

def chapter12(story):
    story.append(Paragraph("Chapter 12 — Message Detail", H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=MID_BLUE))

    def msg_block(stream_func, name, direction, body_lines, notes=None):
        story.append(Paragraph(f"{stream_func}  —  {name}", H3))
        meta = Table([[Paragraph("Direction", H3), Paragraph(direction, BODY),
                       Paragraph("Reply Required", H3), Paragraph("Yes" if "W" in direction or True else "No", BODY)]],
                     colWidths=[3*cm, 4*cm, 3.5*cm, PAGE_W-2*MARGIN-11*cm])
        meta.setStyle(TableStyle([("GRID",(0,0),(-1,-1),0.4,BORDER),
                                   ("TOPPADDING",(0,0),(-1,-1),3),("BOTTOMPADDING",(0,0),(-1,-1),3),
                                   ("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6)]))
        story.append(meta)
        for line in body_lines:
            safe_line = line.replace("<", "&lt;").replace(">", "&gt;")
            story.append(Paragraph(safe_line, CODE))
        if notes:
            story.append(Paragraph(f"Note: {notes}", NOTE))
        story.append(Spacer(1, 0.2*cm))

    story.append(Paragraph("12.1  S1 — Equipment Status Messages", H2))
    msg_block("S1F3 W / S1F4", "Selected Equipment Status Request / Data", "H→E / E→H", [
        "S1F3 W",
        "<L [n]",
        "  <U2 SVID_1>",
        "  <U2 SVID_2>",
        "  ...",
        ">",
        "",
        "S1F4",
        "<L [n]",
        "  <item SV_VALUE_1>",
        "  <item SV_VALUE_2>",
        "  ...",
        ">",
    ], "SVID list may be empty (request all SVs). Return types match each variable's declared type.")

    msg_block("S1F13 W / S1F14", "Establish Communications", "H→E / E→H", [
        "S1F13 W",
        "<L [2]",
        "  <A MDLN>       -- Equipment model number",
        "  <A SOFTREV>    -- Software revision string",
        ">",
        "",
        "S1F14",
        "<L [2]",
        "  <B COMMACK>    -- 0x00=Accepted, 0x01=Denied (busy), 0x02=Denied (timeout)",
        "  <L [2]",
        "    <A MDLN>",
        "    <A SOFTREV>",
        "  >",
        ">",
    ], "COMMACK=0x00 indicates session established. Host should subscribe to events after S1F14.")

    story.append(Paragraph("12.2  S2 — Equipment Control Messages", H2))
    msg_block("S2F41 W / S2F42", "Host Command Send / Acknowledge", "H→E / E→H", [
        "S2F41 W",
        "<L [2]",
        "  <A RCMD>                -- Remote command name (e.g. 'START_PROCESS')",
        "  <L [n]                  -- Parameter list",
        "    <L [2]",
        "      <A CPNAME>          -- Parameter name (e.g. 'RECIPE_ID')",
        "      <item CPVAL>        -- Parameter value",
        "    >",
        "    ...",
        "  >",
        ">",
        "",
        "S2F42",
        "<L [2]",
        "  <B HCACK>               -- 0x00=OK, 0x01=Invalid cmd, 0x02=Cannot perform now,",
        "                           -- 0x03=At least 1 param invalid, 0x04=Rejected (safety),",
        "                           -- 0x05=Rejected (operator override required)",
        "  <L [n]                  -- Parameter acknowledge list (mirrors S2F41 params)",
        "    <L [2]",
        "      <A CPNAME>",
        "      <B CPACK>           -- 0x00=OK, 0x01=param name not recognised, 0x02=illegal value",
        "    >",
        "  >",
        ">",
    ])

    msg_block("S2F33 W / S2F34", "Define Report / Acknowledge", "H→E / E→H", [
        "S2F33 W",
        "<L [2]",
        "  <U4 DATAID>             -- Unique transaction identifier",
        "  <L [n]                  -- Report definition list",
        "    <L [2]",
        "      <U4 RPTID>          -- Report identifier (e.g. 3101)",
        "      <L [m]              -- Variable list",
        "        <U2 VID>",
        "        ...",
        "      >",
        "    >",
        "  >",
        ">",
        "",
        "S2F34",
        "<B DRACK>                 -- 0x00=OK, 0x01=Insufficient space, 0x02=Invalid format,",
        "                           -- 0x03=1 or more RPTID already defined, 0x04=1 or more invalid VID",
    ])

    story.append(Paragraph("12.3  S5 — Alarm Management", H2))
    msg_block("S5F1", "Alarm Report Send", "E→H (Primary, no reply required)", [
        "S5F1",
        "<L [3]",
        "  <B ALCD>               -- Bit 7=1: alarm set; Bit 7=0: alarm cleared",
        "                         -- Bits 0–6: alarm code category",
        "  <U4 ALID>              -- Alarm ID (e.g. 4001)",
        "  <A ALTX>               -- Alarm text (human-readable description, max 120 chars)",
        ">",
    ], "ALCD bit 7 distinguishes set (1) from cleared (0). Host should log all S5F1 messages.")

    story.append(Paragraph("12.4  S6 — Data Collection", H2))
    msg_block("S6F11 W / S6F12", "Event Report Send / Acknowledge", "E→H / H→E", [
        "S6F11 W",
        "<L [3]",
        "  <U4 DATAID>            -- Unique transaction ID for this event report",
        "  <U4 CEID>              -- Collection Event ID that triggered this report",
        "  <L [n]                 -- Report list (one per linked RPTID)",
        "    <L [2]",
        "      <U4 RPTID>",
        "      <L [m]             -- Variable values in RPTID's defined order",
        "        <item V1>",
        "        <item V2>",
        "        ...",
        "      >",
        "    >",
        "  >",
        ">",
        "",
        "S6F12",
        "<B ACKC6>               -- 0x00=Accepted, 0x01=Unrecognised DATAID",
    ])

    story.append(Paragraph("12.5  S7 — Process Program Management", H2))
    msg_block("S7F3 W / S7F4", "Process Program Send / Acknowledge", "H→E / E→H", [
        "S7F3 W",
        "<L [2]",
        "  <A PPID>               -- Process Program ID (recipe name string, max 64 chars)",
        "  <A PPBODY>             -- Recipe body (equipment-specific format, base64 if binary)",
        ">",
        "",
        "S7F4",
        "<B ACKC7>               -- 0x00=Accepted, 0x01=PPFormat Error, 0x02=Recipe too long,",
        "                        -- 0x03=Insufficient storage, 0x04=Invalid PPID",
    ])

    story.append(Paragraph("12.6  S9 — System Error Messages", H2))
    msg_block("S9F7", "Illegal Data", "E→H (Primary, no reply)", [
        "S9F7",
        "<L [2]",
        "  <B MHEAD>              -- First 10 bytes of the offending message header",
        "  <B SHEAD>              -- System bytes from the offending message",
        ">",
    ], "Equipment sends S9Fx messages in response to host messages with format errors. Host should log and alert operator.")
    story.append(PageBreak())

# ── Appendices ────────────────────────────────────────────────────────────────

def appendices(story):
    # Appendix A — GEM Compliance Matrix
    story.append(Paragraph("Appendix A — GEM Compliance Matrix", H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=MID_BLUE))
    story.append(Paragraph(
        "The following matrix maps SEMI E30 GEM capability requirements to the implementing "
        "SECS-II stream/function messages on the CVD-F800.", BODY))
    comp = [
        ["E30 Section", "Capability",                   "Type",     "S/F Pairs",            "Status"],
        ["6.1",  "Establish Communications",            "Required", "S1F13/F14",            "Compliant"],
        ["6.2",  "Process Program Management",          "Required", "S7F3/F4, S7F5/F6",     "Compliant"],
        ["6.3",  "Equipment Self-Description",          "Required", "S1F1/F2, S1F3/F4",     "Compliant"],
        ["6.4",  "Control",                             "Required", "S2F41/F42",            "Compliant"],
        ["6.5",  "Alarm Management",                    "Required", "S5F1–F8",              "Compliant"],
        ["6.6",  "Event Notification",                  "Required", "S6F11/F12",            "Compliant"],
        ["6.7",  "Online Identification",               "Required", "S1F1/F2",              "Compliant"],
        ["6.8",  "Error Messages",                      "Required", "S9F1–F11",             "Compliant"],
        ["7.1",  "Variable Data Collection",            "Optional", "S2F23, S6F1–F4",       "Implemented"],
        ["7.2",  "Trace Data Collection",               "Optional", "S2F23, S6F1",          "Implemented"],
        ["7.3",  "Limits Monitoring",                   "Optional", "S2F45–F48",            "Implemented"],
        ["7.4",  "Status Data Collection",              "Optional", "S1F3/F4, S1F5/F6",     "Implemented"],
        ["7.5",  "Recipe Management Enhanced",          "Optional", "S7F17–F26",            "Implemented"],
        ["7.6",  "Spooling",                            "Optional", "S2F43/F44",            "Implemented"],
        ["7.7",  "Clock",                               "Optional", "S2F17/F18",            "Implemented"],
        ["7.8",  "Equipment Terminal Services",         "Optional", "S10F1–F4",             "Implemented"],
        ["7.9",  "Message Acknowledgement Spooling",    "Optional", "—",                    "Not Implemented"],
        ["7.10", "Dynamic Event Configuration",         "Optional", "S2F33/F35/F37",        "Implemented"],
    ]
    story.append(make_table(comp[0], comp[1:],
        [1.8*cm, 5.5*cm, 2.5*cm, 4*cm, PAGE_W-2*MARGIN-13.8*cm]))
    story.append(PageBreak())

    # Appendix B — Variable Cross-Reference Index
    story.append(Paragraph("Appendix B — Variable Cross-Reference Index", H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=MID_BLUE))
    story.append(Paragraph(
        "This index lists all variables alphabetically with their VID and type for quick reference.", BODY))
    xref = [
        ["Variable Name",             "VID",  "Type", "Chapter"],
        ["ActualDepositionTime",       "2056", "DV",   "5"],
        ["ActualPressure_Avg",         "2058", "DV",   "5"],
        ["ActualRFPower_Avg",          "2059", "DV",   "5"],
        ["ActualTemperature_Avg",      "2057", "DV",   "5"],
        ["BiasVoltage_A",              "1358", "SV",   "4"],
        ["BiasVoltage_B",              "1359", "SV",   "4"],
        ["ChamberA_CycleCount",        "1113", "SV",   "4"],
        ["ChamberA_HeaterPower_Avg",   "1115", "SV",   "4"],
        ["ChamberA_Pressure",          "1107", "SV",   "4"],
        ["ChamberA_PressureSetpoint",  "1108", "SV",   "4"],
        ["ChamberA_ProcessState",      "1109", "SV",   "4"],
        ["ChamberA_RecipeActive",      "1112", "SV",   "4"],
        ["ChamberA_TempSetpoint",      "1106", "SV",   "4"],
        ["ChamberA_Temperature_Zone1", "1101", "SV",   "4"],
        ["ChamberA_Temperature_Zone2", "1102", "SV",   "4"],
        ["ChamberA_Temperature_Zone3", "1103", "SV",   "4"],
        ["ChamberA_Temperature_Zone4", "1104", "SV",   "4"],
        ["ChamberA_Temperature_Zone5", "1105", "SV",   "4"],
        ["ChamberA_ThrottleValvePos",  "1114", "SV",   "4"],
        ["ChamberA_WaferID",           "1111", "SV",   "4"],
        ["ChamberA_WaferPresent",      "1110", "SV",   "4"],
        ["ChamberB_CycleCount",        "1213", "SV",   "4"],
        ["ChamberB_Pressure",          "1207", "SV",   "4"],
        ["ChamberB_ProcessState",      "1209", "SV",   "4"],
        ["ChamberB_Temperature_Zone1", "1201", "SV",   "4"],
        ["ChamberB_Temperature_Zone3", "1203", "SV",   "4"],
        ["ChamberB_Temperature_Zone5", "1205", "SV",   "4"],
        ["ChamberB_WaferPresent",      "1210", "SV",   "4"],
        ["ChamberID_Used",             "2066", "DV",   "5"],
        ["ControlState",               "1002", "SV",   "4"],
        ["DepositionRate",             "2055", "DV",   "5"],
        ["DepositionTimeTarget",       "2009", "DV",   "5"],
        ["EMOStatus",                  "1011", "SV",   "4"],
        ["EquipmentTime",              "1008", "SV",   "4"],
        ["FilmThickness_Avg",          "2051", "DV",   "5"],
        ["FilmThickness_Max",          "2053", "DV",   "5"],
        ["FilmThickness_Min",          "2052", "DV",   "5"],
        ["GasCabinet_Pressure",        "1314", "SV",   "4"],
        ["GasLeak_Detector",           "1315", "SV",   "4"],
        ["LotID",                      "2003", "DV",   "5"],
        ["MFC1_Flow_SiH4",             "1301", "SV",   "4"],
        ["MFC2_Flow_NH3",              "1303", "SV",   "4"],
        ["MFC3_Flow_N2O",              "1305", "SV",   "4"],
        ["MFC4_Flow_N2",               "1307", "SV",   "4"],
        ["MFC5_Flow_Ar",               "1308", "SV",   "4"],
        ["MFC6_Flow_H2",               "1309", "SV",   "4"],
        ["ProcessResult",              "2064", "DV",   "5"],
        ["RF_ForwardPower_A",          "1351", "SV",   "4"],
        ["RF_MatchNetwork_A",          "1354", "SV",   "4"],
        ["RF_ReflectedPower_A",        "1352", "SV",   "4"],
        ["RecipeID",                   "2001", "DV",   "5"],
        ["RecipeVersion",              "2002", "DV",   "5"],
        ["RobotPosition",              "1004", "SV",   "4"],
        ["RobotStatus",                "1003", "SV",   "4"],
        ["StressValue",                "2061", "DV",   "5"],
        ["SystemStatus",               "1001", "SV",   "4"],
        ["WIWNU",                      "2054", "DV",   "5"],
        ["WaferID_ChamberA",           "2004", "DV",   "5"],
        ["WaferTemperatureUniformity", "2067", "DV",   "5"],
    ]
    story.append(make_table(xref[0], xref[1:],
        [6*cm, 1.8*cm, 1.5*cm, PAGE_W-2*MARGIN-9.8*cm]))
    story.append(PageBreak())

    # Appendix C — Alarm Response Procedures
    story.append(Paragraph("Appendix C — Alarm Response Procedures (Detailed)", H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=MID_BLUE))
    procedures = [
        ("ALID 4001 / 4006 — Chamber Over-Temperature", [
            "1. Send ABORT_PROCESS RCMD immediately for the affected chamber.",
            "2. Do NOT open the chamber door. Allow natural cool-down with N2 flowing.",
            "3. Monitor SVIDs 1101–1105 (or 1201–1205) until all zones <200 degC.",
            "4. Check thermocouple continuity on the faulted zone.",
            "5. Inspect heater power relay and zone controller for faults.",
            "6. If hardware confirmed healthy, send RESET_FAULT RCMD with FAULT_CODE=0x01.",
            "7. If fault recurs within 3 cycles, schedule preventive maintenance.",
        ]),
        ("ALID 4003 / 4008 — Plasma Failure", [
            "1. Verify process gas flows are within specification (check SVIDs 1301–1308).",
            "2. Check RF generator fault code (accessible via S10 terminal message).",
            "3. Verify chamber pressure is within ignition range (50–500 mTorr).",
            "4. Send START_PROCESS RCMD again (up to 2 automatic retries are allowed).",
            "5. If 3 consecutive ignition failures, lock out the chamber and call RF maintenance.",
        ]),
        ("ALID 4005 / 4010 — Gas Leak Detected", [
            "1. Immediately activate facility gas shutoff valve for the affected gas species.",
            "2. Evacuate all personnel from the gas cabinet bay.",
            "3. Notify facility safety officer before re-entry.",
            "4. Do not send RESET_FAULT until leak source is confirmed cleared by leak detection.",
            "5. Document event in facility safety log.",
        ]),
        ("ALID 4013 — EMO Activated", [
            "1. Identify the cause of the EMO activation before approaching equipment.",
            "2. All in-progress processes are aborted. Wafers in chambers may be at risk.",
            "3. Follow lockout/tagout procedure before any physical inspection.",
            "4. Once safe, perform full equipment integrity check before resetting EMO.",
            "5. Issue RESET_FAULT after safety check is documented and signed off.",
        ]),
    ]
    for title, steps in procedures:
        story.append(Paragraph(title, H3))
        for step in steps:
            story.append(Paragraph(step, BODY))
        story.append(Spacer(1, 0.2*cm))
    story.append(PageBreak())

    # Appendix D — Operational Scenarios
    story.append(Paragraph("Appendix D — Operational Scenarios", H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=MID_BLUE))
    story.append(Paragraph("D.1  Successful Process Run — Chamber A", H2))
    scenario = [
        ["Step", "Direction", "Message",        "Description"],
        ["1",  "H→E", "S1F13 W",        "Host initiates communication session"],
        ["2",  "E→H", "S1F14",          "Equipment acknowledges with COMMACK=0x00"],
        ["3",  "H→E", "S2F33 W",        "Host defines reports RPT_3101 and RPT_3102"],
        ["4",  "E→H", "S2F34",          "DRACK=0x00 (reports defined OK)"],
        ["5",  "H→E", "S2F35 W",        "Host links CEID 3001 -> RPTID 3101, CEID 3002 -> RPTID 3102"],
        ["6",  "E→H", "S2F36",          "LRACK=0x00 (links established)"],
        ["7",  "H→E", "S2F37 W",        "Host enables events 3001, 3002, 3031, 3032"],
        ["8",  "E→H", "S2F38",          "ERACK=0x00 (events enabled)"],
        ["9",  "H→E", "S7F3 W",         "Host uploads recipe NITRIDE_STD_V2"],
        ["10", "E→H", "S7F4",           "ACKC7=0x00 (recipe accepted)"],
        ["11", "H→E", "S2F41 W",        "START_PROCESS: CHAMBER_ID=A, RECIPE_ID=NITRIDE_STD_V2, WAFER_ID=WFR-001"],
        ["12", "E→H", "S2F42",          "HCACK=0x00 (command accepted)"],
        ["13", "E→H", "S6F11 W (3031)", "WaferLoaded_ChamberA event with RPT_WaferLoad"],
        ["14", "H→E", "S6F12",          "ACKC6=0x00"],
        ["15", "E→H", "S6F11 W (3001)", "ProcessStart_ChamberA event with RPT_3101 (temp, pressure, recipe)"],
        ["16", "H→E", "S6F12",          "ACKC6=0x00"],
        ["17", "E→H", "S6F11 W (3002)", "ProcessEnd_ChamberA event with RPT_3102 (thickness, WIWNU, result=PASS)"],
        ["18", "H→E", "S6F12",          "ACKC6=0x00"],
        ["19", "E→H", "S6F11 W (3032)", "WaferUnloaded_ChamberA event with RPT_WaferUnload"],
        ["20", "H→E", "S6F12",          "ACKC6=0x00"],
    ]
    story.append(make_table(scenario[0], scenario[1:],
        [1*cm, 1.8*cm, 3.5*cm, PAGE_W-2*MARGIN-6.8*cm]))

    story.append(Paragraph("D.2  Alarm Handling Scenario", H2))
    alarm_scenario = [
        ["Step", "Direction", "Message",        "Description"],
        ["1",  "E→H", "S5F1",           "Alarm set: ALID=4053 (ChamberA_PressureInstability), ALCD=0x81"],
        ["2",  "E→H", "S6F11 W (3070)", "AlarmSet event with RPT_AlarmEvent (SystemStatus + timestamp)"],
        ["3",  "H→E", "S6F12",          "Host acknowledges alarm event"],
        ["4",  "H→E", "S1F3 W",         "Host polls SVIDs 1107, 1108, 1114 (pressure, setpoint, throttle position)"],
        ["5",  "E→H", "S1F4",           "Returns current values: pressure=482 mTorr (setpoint=450), throttle=78%"],
        ["6",  "H→E", "S2F41 W",        "PAUSE_PROCESS: CHAMBER_ID=A"],
        ["7",  "E→H", "S2F42",          "HCACK=0x00"],
        ["8",  "E→H", "S5F1",           "Alarm cleared: ALID=4053, ALCD=0x01 (pressure stabilised)"],
        ["9",  "H→E", "S2F41 W",        "RESUME_PROCESS: CHAMBER_ID=A"],
        ["10", "E→H", "S2F42",          "HCACK=0x00"],
    ]
    story.append(make_table(alarm_scenario[0], alarm_scenario[1:],
        [1*cm, 1.8*cm, 3.5*cm, PAGE_W-2*MARGIN-6.8*cm]))
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph(
        "End of Document — CVD-F800 SECS/GEM Interface Specification Rev C", NOTE))

# ── Page numbering ────────────────────────────────────────────────────────────

def add_page_number(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#666666"))
    w, h = A4
    canvas.drawString(MARGIN, 1.2*cm,
        f"CVD-F800 SECS/GEM Interface Specification  |  Revision C  |  FabTech Systems Inc.")
    canvas.drawRightString(w - MARGIN, 1.2*cm, f"Page {doc.page}")
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.5)
    canvas.line(MARGIN, 1.5*cm, w - MARGIN, 1.5*cm)
    canvas.restoreState()

# ── Build ─────────────────────────────────────────────────────────────────────

def build_pdf(output_path):
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=2*cm, bottomMargin=2.5*cm,
        title="CVD-F800 SECS/GEM Interface Specification",
        author="FabTech Systems Inc.",
        subject="GEM ICD Rev C",
    )
    story = []
    cover_page(story)
    toc_page(story)
    chapter1(story)
    chapter2(story)
    chapter3(story)
    chapter4(story)
    chapter5(story)
    chapter6(story)
    chapter7(story)
    chapter8(story)
    chapter9(story)
    chapter10(story)
    chapter11(story)
    chapter12(story)
    appendices(story)
    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    print(f"PDF written to {output_path}")

if __name__ == "__main__":
    build_pdf(r"E:\Github\EquipmentAutomationPlatforms\CVD_F800_GEM_Interface_Spec_RevC.pdf")
