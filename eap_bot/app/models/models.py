from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db import Base


class ProjectRow(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    specs = relationship("EquipmentSpecRow", back_populates="project")


class EquipmentSpecRow(Base):
    __tablename__ = "equipment_specs"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True, index=True)
    tool_id = Column(String, index=True)
    tool_type = Column(String, index=True)
    filename = Column(String)
    raw_text = Column(Text)
    spec_json = Column(Text)
    validation_json = Column(Text)

    # Mapping data (Unified)
    mapping_json = Column(Text, nullable=True)
    mapping_is_approved = Column(Boolean, default=False)
    mapping_approved_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("ProjectRow", back_populates="specs")
