import logging
import re

logger = logging.getLogger(__name__)


def _get_descriptive_name(header_line: str, sml_text: str, last_comment: str = "") -> str:
    # 1. Parse out the SECS message ID (SxFy) from the header_line
    match = re.search(r'(S\d+F\d+)', header_line, re.IGNORECASE)
    cmd = match.group(1).upper() if match else ""
    
    # 2. Extract a description from last_comment if possible
    comment_desc = ""
    if last_comment:
        # Clean comment markers
        cleaned = last_comment.replace("//", "").replace("#", "").replace("---", "").replace("===", "").strip()
        if cleaned:
            # Check if it starts with the command, e.g. "S1F1 - Are You There Request"
            m = re.match(r'^\s*(S\d+F\d+)\s*[\-—:]\s*(.+)$', cleaned, re.IGNORECASE)
            if m:
                comment_desc = m.group(2).strip()
            else:
                m2 = re.match(r'^\s*(S\d+F\d+)\s+(.+)$', cleaned, re.IGNORECASE)
                if m2:
                    comment_desc = m2.group(2).strip()
                else:
                    # If it's a command name only, e.g., "S1F1" or "S1F1 W"
                    if re.match(r'^S\d+F\d+\s*[Ww]?$', cleaned, re.IGNORECASE):
                        comment_desc = ""
                    else:
                        comment_desc = cleaned
                        
    # 3. If we have a descriptive comment, format it as "SxFy - Description"
    if comment_desc:
        if cmd:
            return f"{cmd} - {comment_desc}"
        return comment_desc
        
    # 4. Fallback: map using standard dictionary or content-based rules
    if cmd:
        if cmd == "S5F3":
            if "false" in sml_text.lower():
                return "S5F3 - DISABLE ALL ALARMS"
            elif "true" in sml_text.lower():
                return "S5F3 - ENABLE ALL ALARMS"
            return "S5F3 - Enable/Disable Alarm Send"
            
        if cmd == "S2F37":
            if "false" in sml_text.lower():
                return "S2F37 - DISABLE ALL EVENTS"
            elif "true" in sml_text.lower():
                return "S2F37 - ENABLE ALL EVENTS"
            return "S2F37 - Enable/Disable Event Report"
            
        if cmd == "S2F41":
            a_match = re.search(r'<A\s+["\']([^"\']+)["\']>', sml_text, re.IGNORECASE)
            if a_match:
                cmd_name = a_match.group(1).strip().upper()
                return f"S2F41 - {cmd_name}"
            return "S2F41 - Host Command Send"
            
        MAPPING = {
            "S1F1": "Are You There Request",
            "S1F3": "Selected Status Request",
            "S1F11": "Status Variable Namelist Request",
            "S1F13": "Establish Communications Request",
            "S1F15": "Request OFF-LINE",
            "S1F17": "Request ON-LINE",
            "S1F21": "Data Variable Namelist Request",
            "S2F17": "Date and Time Request",
            "S2F23": "Trace Initialize",
            "S2F31": "Comm Delay Timer Request",
            "S2F33": "Define Report",
            "S2F35": "Link Event Report",
            "S5F1": "Alarm Report Send",
            "S6F1": "Trace Data Send",
            "S6F11": "Event Report Send",
            "S7F1": "Process Program Load Inquire",
            "S7F3": "Process Program Send",
            "S7F5": "Process Program Request",
            "S7F17": "Process Program Delete",
            "S7F19": "Current EPPD Request",
            "S9F1": "Unrecognized Device ID",
            "S9F3": "Unrecognized Stream Type",
            "S9F5": "Unrecognized Function Type",
            "S9F7": "Illegal Data",
            "S9F9": "Transaction Timer Timeout",
            "S10F1": "Terminal Request",
            "S10F3": "Terminal Display, Single",
            "S10F5": "Terminal Display, Multi",
        }
        if cmd in MAPPING:
            return f"{cmd} - {MAPPING[cmd]}"
            
    return header_line


class TestScriptService:
    def parse_sml_to_tests(self, content: str) -> list[dict]:
        lines = content.splitlines()
        tests = []
        current_lines = []
        last_comment = ""

        for line in lines:
            stripped = line.strip()
            # If we are not currently accumulating a block, skip comments and empty lines
            if not current_lines:
                if not stripped:
                    last_comment = ""
                    continue
                if stripped.startswith("//") or stripped.startswith("#"):
                    last_comment = stripped
                    continue

            current_lines.append(line)

            # An SML block ends with a line consisting solely of "." (possibly with trailing whitespace or comment)
            if stripped == "." or (
                stripped.startswith(".")
                and (
                    len(stripped) == 1
                    or stripped[1:].strip().startswith("//")
                    or stripped[1:].strip().startswith("#")
                )
            ):
                sml_text = "\n".join(current_lines).strip()

                # Extract first non-comment, non-empty line as header to classify category
                header_line = ""
                for l in current_lines:
                    s_l = l.strip()
                    if s_l and not s_l.startswith("//") and not s_l.startswith("#"):
                        header_line = s_l
                        break

                category = "Equipment Control"  # default fallback
                if header_line:
                    parts = header_line.split()
                    if parts:
                        sml_cmd = parts[0].upper()
                        if "F" in sml_cmd:
                            stream_part = sml_cmd.split("F")[0]
                        else:
                            stream_part = sml_cmd
                        
                        try:
                            # stream_part is like 'S1', we need the integer 1
                            stream_id = int(stream_part.replace("S", ""))
                            from source.services.secs_categories import get_stream_category
                            category = get_stream_category(stream_id)
                        except (ValueError, TypeError):
                            pass

                # Determine TestName using mapping rules
                test_name = _get_descriptive_name(header_line, sml_text, last_comment)
                if not test_name:
                    test_name = f"Test {len(tests) + 1}"

                tests.append(
                    {
                        "TestID": str(len(tests) + 1),
                        "TestName": test_name,
                        "Category": category,
                        "SML": sml_text,
                        "Status": "NotRun",
                    }
                )
                current_lines = []
                last_comment = ""

        return tests
