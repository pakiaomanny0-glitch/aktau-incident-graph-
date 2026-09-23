from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Text
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class District(Base):
    """Ақтаудың мкр-дары (Адам 2 districts.json осыған сай толтырады)"""
    __tablename__ = "districts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)   # мыс: "5 мкр"
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)

    readings = relationship("Reading", back_populates="district")
    incidents = relationship("Incident", back_populates="district")


class Reading(Base):
    """Уақыт бойынша сенсор/synthetic деректер: температура, су сұранысы, су қысымы т.б."""
    __tablename__ = "readings"

    id = Column(Integer, primary_key=True, index=True)
    district_id = Column(Integer, ForeignKey("districts.id"), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)

    temperature = Column(Float, nullable=True)      # °C
    water_demand = Column(Float, nullable=True)      # шартты бірлік
    water_pressure = Column(Float, nullable=True)    # шартты бірлік / bar
    metric_type = Column(String, nullable=True)      # кеңейту үшін: "temperature", "water_demand"...
    value = Column(Float, nullable=True)             # metric_type-қа сай жалпы мән (икемді нұсқа)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    district = relationship("District", back_populates="readings")


class Incident(Base):
    """Ереже бойынша анықталған оқиға: мыс. heat>35 + demand>X => incident"""
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, index=True)
    district_id = Column(Integer, ForeignKey("districts.id"), nullable=False)

    type = Column(String, nullable=False)        # мыс: "water_shortage", "heat_spike"
    severity = Column(String, nullable=False)     # "low" | "medium" | "high"
    description = Column(Text, nullable=True)

    triggered_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    district = relationship("District", back_populates="incidents")

    # Бір incident бірнеше correlation-ның source/target болуы мүмкін
    source_edges = relationship(
        "Correlation", foreign_keys="Correlation.source_incident_id",
        back_populates="source_incident"
    )
    target_edges = relationship(
        "Correlation", foreign_keys="Correlation.target_incident_id",
        back_populates="target_incident"
    )


class Correlation(Base):
    """
    Incident-тер арасындағы байланыс (граф edge).
    Есептеу Адам 2-нің скриптінде (correlation_engine.py) жасалады,
    backend тек нәтижені сақтайды және /graph арқылы қайтарады.
    """
    __tablename__ = "correlations"

    id = Column(Integer, primary_key=True, index=True)
    source_incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=False)
    target_incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=False)

    weight = Column(Float, nullable=False, default=1.0)   # байланыс күші 0-1
    relation_type = Column(String, nullable=True)          # мыс: "causal", "temporal"
    explanation = Column(Text, nullable=True)               # мыс: "heat spike -> demand surge"

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    source_incident = relationship(
        "Incident", foreign_keys=[source_incident_id], back_populates="source_edges"
    )
    target_incident = relationship(
        "Incident", foreign_keys=[target_incident_id], back_populates="target_edges"
    )
