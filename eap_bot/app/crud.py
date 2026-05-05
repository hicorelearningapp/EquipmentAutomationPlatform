from sqlalchemy.orm import Session

from app.models.models import EquipmentMappingRow, EquipmentSpecRow
from app.schemas.mapping import EquipmentMapping
from app.schemas.secsgem import EquipmentSpec, ValidationReport


class SpecRepository:

    def __init__(self, db: Session) -> None:
        self.db = db

    def save(
        self,
        filename: str,
        raw_text: str,
        spec: EquipmentSpec,
        report: ValidationReport,
    ) -> EquipmentSpecRow:
        row = EquipmentSpecRow(
            tool_id=spec.tool_id,
            tool_type=spec.tool_type,
            filename=filename,
            raw_text=raw_text,
            spec_json=spec.model_dump_json(indent=4),
            validation_json=report.model_dump_json(indent=4),
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def get(self, spec_id: int) -> EquipmentSpecRow | None:
        return self.db.query(EquipmentSpecRow).filter(EquipmentSpecRow.id == spec_id).first()

    def list_all(self) -> list[EquipmentSpecRow]:
        return (
            self.db.query(EquipmentSpecRow)
            .order_by(EquipmentSpecRow.created_at.desc())
            .all()
        )


class MappingRepository:

    def __init__(self, db: Session) -> None:
        self.db = db

    def save(self, mapping: EquipmentMapping) -> EquipmentMappingRow:
        row = EquipmentMappingRow(
            spec_id=mapping.spec_id,
            mapping_json=mapping.model_dump_json(indent=4),
            is_approved=mapping.is_approved,
            approved_at=mapping.approved_at,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def get_by_spec(self, spec_id: int) -> EquipmentMappingRow | None:
        return (
            self.db.query(EquipmentMappingRow)
            .filter(EquipmentMappingRow.spec_id == spec_id)
            .order_by(EquipmentMappingRow.created_at.desc())
            .first()
        )
