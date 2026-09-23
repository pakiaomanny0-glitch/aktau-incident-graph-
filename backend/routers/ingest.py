from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
import models
import schemas

router = APIRouter(prefix="/ingest", tags=["ingest"])


def get_or_create_district(db: Session, name: str) -> models.District:
    district = db.query(models.District).filter(models.District.name == name).first()
    if not district:
        raise HTTPException(
            status_code=400,
            detail=f"District '{name}' табылмады. Алдымен districts тізімін жіберіңіз."
        )
    return district


@router.post("", response_model=dict)
def ingest_data(payload: schemas.IngestPayload, db: Session = Depends(get_db)):
    """
    Адам 2 (Data) осы endpoint-ке districts.json, synthetic_readings.py,
    correlation_engine.py нәтижесін бір payload ретінде жібере алады.
    Барлық өрістер optional — тек бар болғанын ғана жібереді.
    """
    counts = {"districts": 0, "readings": 0, "incidents": 0, "correlations": 0}

    # 1. Districts бірінші жүктелуі керек (readings/incidents соған сүйенеді)
    if payload.districts:
        for d in payload.districts:
            existing = db.query(models.District).filter(models.District.name == d.name).first()
            if not existing:
                db.add(models.District(name=d.name, lat=d.lat, lng=d.lng))
                counts["districts"] += 1
        db.commit()

    # 2. Readings
    if payload.readings:
        for r in payload.readings:
            district = get_or_create_district(db, r.district_name)
            db.add(models.Reading(
                district_id=district.id,
                timestamp=r.timestamp,
                temperature=r.temperature,
                water_demand=r.water_demand,
                water_pressure=r.water_pressure,
                metric_type=r.metric_type,
                value=r.value,
            ))
            counts["readings"] += 1
        db.commit()

    # 3. Incidents
    if payload.incidents:
        for i in payload.incidents:
            district = get_or_create_district(db, i.district_name)
            db.add(models.Incident(
                district_id=district.id,
                type=i.type,
                severity=i.severity,
                description=i.description,
                triggered_at=i.triggered_at,
            ))
            counts["incidents"] += 1
        db.commit()

    # 4. Correlations (incident_id-лар frontend/data жағында белгілі болуы керек)
    if payload.correlations:
        for c in payload.correlations:
            src = db.query(models.Incident).get(c.source_incident_id)
            tgt = db.query(models.Incident).get(c.target_incident_id)
            if not src or not tgt:
                raise HTTPException(
                    status_code=400,
                    detail=f"Incident {c.source_incident_id} немесе {c.target_incident_id} табылмады."
                )
            db.add(models.Correlation(
                source_incident_id=c.source_incident_id,
                target_incident_id=c.target_incident_id,
                weight=c.weight,
                relation_type=c.relation_type,
                explanation=c.explanation,
            ))
            counts["correlations"] += 1
        db.commit()

    return {"status": "ok", "inserted": counts}


@router.post("/districts", response_model=schemas.DistrictOut)
def ingest_single_district(district: schemas.DistrictCreate, db: Session = Depends(get_db)):
    """Жалғыз district қосу (Data адамының бастапқы setup кезеңіне ыңғайлы)."""
    existing = db.query(models.District).filter(models.District.name == district.name).first()
    if existing:
        return existing
    obj = models.District(**district.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj
