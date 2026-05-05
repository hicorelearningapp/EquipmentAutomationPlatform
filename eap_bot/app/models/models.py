from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db import Base


class EquipmentSpecRow(Base):
    __tablename__ = "equipment_specs"

    id = Column(Integer, primary_key=True, index=True)
    tool_id = Column(String, index=True)
    tool_type = Column(String, index=True)
    filename = Column(String)
    raw_text = Column(Text)
    spec_json = Column(Text)
    validation_json = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    mappings = relationship("EquipmentMappingRow", back_populates="spec", cascade="all, delete-orphan")


class EquipmentMappingRow(Base):
    __tablename__ = "equipment_mappings"

    id = Column(Integer, primary_key=True, index=True)
    spec_id = Column(Integer, ForeignKey("equipment_specs.id"), nullable=False)
    mapping_json = Column(Text)
    is_approved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    approved_at = Column(DateTime, nullable=True)

    spec = relationship("EquipmentSpecRow", back_populates="mappings")
