"""Hardcoded SML script template written to every project on successful Analyze.

Source: "Tool Characterization Testing Sequence Template.docx"
"""

SML_TEMPLATE_FILENAME = "tool_characterization_sequence.txt"

SML_TEMPLATE_CONTENT = '''Tool Characterization Testing Sequence Template

 1. S1F1

S1F1 W
<L [0]>


 2. S1F13  Establish Communications Request

S1F13 W
<L
<A "HOST">
<A "1.0">
>
..


 3. S5F3 – DISABLE ALL ALARMS

S5F3 W
<L
  <BOOLEAN FALSE>
  <ALID>
>


 4. S2F37 – DISABLE ALL EVENTS

S2F37 W
<L
  <BOOLEAN FALSE>
  <CEID>
>
.


 5. S2F35 – UNLINK SPECIFIC REPORTS

S2F35 W
<L
  <CEID>
  <RPTID>
>
.


 6. S2F33 – DELETE SPECIFIC REPORTS

S2F33 W
<L
  <RPTID>
  <L [0]>
>
.


 7. S2F33 – DEFINE REPORTS

S2F33 W
<L
  <RPTID>
  <L
    <VID>
    <SVID>
    <DVID>
  >
>
.


 8. S2F35 – LINK REPORTS

S2F35 W
<L
  <CEID>
  <RPTID>
>
.


 9. S2F37 – ENABLE ALL EVENTS

S2F37 W
<L
  <BOOLEAN TRUE>
  <CEID>
>
.


 10. S5F3 – ENABLE ALL ALARMS

S5F3 W
<L
  <BOOLEAN TRUE>
  <ALID>
>
.

 10. S2F41 – PPSELECT

S2F41 W
<L
  <A "PPSELECT">
  <L
    <L
      <A "PPID">
      <A "PPID_VALUE">
    >
  >
>
.

 11. S2F41 – START

S2F41 W
<L
  <A "START">
  <L
    <L
      <A "LOTID">
      <A "LOTID_VALUE">
    >
  >
>
.

 12. S2F23 – TRACE SEND

S2F23 W
<L
  <TRID>
  <DSPER>
  <TOTSMP>
  <L
    <SVID>
  >
>
.

 13. S2F23 – TRACE CANCELLED
S2F23 W
<L
  <TRID>
  <DSPER>
  <TOTSMP>
  <L [0]>
>
.
'''
