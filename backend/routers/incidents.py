from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List

from database import get_db
import models
import schemas

router = APIRouter(prefix="/incidents", tags=["incidents"])


def _to_out(incident: models.Incident) -> schemas.IncidentOut:
    return schemas.IncidentOut(
        id=incident.id,
        district_id=incident.district_id,
        district_name=incident.district.name if incident.district else None,
        type=incident.type,
        severity=incident.severity,
        description=incident.description,
        triggered_at=incident.triggered_at,
        lat=incident.district.lat if incident.district else None,
        lng=incident.district.lng if incident.district else None,
    )


@router.get("", response_model=List[schemas.IncidentOut])
def list_incidents(
    district: Optional[str] = Query(None, description="Мкр атауы бойынша сүзгі"),
    severity: Optional[str] = Query(None, description="low | medium | high"),
    type: Optional[str] = Query(None, description="incident түрі бойынша сүзгі"),
    db: Session = Depends(get_db),
):
    """Frontend dashboard/карта үшін негізгі incident тізімі. Sүзгілер: аймақ, severity, type."""
    q = db.query(models.Incident)
    if district:
        q = q.join(models.District).filter(models.District.name == district)
    if severity:
        q = q.filter(models.Incident.severity == severity)
    if type:
        q = q.filter(models.Incident.type == type)

    incidents = q.order_by(models.Incident.triggered_at.desc()).all()
    return [_to_out(i) for i in incidents]


@router.get("/{incident_id}", response_model=schemas.IncidentOut)
def get_incident(incident_id: int, db: Session = Depends(get_db)):
    incident = db.query(models.Incident).get(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident табылмады")
    return _to_out(incident)


@router.post("", response_model=schemas.IncidentOut)
def create_incident(payload: schemas.IncidentCreate, db: Session = Depends(get_db)):
    """Қолмен немесе демо кезінде бір incident құру."""
    district = db.query(models.District).filter(models.District.name == payload.district_name).first()
    if not district:
        raise HTTPException(status_code=400, detail=f"District '{payload.district_name}' табылмады")

    incident = models.Incident(
        district_id=district.id,
        type=payload.type,
        severity=payload.severity,
        description=payload.description,
        triggered_at=payload.triggered_at,
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return _to_out(incident)
