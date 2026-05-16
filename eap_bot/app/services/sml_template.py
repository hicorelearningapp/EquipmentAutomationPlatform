"""Hardcoded SML script template written to every project on successful Analyze.

Source: "Tool Characterization Testing Sequence Template.docx"
"""

SML_TEMPLATE_FILENAME = "tool_characterization_sequence.txt"

SML_GENERAL_TEMPLATE = """
// S1F1 - Are You There Request
S1F1 W
<L [0]>
.

// S1F3 - Selected Equipment Status Request Without Values
S1F3 W
<L [0]>
.

// S1F3 - Selected Equipment Status Request With Values
S1F3 W
<L
  <U4 1001>
  <U4 1002>
>
.

// S1F11 - Status Variable Namelist Request
S1F11 W
<L
  <U4 1001>
  <U4 1002>
>
.

// S1F1 Establish Communications Request Without Values
S1F3 W
<L [0]>
.

// S1F15 - Request OFF-LINE
S1F15 W
<L [0]>
.

// S1F17 - Request ON-LINE
S1F17 W
<L [0]>
.

// S1F21 - Data Variable Namelist Request Request ALL Data Variables (Without Values)  Request:
S1F21 W
<L [0]>
.

// S1F21 - Data Variable Namelist Request Request  Data Variables (With Values)  Request:
S1F21 W
<L
  <U4 2001>
  <U4 2002>
>
.

// S1F23 - Collection Event Namelist Request(Without Values)
S1F23 W
<L [0]>
.

// S1F23 - Collection Event Namelist Request(With Values)
S1F23 W
<L
  <U4 3001>
>
.

// S2F13 - Equipment Constant Request (Without Values)
S2F13 W
<L [0]>
.

// S2F13 - Equipment Constant Request (WithValues)

S2F13 W
<L
  <U4 5001>
>
.

// S2F15 - New Equipment Constant Send (Without Values)
S2F15 W
<L [0]>
.

// S2F15 - New Equipment Constant Send (With Values)
S2F15 W
<L
  <L
    <U4 5001>
    <A "150">
  >
>
.

// S2F17 - Date and Time Request
S2F17 W
<L [0]>
.

// S2F23 - Trace Initialize Send-delete
S2F23 W
<L [0]>
.
S2F23 W
<L
  <U4 1>
  <U4 10>
  <U4 5>
>
.

// S2F29 - Equipment Constant Namelist Request (Without Values)
S2F29 W
<L [0]>
.

// S2F29 - Equipment Constant Namelist Request
 (With Values)
S2F29 W
<L
  <U4 5001>
>
.

// S2F31 - Date and Time Set Request
S2F31 W
<A "20260514123045">
.
// S2F33 - Define Report
S2F33 W
<L
  <U4 1>
  <L
    <U4 1001>
    <U4 1002>
  >
>
.

// S2F35 - Link Event Report
S2F35 W
<L
  <U4 3001>
  <U4 1>
>
.

// S2F37 - Enable Event Report
S2F37 W
<L
  <BOOLEAN TRUE>
  <U4 3001>
>
.

// S2F37 - Enable Event Report
S2F37 W
<L [2]
  <B 0x00>        
  <L [0]>         
>
.

// S2F39 - Multi-block Inquire
S2F39 W
<U4 2048>
.

// S2F49 - Enhanced Remote Command
S2F49 W
<L
  <A "PPSELECT">
  <L
    <L
      <A "PPID">
      <A "RECIPE01">
    >
  >
>
.

//S5F1 — Alarm Report Send
S5F1 W
<L
  <B 0x80>
  <U4 9001>
  <A "Vacuum Low">
>
.

//S5F2 — Alarm Acknowledge
S5F2
<B 0x00>
.
//S5F3 — Enable/Disable Alarm Send
S5F3 W
<L
  <BOOLEAN TRUE>
  <U4 9001>
>
.

//S5F4 — Alarm Enable Acknowledge
S5F4
<B 0x00>
.

//S5F5 — List Alarm Request
S5F5 W
<L [0]>
.
//S5F6 — List Alarm Reply
S5F6
<L
  <L
    <U4 9001>
    <A "Vacuum Low">
  >
>
.

// Equipment sends Trace Data
S6F1 W
<L
<U4 1>
<A "TRACE DATA">
>
.

// Host replies Trace Data Ack
S6F2
<B 0x00>
.

// Equipment sends Multi-block Data
S6F5 W
<L
<A "BLOCK1">
>
.

// Host replies Multi-block Ack
S6F6
<B 0x00>
.

// Equipment sends Event Report
S6F11 W
<L
<U4 3001>
<U4 1>
<L
<A "RUNNING">
>
>
.

// Host replies Event Report Ack
S6F12
<B 0x00>
.

// S7F1 - Process Program Load Inquire
S7F1 W
<A "RECIPE01">
.

// S7F3 - Process Program Send
S7F3 W
<L [2]
  <A "GOLD_ETCH_V2"> 
  <B 0x47 0x4F 0x4C 0x44...> 
>
.

// S7F5 - Process Program Request
S7F5 W
<A "RECIPE01">
.

// S7F17 - Delete Process Program Send
S7F17 W
<A "RECIPE01">
.

// S7F19 - Current Equipment Process Program Request
S7F19 W
<L [0]>
.

// S10F1 - Terminal Request
S10F1 W
<A "Operator Message">
.

// S10F3 - Terminal Display Single Message
S10F3 W
<L
  <A "SYSTEM READY">
>
.

// S10F5 - Terminal Display Multi-block Message
S10F5 W
<L
  <A "MULTI BLOCK MESSAGE">
>
.

"""

SML_CHARACTERISATION_TEMPLATE = """

// Tool Characterization Testing Sequence
// S1F1 - Are You There Request
S1F1 W
<L [0]>
.

// S1F13 - Establish Communications Request
S1F13 W
<L [0]>
.

// S5F3 - DISABLE ALL ALARMS
S5F3 W
<L
  <BOOLEAN FALSE>
  <U4 1001>
>
.

// S2F37 - DISABLE ALL EVENTS
S2F37 W
<L
  <BOOLEAN FALSE>
  <U4 2001>
>
.

// S2F35 - UNLINK SPECIFIC REPORTS
S2F35 W
<L
  <U4 2001>
  <U4 3001>
>
.

// S2F33 - DELETE SPECIFIC REPORTS
S2F33 W
<L
  <U4 3001>
  <L [0]>
>
.

// S2F33 - DEFINE REPORTS
S2F33 W
<L
  <U4 3001>
  <L
    <U4 4001>
    <U4 5001>
    <U4 6001>
  >
>
.

// S2F35 - LINK REPORTS
S2F35 W
<L
  <U4 2001>
  <U4 3001>
>
.

// S2F37 - ENABLE ALL EVENTS
S2F37 W
<L
  <BOOLEAN TRUE>
  <U4 2001>
>
.

// S5F3 - ENABLE ALL ALARMS
S5F3 W
<L
  <BOOLEAN TRUE>
  <U4 1001>
>
.

// S2F41 - PPSELECT
S2F41 W
<L
  <A "PPSELECT">
  <L
    <L
      <A "PPID">
      <A "RECIPE_01">
    >
  >
>
.
// S2F41 - START
S2F41 W
<L
  <A "PPSTART">
  <L
    <L
      <A "LOTID">
      <A "LOT1001">
    >
  >
>
.
// S2F23 - TRACE SEND
S2F23 W
<L
  <U4 7001>
  <U4 10>
  <U4 50>
  <L
    <U4 5001>
  >
>
.
// S2F23 - TRACE CANCELLED
S2F23 W
<L
  <U4 7001>
  <U4 0>
  <U4 0>
  <L [0]>
>
.
"""

SML_TEMPLATES = {
    "GeneralGEMTesting": SML_GENERAL_TEMPLATE,
    "ToolCharacterisationTesting": SML_CHARACTERISATION_TEMPLATE
}

# For backward compatibility with storage_service or other legacy code
SML_TEMPLATE_CONTENT = SML_CHARACTERISATION_TEMPLATE
