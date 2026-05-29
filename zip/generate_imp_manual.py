"""
generate_imp_manual.py
======================
Generates the SECS/GEM User Manual PDF for the IMP-HE2000 Ion Implanter.
Contains cover page, table of contents, 12 chapters, and 3 appendices.
No data tables are included; all tables are referenced to the Excel workbook.
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY

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

TITLE_STYLE   = S("DocTitle",   fontSize=24, textColor=WHITE,  leading=30, alignment=TA_CENTER, fontName="Helvetica-Bold")
SUBTITLE_STYLE= S("DocSub",    fontSize=12, textColor=LIGHT_BLUE, leading=16, alignment=TA_CENTER, fontName="Helvetica")
H1            = S("H1",         fontSize=14, textColor=DARK_BLUE, leading=18, spaceBefore=18, spaceAfter=6,  fontName="Helvetica-Bold")
H2            = S("H2",         fontSize=11, textColor=MID_BLUE,  leading=15, spaceBefore=12, spaceAfter=4,  fontName="Helvetica-Bold")
H3            = S("H3",         fontSize=9.5, textColor=DARK_BLUE, leading=13, spaceBefore=8,  spaceAfter=3,  fontName="Helvetica-BoldOblique")
BODY          = S("Body",       fontSize=9,  textColor=BLACK,    leading=13, spaceBefore=3,  spaceAfter=3,  fontName="Helvetica")
BODY_J        = S("BodyJ",      fontSize=9,  textColor=BLACK,    leading=13, spaceBefore=3,  spaceAfter=3,  fontName="Helvetica", alignment=TA_JUSTIFY)
NOTE          = S("Note",       fontSize=8,  textColor=colors.HexColor("#444444"), leading=11, fontName="Helvetica-Oblique", leftIndent=12)
CODE          = S("Code",       fontSize=7.5,textColor=colors.HexColor("#1A1A1A"), leading=11, fontName="Courier", backColor=PALE_GREY, leftIndent=8, rightIndent=8)
TH            = S("TH",         fontSize=8,  textColor=WHITE,    leading=11, fontName="Helvetica-Bold", alignment=TA_CENTER)
TD            = S("TD",         fontSize=8,  textColor=BLACK,    leading=11, fontName="Helvetica")
TD_C          = S("TDC",        fontSize=8,  textColor=BLACK,    leading=11, fontName="Helvetica", alignment=TA_CENTER)
WARN          = S("Warn",       fontSize=8,  textColor=RED_DARK, leading=11, fontName="Helvetica-Bold")

# ── Cover page ────────────────────────────────────────────────────────────────
def cover_page(story):
    story.append(Spacer(1, 3*cm))
    # Coloured title block
    cover_data = [
        [Paragraph("ION IMPLANTER SYSTEM", TITLE_STYLE)],
        [Paragraph("SECS/GEM User Manual", SUBTITLE_STYLE)],
        [Spacer(1, 0.3*cm)],
        [Paragraph("Model: IMP-HE2000 — High-Energy Medium-Current Ion Implanter", SUBTITLE_STYLE)],
        [Spacer(1, 0.3*cm)],
        [Paragraph("Document No.: IMP-HE2000-GEM-UM-001  |  Revision: A  |  2025-01", SUBTITLE_STYLE)],
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
        ["Equipment Type",  "Ion Implantation (High-Energy Medium-Current)"],
        ["Tool ID",         "IMP-HE2000-FAB002"],
        ["Manufacturer",    "PrecisionBeam Technologies"],
        ["Protocol",        "SECS-I / HSMS / SECS-II (SEMI E37)"],
        ["GEM Standard",    "SEMI E30 — Generic Equipment Model"],
        ["Communication",   "HSMS-SS, Passive Mode, Port 5020"],
        ["Document Class",  "User Manual"],
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
        "CONFIDENTIAL — This document contains proprietary information of PrecisionBeam Technologies. "
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
        ("  1.2", "How to Use This Manual", "3"),
        ("  1.3", "Companion Documents", "3"),
        ("  1.4", "Terminology and Abbreviations", "3"),
        ("  1.5", "Referenced Standards", "4"),
        ("Chapter 2", "Equipment Overview", "5"),
        ("  2.1", "System Architecture", "5"),
        ("  2.2", "Ion Source Subsystem", "5"),
        ("  2.3", "Beamline Subsystem", "5"),
        ("  2.4", "End Station Subsystem", "5"),
        ("  2.5", "Wafer Handling Subsystem", "6"),
        ("  2.6", "Vacuum System", "6"),
        ("  2.7", "High-Voltage System", "6"),
        ("  2.8", "Safety Systems and Interlocks", "6"),
        ("Chapter 3", "Communication Configuration", "7"),
        ("  3.1", "HSMS Communication Parameters", "7"),
        ("  3.2", "Device Configuration and VID Ranges", "7"),
        ("  3.3", "Tool Identity Block", "7"),
        ("Chapter 4", "Status Variables (SV) — Description", "8"),
        ("  4.1", "Global System Variables", "8"),
        ("  4.2", "Ion Source Variables", "8"),
        ("  4.3", "Beamline Variables", "8"),
        ("  4.4", "End Station Variables", "8"),
        ("  4.5", "Wafer Handler Variables", "9"),
        ("  4.6", "Vacuum System Variables", "9"),
        ("  4.7", "High-Voltage and Power Variables", "9"),
        ("Chapter 5", "Data Variables (DV) — Description", "10"),
        ("  5.1", "Recipe and Implant Target Variables", "10"),
        ("  5.2", "Process Result and Metrology Variables", "10"),
        ("Chapter 6", "Collection Events (CEID) — Description", "11"),
        ("  6.1", "Implant Lifecycle Events", "11"),
        ("  6.2", "Beam Tuning Events", "11"),
        ("  6.3", "Wafer Handling Events", "11"),
        ("  6.4", "System and Maintenance Events", "11"),
        ("Chapter 7", "Reports (RPTID) — Description", "12"),
        ("  7.1", "Standard Linked Reports", "12"),
        ("  7.2", "Report–Event Linking", "12"),
        ("Chapter 8", "Alarm Management — Description", "13"),
        ("  8.1", "Critical Alarms", "13"),
        ("  8.2", "Warning Alarms", "13"),
        ("  8.3", "Alarm Response Procedures (Detailed)", "13"),
        ("Chapter 9", "Remote Commands (RCMD) — Description", "14"),
        ("  9.1", "Process Control Commands", "14"),
        ("  9.2", "Beam and Source Commands", "14"),
        ("  9.3", "Maintenance and Configuration Commands", "14"),
        ("Chapter 10", "Equipment State Machine", "15"),
        ("  10.1", "State Definitions", "15"),
        ("  10.2", "Transition Logic", "15"),
        ("  10.3", "GEM Control State Overlay", "15"),
        ("Chapter 11", "SECS-II Message Summary", "16"),
        ("  11.1", "Host-to-Equipment Messages", "16"),
        ("  11.2", "Equipment-to-Host Messages", "16"),
        ("Chapter 12", "SECS-II Message Detail", "17"),
        ("  12.1", "S1 — Equipment Status", "17"),
        ("  12.2", "S2 — Equipment Control", "18"),
        ("  12.3", "S5 — Alarm Management", "19"),
        ("  12.4", "S6 — Data Collection", "20"),
        ("  12.5", "S7 — Process Program Management", "21"),
        ("  12.6", "S9 — System Errors", "22"),
        ("Appendix A", "GEM Compliance Matrix (Prose)", "23"),
        ("Appendix B", "Operational Scenarios (Prose)", "24"),
        ("Appendix C", "Alarm Recovery Procedures (Detailed Step-by-Step)", "25"),
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

    story.append(Paragraph("1.1 Purpose and Scope", H2))
    story.append(Paragraph(
        "This manual describes the operation, architecture, and SECS/GEM host interface "
        "of the IMP-HE2000 High-Energy Medium-Current Ion Implanter manufactured by "
        "PrecisionBeam Technologies. It covers equipment subsystems, process workflows, "
        "state machine behaviour, alarm handling, and remote command capabilities. "
        "For all tabular data — including variable IDs, event codes, alarm definitions, "
        "report structures, and state transitions — refer to the companion workbook: "
        "IMP_HE2000_Variable_Tables.xlsx.", BODY_J))

    story.append(Paragraph("1.2 How to Use This Manual", H2))
    story.append(Paragraph(
        "This manual is the prose companion to the Variable Tables workbook. The manual "
        "explains HOW the equipment works and WHY variables/events/alarms exist. The "
        "workbook provides the WHAT — exact IDs, types, ranges, and linkages. Together "
        "they form the complete SECS/GEM Interface Control Document (ICD).", BODY_J))

    story.append(Paragraph("1.3 Companion Documents", H2))
    story.append(Paragraph(
        "The following companion documents should be read in conjunction with this manual:", BODY))
    story.append(Paragraph(
        "• <b>IMP_HE2000_Variable_Tables.xlsx</b> — All variable, event, alarm, report, and command tables.<br/>"
        "• <b>IMP-HE2000-GEM-ICD-001 Rev A</b> — Combined engineering specification (future release).", BODY))

    story.append(Paragraph("1.4 Terminology and Abbreviations", H2))
    story.append(Paragraph(
        "<b>AMU (Atomic Mass Unit)</b>: The unit of measurement used to specify the mass of ions. "
        "It is critical in mass spectrometry and ion beam mass analysis to ensure only the desired dopant "
        "species is selected and accelerated toward the wafer.<br/><br/>"
        "<b>AsH₃ (Arsine)</b>: A toxic process gas used as a precursor to supply Arsenic (As) ions "
        "for n-type doping of silicon substrates.<br/><br/>"
        "<b>BF₃ (Boron Trifluoride)</b>: A process gas commonly used to supply Boron (B) ions "
        "for p-type doping in semiconductor processing.<br/><br/>"
        "<b>CEID (Collection Event ID)</b>: A unique numeric identifier representing an equipment event "
        "that the host can subscribe to, such as a process step starting, wafer loading, or status transition.<br/><br/>"
        "<b>DV / DVID (Data Variable / Data Variable ID)</b>: A dynamic variable whose value is "
        "updated only during or upon completion of specific events (e.g., post-implant wafer results).<br/><br/>"
        "<b>EC (Equipment Constant)</b>: A user-configurable setpoint or operational parameter "
        "stored in the equipment controller that governs local tool behaviour and can be modified by the host.<br/><br/>"
        "<b>GEM (Generic Equipment Model)</b>: The SEMI E30 standard defining a generic model for "
        "communications and control of manufacturing equipment by a host computer in a semiconductor fab.<br/><br/>"
        "<b>HSMS (High-Speed Message Services)</b>: The SEMI E37 standard defining the TCP/IP-based "
        "transport layer protocol used to transmit SECS-II messages between the equipment and the host.<br/><br/>"
        "<b>keV (kilo-electron-Volt)</b>: A unit of energy representing the kinetic energy gained by an "
        "electron accelerating through a potential difference of one thousand volts. It is the standard unit "
        "for specifying ion beam energy.<br/><br/>"
        "<b>MFC (Mass Flow Controller)</b>: An active device used to precisely measure and control the "
        "flow rate of process gases into the plasma arc chamber of the ion source.<br/><br/>"
        "<b>PH₃ (Phosphine)</b>: A toxic process gas used to supply Phosphorus (P) ions for "
        "n-type doping in silicon wafers.<br/><br/>"
        "<b>RCMD (Remote Command)</b>: A host-initiated instruction sent to the equipment to trigger "
        "a physical or logical change (e.g., START_IMPLANT, ABORT_IMPLANT).<br/><br/>"
        "<b>RPT / RPTID (Report / Report ID)</b>: A grouping of status or data variables defined by "
        "the host and linked to collection events for structured data collection.<br/><br/>"
        "<b>SECS-II (SEMI Equipment Communications Standard 2)</b>: The SEMI E5 standard defining "
        "the message structure and semantic content exchanged between the host and the tool over HSMS.<br/><br/>"
        "<b>SV / SVID (Status Variable / Status Variable ID)</b>: A continuous, real-time status variable "
        "representing equipment parameters that can be read or polled at any time.<br/><br/>"
        "<b>VID (Variable ID)</b>: A generic term referencing any status variable (SVID) or data variable (DVID).", BODY_J))

    story.append(Paragraph("1.5 Referenced Standards", H2))
    story.append(Paragraph(
        "The IMP-HE2000 SECS/GEM interface complies with the following industry standards:<br/>"
        "• <b>SEMI E5</b> — SECS-II Message Content Standard<br/>"
        "• <b>SEMI E30</b> — Generic Equipment Model (GEM) Standard<br/>"
        "• <b>SEMI E37</b> — High-Speed SECS Message Services (HSMS) Standard<br/>"
        "• <b>SEMI E10</b> — Equipment Reliability, Availability, and Maintainability (RAM)<br/>"
        "• <b>SEMI E40</b> — Standard for Processing Management<br/>"
        "• <b>SEMI E90</b> — Standard for Substrate Tracking", BODY))
    story.append(PageBreak())

# ── Chapter 2 — Equipment Overview ────────────────────────────────────────────
def chapter2(story):
    story.append(Paragraph("Chapter 2 — Equipment Overview", H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=MID_BLUE))

    story.append(Paragraph("2.1 System Architecture", H2))
    story.append(Paragraph(
        "The PrecisionBeam IMP-HE2000 is a high-energy, medium-current ion implanter designed "
        "specifically for 300 mm silicon wafer processing in modern semiconductor fabs. "
        "The system consists of seven primary hardware subsystems: the Ion Source, the Beamline, the "
        "End Station, the Wafer Handler, the Vacuum System, the High-Voltage System, and the central "
        "Control System. All subsystems interface directly with the equipment controller, which hosts "
        "the SECS/GEM software stack and manages the factory automation link over HSMS-SS.", BODY_J))

    story.append(Paragraph("2.2 Ion Source Subsystem", H2))
    story.append(Paragraph(
        "The ion source is a Freeman-type hot cathode source designed for high plasma stability. "
        "Precursor gases (BF₃, PH₃, AsH₃, or Ar for setup) are introduced into the arc chamber via "
        "mass flow controllers. A tungsten filament is heated to thermionic emission temperatures, "
        "and an electrical discharge (arc voltage) ignites a dense plasma inside the chamber. An "
        "extraction electrode assembly pulls positive ions from the plasma aperture, forming a "
        "preliminary ion beam. Real-time parameters include arc current, filament current, extraction voltage, "
        "and source gas pressure. The filament and arc chamber have finite lifetimes and require "
        "periodic maintenance, tracked by local timers.", BODY_J))

    story.append(Paragraph("2.3 Beamline Subsystem", H2))
    story.append(Paragraph(
        "The beamline collimates, refines, and accelerates the extracted ion beam. An analyzer magnet "
        "acts as a mass spectrometer, bending the ion path through a 90-degree arc. Since mass deflection "
        "is proportional to charge, only the desired dopant species (e.g., Boron-11) passes through the "
        "resolving aperture, filtering out contaminants and unwanted carrier species. The filtered beam "
        "is then accelerated or decelerated in the high-voltage column to match recipe requirements. "
        "Electrostatic scan plates deflect the beam at high frequencies to create a uniform scanning "
        "ribbon beam. Multi-point Faraday cups measure the beam current to ensure stability and parallelism.", BODY_J))

    story.append(Paragraph("2.4 End Station Subsystem", H2))
    story.append(Paragraph(
        "The end station houses the process chamber where wafers undergo ion implantation under high "
        "vacuum. A wafer is held on an electrostatic chuck (platen) that provides Helium backside cooling "
        "to maintain wafer temperature below critical photoresist degradation levels (typically &lt; 120°C). "
        "The platen tilt and twist mechanisms position the wafer relative to the incoming beam, avoiding "
        "crystal channeling. A Faraday cup array behind the platen measures the actual dose in real-time, "
        "halting the implant when the target dose is achieved.", BODY_J))

    story.append(Paragraph("2.5 Wafer Handling Subsystem", H2))
    story.append(Paragraph(
        "The wafer handler manages wafer transfer between atmospheric and vacuum environments. It features "
        "two FOUP load ports, an atmospheric transfer robot with a slot-mapping sensor, an optical notch "
        "pre-aligner, a vacuum load lock chamber, and a vacuum transfer arm. Wafers are transferred "
        "individually to the process platen, maintaining high vacuum in the process chamber during "
        "lot processing.", BODY_J))

    story.append(Paragraph("2.6 Vacuum System", H2))
    story.append(Paragraph(
        "High-vacuum integrity is vital to prevent ion beam scattering and wafer contamination. The beamline "
        "is evacuated by dual turbomolecular pumps backed by dry scroll pumps. The end station process "
        "chamber uses a cryogenic pump for ultra-high vacuum (~10⁻⁶ Torr). Gate valves isolate the "
        "subsystems, and vacuum gauges continuously monitor pressures across all chambers.", BODY_J))

    story.append(Paragraph("2.7 High-Voltage System", H2))
    story.append(Paragraph(
        "The high-voltage system provides acceleration potentials up to 200 kV inside an insulated terminal. "
        "Terminal voltage, extraction voltage, and suppression power supplies are managed by a dedicated "
        "HV controller. Hardwired interlocks disable high-voltage generation if vacuum thresholds are violated "
        "or access panel switches are tripped.", BODY_J))

    story.append(Paragraph("2.8 Safety Systems and Interlocks", H2))
    story.append(Paragraph(
        "Personnel and equipment safety are maintained through a distributed interlock system. The interlock loop "
        "monitors toxic gas detectors (for Arsine and Phosphine leaks), radiation levels (X-ray monitoring near the "
        "high-voltage column), vacuum pressures, cooling water flow, and the Emergency Master Off (EMO) buttons. "
        "If any safety threshold is exceeded, the beam shutter is immediately closed, and high voltage is tripped.", BODY_J))
    story.append(PageBreak())

# ── Chapter 3 — Communication Configuration ─────────────────────────────────────
def chapter3(story):
    story.append(Paragraph("Chapter 3 — Communication Configuration", H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=MID_BLUE))

    story.append(Paragraph("3.1 HSMS Communication Parameters", H2))
    story.append(Paragraph(
        "The HSMS interface on the IMP-HE2000 operates in Passive mode, meaning the tool listens for an incoming "
        "connection from the factory host. The default TCP port is 5020. Standard timeout parameters "
        "(T3, T5, T6, T7, and T8) are set to SEMI E37 defaults. These values can be modified locally on the tool's "
        "engineering panel or remotely via SECS-II messages.<br/><br/>"
        "Refer to the companion Variable Tables workbook, Sheet <b>'HSMS Parameters'</b>, for the complete list "
        "of network settings, IP addresses, port configuration, and timeout limits.", BODY_J))

    story.append(Paragraph("3.2 Device Configuration and VID Ranges", H2))
    story.append(Paragraph(
        "The IMP-HE2000 is represented as a single logical SECS-II device with DeviceID = 1. To organize the "
        "large number of variables, events, and alarms, VIDs are partitioned into distinct ranges based on "
        "subsystem and variable type. For instance, Global System Variables occupy VIDs 1000–1049, Ion Source "
        "Variables occupy 1050–1099, and Data Variables are assigned to the 2000+ range.<br/><br/>"
        "Refer to the companion Variable Tables workbook, Sheet <b>'VID Range Map'</b>, for the complete partitioning "
        "table and subsystem allocations.", BODY_J))

    story.append(Paragraph("3.3 Tool Identity Block", H2))
    story.append(Paragraph(
        "The tool maintains static hardware and firmware configuration details in its non-volatile memory. "
        "This identity block contains parameters such as the unique Tool ID, serial number, firmware revision, "
        "and physical limits (e.g., energy and current range). These parameters can be queried by the host "
        "during initial online handshaking.<br/><br/>"
        "Refer to the companion Variable Tables workbook, Sheet <b>'Tool Identity'</b>, for the detailed equipment "
        "metadata and version strings.", BODY_J))
    story.append(PageBreak())

# ── Chapter 4 — Status Variables ─────────────────────────────────────────────
def chapter4(story):
    story.append(Paragraph("Chapter 4 — Status Variables (SV) — Description", H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=MID_BLUE))
    story.append(Paragraph(
        "Status Variables (SVs) represent continuously updated, real-time parameters monitored by the IMP-HE2000 "
        "control computer. The host can poll these variables at any time using S1F3/F4 messages or include them "
        "in periodic trace definitions (S2F23) or linked event reports (S2F35).", BODY_J))

    story.append(Paragraph("4.1 Global System Variables", H2))
    story.append(Paragraph(
        "Global variables track tool-wide states, GEM control states, and system-wide safety interlocks. These variables "
        "help the host verify the current operating mode (e.g., IDLE, IMPLANTING) and ensure safety conditions are met "
        "before starting a run.<br/><br/>"
        "Refer to the companion Variable Tables workbook, Sheet <b>'SV - Global System'</b>, for the complete list of "
        "global variables, including SystemStatus, ControlState, and EMOStatus.", BODY_J))

    story.append(Paragraph("4.2 Ion Source Variables", H2))
    story.append(Paragraph(
        "Ion source variables monitor the health and discharge characteristics of the Freeman plasma source. Parameters "
        "include arc current, filament current, filament voltage, extraction voltage, gas flow rate, and gas species. "
        "These values are refreshed every 500 ms.<br/><br/>"
        "Refer to the companion Variable Tables workbook, Sheet <b>'SV - Ion Source'</b>, for all source-related SVs.", BODY_J))

    story.append(Paragraph("4.3 Beamline Variables", H2))
    story.append(Paragraph(
        "Beamline variables monitor ion beam transport and beam qualities, such as mass analyzer coil current, beam energy, "
        "resolved Faraday cup current, electrostatic scan frequencies, spot sizes, and beam parallelism. These are critical "
        "to verify that the ion beam is properly tuned and aligned before implanting the wafer.<br/><br/>"
        "Refer to the companion Variable Tables workbook, Sheet <b>'SV - Beamline'</b>, for the beamline variables list.", BODY_J))

    story.append(Paragraph("4.4 End Station Variables", H2))
    story.append(Paragraph(
        "End station variables track process chamber parameters during implantation, including platen tilt/twist angles, "
        "wafer clamp status, backside helium cooling flow, and real-time dose accumulation. Fast updates (200 ms) are provided "
        "for critical dose and beam current parameters.<br/><br/>"
        "Refer to the companion Variable Tables workbook, Sheet <b>'SV - End Station'</b>, for end station SV details.", BODY_J))

    story.append(Paragraph("4.5 Wafer Handler Variables", H2))
    story.append(Paragraph(
        "Wafer handler variables track the robot state, robot end-effector positions, load lock chamber pressure, load lock "
        "pump/vent states, pre-aligner notch angle, and FOUP wafer mapping counts.<br/><br/>"
        "Refer to the companion Variable Tables workbook, Sheet <b>'SV - Wafer Handler'</b>, for handling SVs.", BODY_J))

    story.append(Paragraph("4.6 Vacuum System Variables", H2))
    story.append(Paragraph(
        "Vacuum system variables monitor pressures in the beamline, process chamber, and source chamber, as well as turbomolecular "
        "pump speeds, cryopump cold-head temperature, and isolation gate valve positions.<br/><br/>"
        "Refer to the companion Variable Tables workbook, Sheet <b>'SV - Vacuum System'</b>, for vacuum SVs.", BODY_J))

    story.append(Paragraph("4.7 High-Voltage and Power Variables", H2))
    story.append(Paragraph(
        "High-voltage variables monitor terminal acceleration voltage, suppression voltage, extraction voltage, and power supply "
        "status. Host software should verify that terminal voltage matches recipe targets prior to beam-on commands.<br/><br/>"
        "Refer to the companion Variable Tables workbook, Sheet <b>'SV - High Voltage and Power'</b>, for high-voltage and "
        "power status variables.", BODY_J))
    story.append(PageBreak())

# ── Chapter 5 — Data Variables ────────────────────────────────────────────────
def chapter5(story):
    story.append(Paragraph("Chapter 5 — Data Variables (DV) — Description", H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=MID_BLUE))
    story.append(Paragraph(
        "Data Variables (DVs) differ from Status Variables in that their values are event-dependent. They represent "
        "process setup targets and post-process results (such as lot ID, recipe settings, measured dose, uniformity, "
        "and particle counts). These values are updated at specific event triggers (like ImplantStart and ImplantEnd) "
        "and are typically read by the host inside linked reports rather than polled during idle periods.", BODY_J))

    story.append(Paragraph("5.1 Recipe and Implant Target Variables", H2))
    story.append(Paragraph(
        "These variables capture the target process parameters defined in the active recipe, including the Target Species, "
        "Target Energy, Target Dose, and Target Platen Tilt/Twist angles. They are updated when a recipe is loaded "
        "or an implant run starts.<br/><br/>"
        "Refer to the companion Variable Tables workbook, Sheet <b>'DV - Recipe and Implant Targets'</b>, for recipe DVs.", BODY_J))

    story.append(Paragraph("5.2 Process Result and Metrology Variables", H2))
    story.append(Paragraph(
        "Post-process variables contain metrology and quality assurance results for the most recently processed wafer, "
        "such as actual dose delivered, measured dose uniformity, average beam current, implant duration, maximum wafer temperature, "
        "ellipsometry results, and the process outcome (PASS/FAIL). These variables are updated when the wafer processing "
        "ends or is aborted.<br/><br/>"
        "Refer to the companion Variable Tables workbook, Sheet <b>'DV - Process Results'</b>, for results and metrology DVs.", BODY_J))
    story.append(PageBreak())

# ── Chapter 6 — Collection Events ────────────────────────────────────────────
def chapter6(story):
    story.append(Paragraph("Chapter 6 — Collection Events (CEID) — Description", H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=MID_BLUE))
    story.append(Paragraph(
        "Collection Events (CEIDs) represent milestones in the equipment's physical and logical workflow. "
        "When an event occurs, the equipment sends an S6F11 Event Report message containing linked reports to the host. "
        "The host can dynamically enable or disable reporting for individual event IDs using the S2F37 message.", BODY_J))

    story.append(Paragraph("6.1 Implant Lifecycle Events", H2))
    story.append(Paragraph(
        "Implant lifecycle events track progress during wafer processing. The primary lifecycle events are "
        "ImplantStart, ImplantEnd, and ImplantAbort. These events allow the host to track processing times and receive "
        "detailed post-implant results immediately after a wafer is processed.", BODY_J))

    story.append(Paragraph("6.2 Beam Tuning Events", H2))
    story.append(Paragraph(
        "Beam tuning events notify the host of beam preparation progress. They include BeamTuneStart, BeamTuneComplete, "
        "BeamLost, SourceIgnition, SourceExtinguish, and SourceFault. These events help the host monitor source stability "
        "and track beam setup durations.", BODY_J))

    story.append(Paragraph("6.3 Wafer Handling Events", H2))
    story.append(Paragraph(
        "Handling events track wafer and FOUP movements. Key events include WaferLoaded_EndStation, WaferUnloaded_EndStation, "
        "WaferPrealigned, FOUPLoaded_Port1/2, FOUPUnloaded_Port1/2, LoadLockPumpDown, LoadLockVacuumReached, and LoadLockVent. "
        "These events allow tracking of wafer locations within the tool.", BODY_J))

    story.append(Paragraph("6.4 System and Maintenance Events", H2))
    story.append(Paragraph(
        "System events track state changes and maintenance intervals. They include ControlStateChange, RecipeLoaded, "
        "RecipeDeleted, MaintenanceModeEntered/Exited, HV_Enabled/Disabled, AlarmSet/Cleared, and PMDue_Source/Beamline. "
        "These events alert the host to configuration changes and required maintenance actions.<br/><br/>"
        "Refer to the companion Variable Tables workbook, Sheet <b>'Collection Events'</b>, for the complete list of "
        "CEIDs, linked variables, and trigger conditions.", BODY_J))
    story.append(PageBreak())

# ── Chapter 7 — Reports ───────────────────────────────────────────────────────
def chapter7(story):
    story.append(Paragraph("Chapter 7 — Reports (RPTID) — Description", H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=MID_BLUE))
    story.append(Paragraph(
        "Reports (RPTIDs) are host-defined or factory-default structures that group multiple variables. "
        "By linking reports to events, the host receives only the relevant parameters when an event occurs, "
        "minimising network traffic and processing overhead. Report definition is managed via S2F33, "
        "and linking is performed via S2F35.", BODY_J))

    story.append(Paragraph("7.1 Standard Linked Reports", H2))
    story.append(Paragraph(
        "The IMP-HE2000 defines 14 standard reports, including RPT_ImplantStart, RPT_ImplantEnd, RPT_BeamStatus, "
        "RPT_WaferLoad, RPT_AlarmEvent, RPT_SourceStatus, and RPT_VacuumStatus. These reports group relevant status "
        "and data variables to provide a complete status update at the moment an event is triggered.<br/><br/>"
        "Refer to the companion Variable Tables workbook, Sheet <b>'Reports'</b>, for details of all default reports "
        "and their variables.", BODY_J))

    story.append(Paragraph("7.2 Report–Event Linking", H2))
    story.append(Paragraph(
        "The equipment controller maintains a default linking configuration to provide standard GEM reports out-of-the-box. "
        "For example, the ImplantStart event is linked to RPT_ImplantStart and RPT_BeamStatus, ensuring the host receives "
        "both process targets and beam parameters at start.<br/><br/>"
        "Refer to the companion Variable Tables workbook, Sheet <b>'Report-Event Links'</b>, for the default "
        "links table.", BODY_J))
    story.append(PageBreak())

# ── Chapter 8 — Alarm Management ─────────────────────────────────────────────
def chapter8(story):
    story.append(Paragraph("Chapter 8 — Alarm Management — Description", H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=MID_BLUE))
    story.append(Paragraph(
        "Alarms are generated when an operational parameter exceeds safe limits or a hardware failure is detected. "
        "Alarms are reported to the host immediately via S5F1 messages. In addition, an AlarmSet event is triggered, "
        "allowing the host to receive a linked report with system status details. Host control systems should monitor "
        "alarms to interlock factory automation tasks.", BODY_J))

    story.append(Paragraph("8.1 Critical Alarms", H2))
    story.append(Paragraph(
        "Critical Alarms represent severe faults that cause an immediate process abort, close the beam shutter, and "
        "trip high voltage. Examples include Source_ArcFault, Source_GasLeak, Beam_EnergyContamination, EndStn_DoseOverrun, "
        "HV_ArcOver, Vacuum leaks, and EMO activation.<br/><br/>"
        "Refer to the companion Variable Tables workbook, Sheet <b>'Alarms - Critical'</b>, for the complete list of "
        "critical alarms, codes, and linked SVIDs.", BODY_J))

    story.append(Paragraph("8.2 Warning Alarms", H2))
    story.append(Paragraph(
        "Warning Alarms notify the operator of degraded performance or upcoming maintenance needs without aborting "
        "the active process. Examples include Source_FilamentDegraded, Beam_CurrentInstability, EndStn_CoolantFlowLow, "
        "cryopump temperature drift, and pending PM counters.<br/><br/>"
        "Refer to the companion Variable Tables workbook, Sheet <b>'Alarms - Warning'</b>, for all warning alarms.", BODY_J))

    story.append(Paragraph("8.3 Alarm Response Procedures (Detailed)", H2))
    story.append(Paragraph(
        "When an alarm is received by the host, the factory control system should log the Alarm ID and text, "
        "check linked variables (e.g., pressure or temperature SVIDs) to assess severity, and notify the operator. "
        "Critical alarms require manual operator investigation, hardware repair (if needed), and a RESET_FAULT command "
        "to clear the error state. Step-by-step recovery details are provided in Appendix C.", BODY_J))
    story.append(PageBreak())

# ── Chapter 9 — Remote Commands ─────────────────────────────────────────────
def chapter9(story):
    story.append(Paragraph("Chapter 9 — Remote Commands (RCMD) — Description", H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=MID_BLUE))
    story.append(Paragraph(
        "Remote Commands allow the host to control equipment operations using S2F41 messages. Commands can include "
        "parameters (e.g., recipe name, wafer ID) passed as CPNAME/CPVAL pairs. The equipment replies with S2F42 "
        "containing the HCACK code indicating acceptance or rejection.", BODY_J))

    story.append(Paragraph("9.1 Process Control Commands", H2))
    story.append(Paragraph(
        "Process control commands manage the implant run. They include START_IMPLANT (starts the run with specified "
        "RECIPE_ID and WAFER_ID parameters), ABORT_IMPLANT (aborts the run immediately), PAUSE_IMPLANT, and RESUME_IMPLANT. "
        "These commands allow full automated operation of wafer lots.", BODY_J))

    story.append(Paragraph("9.2 Beam and Source Commands", H2))
    story.append(Paragraph(
        "These commands manage beam preparation, including TUNE_BEAM (initiates tuning for species and energy setpoints), "
        "SOURCE_ON (ignites source plasma with specified gas), SOURCE_OFF, HV_ON, and HV_OFF. These allow the host to "
        "prepare the tool prior to starting a process lot.", BODY_J))

    story.append(Paragraph("9.3 Maintenance and Configuration Commands", H2))
    story.append(Paragraph(
        "Maintenance commands assist with calibration and troubleshooting. They include LOAD_RECIPE, DELETE_RECIPE, "
        "ENTER_MAINTENANCE, EXIT_MAINTENANCE, RESET_FAULT (clears fault state to IDLE), SET_CLOCK, RESET_PM_COUNTER, "
        "PUMP_DOWN_LOADLOCK, and VENT_LOADLOCK.<br/><br/>"
        "Refer to the companion Variable Tables workbook, Sheet <b>'Remote Commands'</b>, for all command names, "
        "parameter requirements, and resulting events.", BODY_J))
    story.append(PageBreak())

# ── Chapter 10 — State Machine ────────────────────────────────────────────────
def chapter10(story):
    story.append(Paragraph("Chapter 10 — Equipment State Machine", H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=MID_BLUE))

    story.append(Paragraph("10.1 State Definitions", H2))
    story.append(Paragraph(
        "The IMP-HE2000 process state machine represents the physical status of the implanter. The primary states "
        "are: IDLE (ready to accept commands), SETTING_UP (recipe loaded, source warming, beam tuning active), "
        "BEAM_READY (beam stable, waiting for wafer), LOADING (transferring wafer to platen), ALIGNING (moving platen "
        "to tilt/twist angles), IMPLANTING (beam on, scanning, dose accumulating), UNLOADING (wafer returning to load lock), "
        "COMPLETED (run finished), FAULT (stopped due to alarm), and MAINTENANCE (servicing active).<br/><br/>"
        "Refer to the companion Variable Tables workbook, Sheet <b>'State Definitions'</b>, for definitions of all "
        "process states.", BODY_J))

    story.append(Paragraph("10.2 Transition Logic", H2))
    story.append(Paragraph(
        "Transitions occur in response to host commands (manual) or equipment events (automatic). "
        "For example, receiving a START_IMPLANT command triggers a transition from IDLE to SETTING_UP. "
        "Once beam tuning completes, the tool automatically transitions to BEAM_READY. Critical alarms trigger an "
        "automatic transition from any active state to FAULT.<br/><br/>"
        "Refer to the companion Variable Tables workbook, Sheet <b>'State Transitions'</b>, for the complete transition "
        "table, including source states, destination states, triggers, and manual/auto classifications.", BODY_J))

    story.append(Paragraph("10.3 GEM Control State Overlay", H2))
    story.append(Paragraph(
        "The GEM Control State machine governs the host-equipment relationship. It operates independently of the "
        "process state machine and consists of: OFF-LINE (no host communication), ON-LINE LOCAL (host can read data, "
        "but commands are rejected except for online request), and ON-LINE REMOTE (host has full control, can send "
        "remote commands and recipes). Control state transitions are reported via the ControlStateChange event.", BODY_J))
    story.append(PageBreak())

# ── Chapter 11 — Message Summary ─────────────────────────────────────────────
def chapter11(story):
    story.append(Paragraph("Chapter 11 — SECS-II Message Summary", H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=MID_BLUE))
    story.append(Paragraph(
        "This chapter summarizes the SECS-II stream and function messages supported by the IMP-HE2000. "
        "The supported messages cover the required GEM capabilities and selected optional capabilities "
        "required for factory host integration.", BODY_J))

    story.append(Paragraph("11.1 Host-to-Equipment Messages", H2))
    story.append(Paragraph(
        "Host-to-Equipment messages are sent by the factory host to request status, send commands, manage "
        "recipes, or configure reports. Key streams include S1 (status requests), S2 (configuration/control), "
        "S5 (alarm enable), S7 (recipe transfer), and S10 (terminal display).<br/><br/>"
        "Refer to the companion Variable Tables workbook, Sheet <b>'Messages H to E'</b>, for the complete summary "
        "of host-initiated messages.", BODY_J))

    story.append(Paragraph("11.2 Equipment-to-Host Messages", H2))
    story.append(Paragraph(
        "Equipment-to-Host messages are sent by the tool to reply to host requests, report events, send trace data, "
        "or notify the host of alarms. Key streams include S1 (status replies), S2 (command acknowledges), "
        "S5 (alarm reports), S6 (event reports), and S9 (system errors).<br/><br/>"
        "Refer to the companion Variable Tables workbook, Sheet <b>'Messages E to H'</b>, for the summary of "
        "equipment-initiated messages.", BODY_J))
    story.append(PageBreak())

# ── Chapter 12 — Message Detail ───────────────────────────────────────────────
def chapter12(story):
    story.append(Paragraph("Chapter 12 — SECS-II Message Detail", H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=MID_BLUE))
    story.append(Paragraph(
        "This chapter provides details of key SECS-II messages, including data structures and item types. "
        "All messages follow the SEMI E5 standard. Note that all angle brackets (&lt; and &gt;) representing "
        "SECS structure levels have been escaped to prevent layout errors.", BODY_J))

    def msg_block(stream_func, name, direction, body_lines, notes=None):
        story.append(Paragraph(f"{stream_func}  —  {name}", H3))
        meta = Table([[Paragraph("Direction", H3), Paragraph(direction, BODY),
                       Paragraph("Reply Required", H3), Paragraph("Yes" if "W" in direction or "Request" in name else "No", BODY)]],
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

    story.append(Paragraph("12.1 S1 — Equipment Status Messages", H2))
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
    ], "SVID list may be empty (requests all SVs). Return types match each variable's declared type.")

    msg_block("S1F13 W / S1F14", "Establish Communications", "H→E / E→H", [
        "S1F13 W",
        "<L [2]",
        "  <A MDLN>       -- Equipment model number ('IMP-HE2000')",
        "  <A SOFTREV>    -- Software revision string ('v6.2.1')",
        ">",
        "",
        "S1F14",
        "<L [2]",
        "  <B COMMACK>    -- 0x00=Accepted, 0x01=Denied",
        "  <L [2]",
        "    <A MDLN>",
        "    <A SOFTREV>",
        "  >",
        ">",
    ], "COMMACK=0x00 indicates communication session is active.")

    story.append(Paragraph("12.2 S2 — Equipment Control Messages", H2))
    msg_block("S2F41 W / S2F42", "Host Command Send / Acknowledge", "H→E / E→H", [
        "S2F41 W",
        "<L [2]",
        "  <A RCMD>                -- Remote command name (e.g. 'START_IMPLANT')",
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
        "  <B HCACK>               -- 0x00=OK, 0x01=Invalid command, 0x02=Cannot perform now,",
        "                           -- 0x03=At least 1 parameter invalid, 0x04=Rejected (safety)",
        "  <L [n]                  -- Parameter acknowledge list",
        "    <L [2]",
        "      <A CPNAME>",
        "      <B CPACK>           -- 0x00=OK, 0x01=Name not recognised, 0x02=Illegal value",
        "    >",
        "  >",
        ">",
    ])

    msg_block("S2F33 W / S2F34", "Define Report / Acknowledge", "H→E / E→H", [
        "S2F33 W",
        "<L [2]",
        "  <U4 DATAID>             -- Unique transaction ID",
        "  <L [n]                  -- Report definition list",
        "    <L [2]",
        "      <U4 RPTID>          -- Report identifier",
        "      <L [m]              -- Variable list",
        "        <U2 VID>",
        "        ...",
        "      >",
        "    >",
        "  >",
        ">",
        "",
        "S2F34",
        "<B DRACK>                 -- 0x00=OK, 0x01=Insufficient space, 0x03=RPTID already defined",
    ])

    story.append(Paragraph("12.3 S5 — Alarm Management", H2))
    msg_block("S5F1", "Alarm Report Send", "E→H (Primary, no reply)", [
        "S5F1",
        "<L [3]",
        "  <B ALCD>               -- Bit 7=1: alarm set; Bit 7=0: alarm cleared",
        "  <U4 ALID>              -- Alarm ID",
        "  <A ALTX>               -- Alarm text description (max 120 chars)",
        ">",
    ], "ALCD bit 7 indicates set/clear state. Host should log all alarm notifications.")

    story.append(Paragraph("12.4 S6 — Data Collection", H2))
    msg_block("S6F11 W / S6F12", "Event Report Send / Acknowledge", "E→H / H→E", [
        "S6F11 W",
        "<L [3]",
        "  <U4 DATAID>            -- Unique transaction ID",
        "  <U4 CEID>              -- Collection Event ID",
        "  <L [n]                 -- Report list",
        "    <L [2]",
        "      <U4 RPTID>",
        "      <L [m]             -- Variable values",
        "        <item V1>",
        "        ...",
        "      >",
        "    >",
        "  >",
        ">",
        "",
        "S6F12",
        "<B ACKC6>               -- 0x00=Accepted",
    ])

    story.append(Paragraph("12.5 S7 — Process Program Management", H2))
    msg_block("S7F3 W / S7F4", "Process Program Send / Acknowledge", "H→E / E→H", [
        "S7F3 W",
        "<L [2]",
        "  <A PPID>               -- Process Program ID (recipe name)",
        "  <B PPBODY>             -- Recipe body bytes",
        ">",
        "",
        "S7F4",
        "<B ACKC7>               -- 0x00=Accepted, 0x01=Format error, 0x03=Insufficient storage",
    ])

    story.append(Paragraph("12.6 S9 — System Errors", H2))
    msg_block("S9F7", "Illegal Data", "E→H (Primary, no reply)", [
        "S9F7",
        "<L [2]",
        "  <B MHEAD>              -- Header of offending message",
        "  <B SHEAD>              -- System bytes of offending message",
        ">",
    ], "Tool sends S9Fx messages in response to host messages with format errors.")
    story.append(PageBreak())

# ── Appendices ────────────────────────────────────────────────────────────────
def appendices(story):
    # Appendix A — GEM Compliance Matrix
    story.append(Paragraph("Appendix A — GEM Compliance Matrix (Prose)", H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=MID_BLUE))
    story.append(Paragraph(
        "The IMP-HE2000 complies with all mandatory capabilities defined in the SEMI E30 Generic "
        "Equipment Model standard, including Establish Communications, Process Program Management, "
        "Equipment Self-Description, Control, Alarm Management, and Event Notification. "
        "It also implements several optional capabilities, such as Variable Data Collection, Limits Monitoring, "
        "enhanced recipe management, equipment terminal services, and clock synchronization.<br/><br/>"
        "Refer to the companion Variable Tables workbook, Sheet <b>'GEM Compliance'</b>, for the complete "
        "compliance matrix mapping each standard capability to its implementing SECS-II stream/function pairs.", BODY_J))
    story.append(PageBreak())

    # Appendix B — Operational Scenarios
    story.append(Paragraph("Appendix B — Operational Scenarios (Prose)", H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=MID_BLUE))

    story.append(Paragraph("B.1 Communication and Configuration Setup", H2))
    story.append(Paragraph(
        "1. <b>Host connection</b>: Host initiates a TCP connection to the tool IP and port 5020. Once established, "
        "host sends <b>S1F13</b> (Establish Communications).<br/>"
        "2. <b>Tool acknowledge</b>: The tool verifies network parameters and replies with <b>S1F14</b> (COMMACK=0x00). "
        "The GEM Control State transitions to ON-LINE.<br/>"
        "3. <b>Report definitions</b>: Host sends <b>S2F33</b> to define standard reports (e.g., linking report "
        "3101 to variables for beam and dose). The tool replies with <b>S2F34</b> (DRACK=0x00).<br/>"
        "4. <b>Link reports to events</b>: Host sends <b>S2F35</b> to link reports to events (e.g., linking event 3001 "
        "to report 3101). Tool replies with <b>S2F36</b> (LRACK=0x00).<br/>"
        "5. <b>Enable event notifications</b>: Host sends <b>S2F37</b> to enable event notifications for lot tracking. "
        "Tool replies with <b>S2F38</b> (ERACK=0x00).", BODY_J))

    story.append(Paragraph("B.2 Successful Implant Process Run", H2))
    story.append(Paragraph(
        "1. <b>Recipe upload</b>: Host uploads process recipe 'B_120K_1E15' using <b>S7F3</b>. Tool replies with <b>S7F4</b> (ACKC7=0x00).<br/>"
        "2. <b>Implant start command</b>: Host sends <b>S2F41</b> with command START_IMPLANT and parameters RECIPE_ID='B_120K_1E15', "
        "WAFER_ID='WFR-B24', SLOT_NUMBER=5. Tool checks safety interlocks and replies with <b>S2F42</b> (HCACK=0x00).<br/>"
        "3. <b>Tuning and load lock pump</b>: Tool transitions to SETTING_UP state. The source plasma is ignited, "
        "and the load lock pumps down. Once vacuum and beam parameters are ready, tool transitions to BEAM_READY.<br/>"
        "4. <b>Wafer loading and alignment</b>: The wafer is loaded onto the platen, and the platen moves to the tilt/twist "
        "angles. The tool sends <b>S6F11</b> for WaferLoaded_EndStation (CEID 3010).<br/>"
        "5. <b>Implant active</b>: The beam shutter opens, and implantation begins. Tool sends <b>S6F11</b> for ImplantStart (CEID 3001).<br/>"
        "6. <b>Dose achieved</b>: When target dose is achieved (1e15 ions/cm²), the beam shutter closes. Tool sends <b>S6F11</b> "
        "for ImplantEnd (CEID 3002) containing report 3102 with delivered dose, uniformity, and PASS result.<br/>"
        "7. <b>Wafer unload</b>: The platen returns to home position, and the robot transfers the wafer back to the FOUP. "
        "Tool sends <b>S6F11</b> for WaferUnloaded_EndStation (CEID 3011).", BODY_J))

    story.append(Paragraph("B.3 Alarm Interlock Handling", H2))
    story.append(Paragraph(
        "1. <b>Overheat alarm</b>: During active implantation, if wafer temperature exceeds 120°C, the tool ignites a critical alarm "
        "and immediately sends <b>S5F1</b> (ALID=4006, ALTX='EndStn_WaferOverheat').<br/>"
        "2. <b>Process abort</b>: Simultaneously, the beam shutter closes, and the tool transitions to FAULT state. The tool sends "
        "<b>S6F11</b> for ImplantAbort (CEID 3003) and AlarmSet (CEID 3037).<br/>"
        "3. <b>Host investigation</b>: Host receives the alarm, queries SVID 1159 (measured wafer temperature), and logs the error.<br/>"
        "4. <b>Recovery</b>: Operator checks backside cooling helium flow and clears platen debris. Once temperature drops "
        "below safe threshold, operator issues a reset command. Host sends <b>S2F41</b> with command RESET_FAULT. Tool clears the fault, "
        "sends S5F1 (ALCD=0x00, ALID=4006, ALTX='Wafer temperature cleared'), and transitions to IDLE state.", BODY_J))
    story.append(PageBreak())

    # Appendix C — Alarm Recovery Procedures
    story.append(Paragraph("Appendix C — Alarm Recovery Procedures (Detailed Step-by-Step)", H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=MID_BLUE))
    
    procedures = [
        ("ALID 4001 — Source_ArcFault", [
            "1. Tool automatically shuts off plasma and closes the beam shutter. High voltage remains disabled.",
            "2. Host receives S5F1 for ALID 4001. Operator should verify SVID 1051 (arc current) and SVID 1052 (arc voltage).",
            "3. Inspect tungsten filament and arc chamber for degradation. Filament operational hours are checked via SVID 1061.",
            "4. If filament is thin or broken, perform source maintenance and reset source lifetime hours counter.",
            "5. After hardware check, send RESET_FAULT RCMD to return to IDLE state."
        ]),
        ("ALID 4002 — Source_GasLeak", [
            "1. Hardwired interlocks close toxic gas cabinet pneumatic valves immediately and trigger facility exhaust alarms.",
            "2. Host receives S5F1 for ALID 4002. Evacuate all personnel from the gas box and tool bay immediately.",
            "3. Notify facility safety officer. Do not attempt local tool reset.",
            "4. Verify leak condition using facility ambient gas monitors.",
            "5. Once cleared, reset facility safety loops, then send RESET_FAULT RCMD from host."
        ]),
        ("ALID 4005 — EndStn_DoseOverrun", [
            "1. Tool closes the electrostatic beam shutter, terminates wafer scanning, and transitions to FAULT.",
            "2. Host receives S5F1 for ALID 4005 and ImplantAbort event report.",
            "3. Check actual dose delivered (DVID 2051) against recipe target (DVID 2008). Check beam stability (DVID 2062).",
            "4. Calibrate dose Faraday cups. Check dose integrator electronics.",
            "5. Send RESET_FAULT RCMD, unload the damaged wafer, and restart process with a test wafer."
        ]),
        ("ALID 4006 — EndStn_WaferOverheat", [
            "1. Beam shutter is closed, platen mechanical scanning is stopped, and tool transitions to FAULT.",
            "2. Check measured wafer temperature (SVID 1159). Monitor until wafer cools down below 50°C.",
            "3. Check backside Helium coolant pressure (SVID 1163) and coolant flow rate (SVID 1162).",
            "4. Verify electrostatic clamp voltage and chuck surface cleanliness. Confirm clamp release works.",
            "5. Once hardware is verified and temperature is below safe threshold, send RESET_FAULT RCMD."
        ])
    ]
    for title, steps in procedures:
        story.append(Paragraph(title, H3))
        for step in steps:
            story.append(Paragraph(step, BODY))
        story.append(Spacer(1, 0.2*cm))
        
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph(
        "End of Document — IMP-HE2000 SECS/GEM User Manual Revision A", NOTE))

# ── Page numbering ────────────────────────────────────────────────────────────
def add_page_number(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#666666"))
    w, h = A4
    canvas.drawString(MARGIN, 1.2*cm,
        f"IMP-HE2000 SECS/GEM User Manual  |  Revision A  |  PrecisionBeam Technologies")
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
        title="IMP-HE2000 SECS/GEM User Manual",
        author="PrecisionBeam Technologies",
        subject="GEM UM Rev A",
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
    build_pdf(r"E:\Github\EquipmentAutomationPlatforms\IMP_HE2000_User_Manual.pdf")
