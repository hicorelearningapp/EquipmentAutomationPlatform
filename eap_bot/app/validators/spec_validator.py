from collections import Counter

from app.schemas.secsgem import EquipmentSpec, ValidationIssue, ValidationReport


class SpecValidator:

    def validate(self, spec: EquipmentSpec) -> ValidationReport:
        """Run all checks and return a consolidated ValidationReport."""
        issues: list[ValidationIssue] = []

        self._check_duplicate_ids(spec, issues)
        self._check_linked_vids(spec, issues)
        self._check_transition_states(spec, issues)
        self._check_transition_triggers(spec, issues)
        self._check_unit_consistency(spec, issues)
        self._check_critical_sections(spec, issues)

        return ValidationReport(Issues=issues)

    @staticmethod
    def _dup_ids(values: list[str]) -> list[str]:
        return [v for v, n in Counter(values).items() if n > 1]

    def _check_duplicate_ids(
        self, spec: EquipmentSpec, issues: list[ValidationIssue]
    ) -> None:
        pairs = [
            ("Variable", [v.VID for v in spec.Variables]),
            ("Event", [e.CEID for e in spec.Events]),
            ("Alarm", [a.AlarmID for a in spec.Alarms]),
            ("RemoteCommand", [c.RCMD for c in spec.RemoteCommands]),
            ("State", [s.StateID for s in spec.States]),
        ]
        for kind, ids in pairs:
            for dup in self._dup_ids(ids):
                issues.append(
                    ValidationIssue(
                        Severity="error",
                        Code="duplicate_id",
                        Message=f"Duplicate {kind} id: {dup}",
                        EntityID=str(dup),
                    )
                )

    def _check_linked_vids(
        self, spec: EquipmentSpec, issues: list[ValidationIssue]
    ) -> None:
        known = {v.VID for v in spec.Variables}
        for e in spec.Events:
            for vid in e.LinkedVIDs:
                if vid not in known:
                    issues.append(
                        ValidationIssue(
                            Severity="error",
                            Code="linked_vid_not_found",
                            Message=f"Event {e.CEID} references unknown VID {vid}",
                            EntityID=str(e.CEID),
                        )
                    )
        for a in spec.Alarms:
            if a.LinkedVID and a.LinkedVID not in known:
                issues.append(
                    ValidationIssue(
                        Severity="error",
                        Code="linked_vid_not_found",
                        Message=f"Alarm {a.AlarmID} references unknown VID {a.LinkedVID}",
                        EntityID=str(a.AlarmID),
                    )
                )

    def _check_transition_states(
        self, spec: EquipmentSpec, issues: list[ValidationIssue]
    ) -> None:
        state_names = {s.Name for s in spec.States} | {s.StateID for s in spec.States}
        for i, t in enumerate(spec.StateTransitions):
            for field in ("FromState", "ToState"):
                value = getattr(t, field)
                if value not in state_names:
                    issues.append(
                        ValidationIssue(
                            Severity="error",
                            Code="transition_state_not_found",
                            Message=(
                                f"Transition #{i} {field}={value!r} "
                                f"does not match any State"
                            ),
                            EntityID=f"transition[{i}]",
                        )
                    )

    def _check_transition_triggers(
        self, spec: EquipmentSpec, issues: list[ValidationIssue]
    ) -> None:
        event_names = {e.Name for e in spec.Events} | {str(e.CEID) for e in spec.Events}
        rcmd_names = {c.RCMD for c in spec.RemoteCommands}
        for i, t in enumerate(spec.StateTransitions):
            if t.TriggerEvent and t.TriggerEvent not in event_names:
                issues.append(
                    ValidationIssue(
                        Severity="warning",
                        Code="transition_trigger_not_found",
                        Message=(
                            f"Transition #{i} TriggerEvent={t.TriggerEvent!r} "
                            f"does not match any Event"
                        ),
                        EntityID=f"transition[{i}]",
                    )
                )
            if t.TriggerCommand and t.TriggerCommand not in rcmd_names:
                issues.append(
                    ValidationIssue(
                        Severity="warning",
                        Code="transition_trigger_not_found",
                        Message=(
                            f"Transition #{i} TriggerCommand={t.TriggerCommand!r} "
                            f"does not match any RemoteCommand"
                        ),
                        EntityID=f"transition[{i}]",
                    )
                )

    def _check_unit_consistency(
        self, spec: EquipmentSpec, issues: list[ValidationIssue]
    ) -> None:
        by_name: dict[str, set[str]] = {}
        for v in spec.Variables:
            if v.Unit:
                by_name.setdefault(v.Name.lower(), set()).add(v.Unit)
        for name, units in by_name.items():
            if len(units) > 1:
                issues.append(
                    ValidationIssue(
                        Severity="warning",
                        Code="unit_mismatch",
                        Message=f"Variable {name!r} has inconsistent units: {sorted(units)}",
                        EntityID=name,
                    )
                )

    def _check_critical_sections(
        self, spec: EquipmentSpec, issues: list[ValidationIssue]
    ) -> None:
        if not spec.Variables:
            issues.append(
                ValidationIssue(
                    Severity="error",
                    Code="extraction_empty",
                    Message="No Variables extracted",
                )
            )
        if not spec.Events:
            issues.append(
                ValidationIssue(
                    Severity="error",
                    Code="extraction_empty",
                    Message="No Events extracted",
                )
            )
        if not spec.Alarms:
            issues.append(
                ValidationIssue(
                    Severity="warning",
                    Code="section_missing",
                    Message="No Alarms extracted",
                )
            )
        if not spec.RemoteCommands:
            issues.append(
                ValidationIssue(
                    Severity="warning",
                    Code="section_missing",
                    Message="No RemoteCommands extracted",
                )
            )
