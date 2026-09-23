from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# ---------- District ----------
class DistrictBase(BaseModel):
    name: str
    lat: float
    lng: float


class DistrictCreate(DistrictBase):
    pass


class DistrictOut(DistrictBase):
    id: int

    class Config:
        from_attributes = True


# ---------- Reading ----------
class ReadingCreate(BaseModel):
    district_name: str          # Data адамы district_id білмейді, атау бойынша жібереді
    timestamp: datetime
    temperature: Optional[float] = None
    water_demand: Optional[float] = None
    water_pressure: Optional[float] = None
    metric_type: Optional[str] = None
    value: Optional[float] = None


class ReadingOut(BaseModel):
    id: int
    district_id: int
    timestamp: datetime
    temperature: Optional[float]
    water_demand: Optional[float]
    water_pressure: Optional[float]
    metric_type: Optional[str]
    value: Optional[float]

    class Config:
        from_attributes = True


# ---------- Incident ----------
class IncidentCreate(BaseModel):
    district_name: str
    type: str
    severity: str                 # "low" | "medium" | "high"
    description: Optional[str] = None
    triggered_at: datetime


class IncidentOut(BaseModel):
    id: int
    district_id: int
    district_name: Optional[str] = None
    type: str
    severity: str
    description: Optional[str]
    triggered_at: datetime
    lat: Optional[float] = None
    lng: Optional[float] = None

    class Config:
        from_attributes = True


# ---------- Correlation ----------
class CorrelationCreate(BaseModel):
    source_incident_id: int
    target_incident_id: int
    weight: float = 1.0
    relation_type: Optional[str] = None
    explanation: Optional[str] = None


class CorrelationOut(BaseModel):
    id: int
    source_incident_id: int
    target_incident_id: int
    weight: float
    relation_type: Optional[str]
    explanation: Optional[str]

    class Config:
        from_attributes = True


# ---------- Ingest (bulk, Адам 2 үшін) ----------
class IngestPayload(BaseModel):
    districts: Optional[List[DistrictCreate]] = None
    readings: Optional[List[ReadingCreate]] = None
    incidents: Optional[List[IncidentCreate]] = None
    correlations: Optional[List[CorrelationCreate]] = None


# ---------- Graph (Frontend үшін) ----------
class GraphNode(BaseModel):
    id: int
    type: str            # "incident"
    incident_type: str
    severity: str
    district_name: str
    lat: float
    lng: float
    triggered_at: datetime


class GraphEdge(BaseModel):
    source: int
    target: int
    weight: float
    relation_type: Optional[str]
    explanation: Optional[str]


class GraphResponse(BaseModel):
    nodes: List[GraphNode]
    edges: List[GraphEdge]
