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

        return ValidationReport(issues=issues)

    @staticmethod
    def _dup_ids(values: list[str]) -> list[str]:
        return [v for v, n in Counter(values).items() if n > 1]

    def _check_duplicate_ids(
        self, spec: EquipmentSpec, issues: list[ValidationIssue]
    ) -> None:
        pairs = [
            ("Variable", [v.vid for v in spec.variables]),
            ("Event", [e.ceid for e in spec.events]),
            ("Alarm", [a.alarm_id for a in spec.alarms]),
            ("RemoteCommand", [c.rcmd for c in spec.remote_commands]),
            ("State", [s.state_id for s in spec.states]),
        ]
        for kind, ids in pairs:
            for dup in self._dup_ids(ids):
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="duplicate_id",
                        message=f"Duplicate {kind} id: {dup}",
                        entity_id=dup,
                    )
                )

    def _check_linked_vids(
        self, spec: EquipmentSpec, issues: list[ValidationIssue]
    ) -> None:
        known = {v.vid for v in spec.variables}
        for e in spec.events:
            for vid in e.linked_vids:
                if vid not in known:
                    issues.append(
                        ValidationIssue(
                            severity="error",
                            code="linked_vid_not_found",
                            message=f"Event {e.ceid} references unknown VID {vid}",
                            entity_id=e.ceid,
                        )
                    )
        for a in spec.alarms:
            if a.linked_vid and a.linked_vid not in known:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="linked_vid_not_found",
                        message=f"Alarm {a.alarm_id} references unknown VID {a.linked_vid}",
                        entity_id=a.alarm_id,
                    )
                )

    def _check_transition_states(
        self, spec: EquipmentSpec, issues: list[ValidationIssue]
    ) -> None:
        state_names = {s.name for s in spec.states} | {s.state_id for s in spec.states}
        for i, t in enumerate(spec.state_transitions):
            for field in ("from_state", "to_state"):
                value = getattr(t, field)
                if value not in state_names:
                    issues.append(
                        ValidationIssue(
                            severity="error",
                            code="transition_state_not_found",
                            message=(
                                f"Transition #{i} {field}={value!r} "
                                f"does not match any State"
                            ),
                            entity_id=f"transition[{i}]",
                        )
                    )

    def _check_transition_triggers(
        self, spec: EquipmentSpec, issues: list[ValidationIssue]
    ) -> None:
        event_names = {e.name for e in spec.events} | {e.ceid for e in spec.events}
        rcmd_names = {c.rcmd for c in spec.remote_commands}
        for i, t in enumerate(spec.state_transitions):
            if t.trigger_event and t.trigger_event not in event_names:
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        code="transition_trigger_not_found",
                        message=(
                            f"Transition #{i} trigger_event={t.trigger_event!r} "
                            f"does not match any Event"
                        ),
                        entity_id=f"transition[{i}]",
                    )
                )
            if t.trigger_command and t.trigger_command not in rcmd_names:
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        code="transition_trigger_not_found",
                        message=(
                            f"Transition #{i} trigger_command={t.trigger_command!r} "
                            f"does not match any RemoteCommand"
                        ),
                        entity_id=f"transition[{i}]",
                    )
                )

    def _check_unit_consistency(
        self, spec: EquipmentSpec, issues: list[ValidationIssue]
    ) -> None:
        by_name: dict[str, set[str]] = {}
        for v in spec.variables:
            if v.unit:
                by_name.setdefault(v.name.lower(), set()).add(v.unit)
        for name, units in by_name.items():
            if len(units) > 1:
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        code="unit_mismatch",
                        message=f"Variable {name!r} has inconsistent units: {sorted(units)}",
                        entity_id=name,
                    )
                )

    def _check_critical_sections(
        self, spec: EquipmentSpec, issues: list[ValidationIssue]
    ) -> None:
        if not spec.variables:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="extraction_empty",
                    message="No Variables extracted",
                )
            )
        if not spec.events:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="extraction_empty",
                    message="No Events extracted",
                )
            )
        if not spec.alarms:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    code="section_missing",
                    message="No Alarms extracted",
                )
            )
        if not spec.remote_commands:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    code="section_missing",
                    message="No RemoteCommands extracted",
                )
            )
