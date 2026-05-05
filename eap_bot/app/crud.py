from sqlalchemy.orm import Session

from app.models.models import EquipmentSpecRow
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

    def save_mapping(self, spec_id: int, mapping: EquipmentMapping) -> EquipmentSpecRow | None:
        row = self.get(spec_id)
        if not row:
            return None
        
        row.mapping_json = mapping.model_dump_json(indent=4)
        row.mapping_is_approved = mapping.is_approved
        row.mapping_approved_at = mapping.approved_at
        
        self.db.commit()
        self.db.refresh(row)
        return row


