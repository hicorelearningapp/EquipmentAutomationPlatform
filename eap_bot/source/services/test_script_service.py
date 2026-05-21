import logging

logger = logging.getLogger(__name__)


class TestScriptService:
    def parse_sml_to_tests(self, content: str) -> list[dict]:
        lines = content.splitlines()
        tests = []
        current_lines = []

        for line in lines:
            stripped = line.strip()
            # If we are not currently accumulating a block, skip comments and empty lines
            if not current_lines:
                if not stripped or stripped.startswith("//") or stripped.startswith("#"):
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

                category = "EquipmentControl"  # default fallback
                if header_line:
                    parts = header_line.split()
                    if parts:
                        sml_cmd = parts[0].upper()
                        if "F" in sml_cmd:
                            stream_part = sml_cmd.split("F")[0]
                        else:
                            stream_part = sml_cmd

                        if sml_cmd == "S2F23":
                            category = "EventReporting"
                        elif stream_part == "S1":
                            category = "EquipmentStatus"
                        elif stream_part == "S2":
                            category = "EquipmentControl"
                        elif stream_part == "S5":
                            category = "AlarmManagement"
                        elif stream_part == "S6":
                            category = "EventReporting"
                        elif stream_part == "S7":
                            category = "ProcessProgramManagement"
                        elif stream_part == "S10":
                            category = "TerminalServices"

                tests.append(
                    {
                        "TestID": str(len(tests) + 1),
                        "Category": category,
                        "SML": sml_text,
                        "Status": "NotRun",
                    }
                )
                current_lines = []

        return tests
