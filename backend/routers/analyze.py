from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
import models
import schemas
from ai_analysis import analyze_districts, AIAnalysisError

router = APIRouter(prefix="/analyze", tags=["analyze"])


def _readings_to_dicts(readings: list[models.Reading]) -> list[dict]:
    return [
        {
            "district_name": r.district.name if r.district else None,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            "temperature": r.temperature,
            "water_demand": r.water_demand,
            "water_pressure": r.water_pressure,
            "metric_type": r.metric_type,
            "value": r.value,
        }
        for r in readings
    ]


def _districts_to_dicts(districts: list[models.District]) -> list[dict]:
    return [{"name": d.name, "lat": d.lat, "lng": d.lng} for d in districts]


@router.post("/run", response_model=dict)
def run_analysis(
    since_hours: Optional[int] = Query(
        24, description="Соңғы N сағаттың readings-ін ғана талдау (әдепкі 24)"
    ),
    district: Optional[str] = Query(
        None, description="Тек осы аймақтың деректерін талдау (аты бойынша)"
    ),
    db: Session = Depends(get_db),
):
    """
    Дерекқордағы districts + readings жинап, DeepSeek-ке жібереді.
    Модель қайтарған incidents/correlations нәтижесін дерекқорға сақтайды.

    Ереже негізінде емес — шешімді толығымен DeepSeek қабылдайды.
    """
    districts_q = db.query(models.District)
    if district:
        districts_q = districts_q.filter(models.District.name == district)
    districts = districts_q.all()

    if not districts:
        raise HTTPException(
            status_code=400,
            detail="Дерекқорда districts жоқ. Алдымен /ingest арқылы districts жіберіңіз.",
        )

    readings_q = db.query(models.Reading).join(models.District)
    if district:
        readings_q = readings_q.filter(models.District.name == district)
    if since_hours:
        cutoff = datetime.utcnow() - timedelta(hours=since_hours)
        readings_q = readings_q.filter(models.Reading.timestamp >= cutoff)

    readings = readings_q.order_by(models.Reading.timestamp.asc()).all()

    if not readings:
        return {
            "status": "ok",
            "message": "Талдауға readings табылмады (уақыт аралығын кеңейтіп көріңіз).",
            "incidents_created": 0,
            "correlations_created": 0,
        }

    try:
        result = analyze_districts(
            districts=_districts_to_dicts(districts),
            readings=_readings_to_dicts(readings),
        )
    except AIAnalysisError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    district_by_name = {d.name: d for d in districts}
    created_incidents: list[models.Incident] = []

    for item in result.get("incidents", []):
        d_name = item.get("district_name")
        target_district = district_by_name.get(d_name)
        if not target_district:
            # DeepSeek берілмеген district атауын қайтарса, оны елемей өтеміз
            continue

        triggered_at_raw = item.get("triggered_at")
        try:
            triggered_at = (
                datetime.fromisoformat(triggered_at_raw)
                if triggered_at_raw
                else datetime.utcnow()
            )
        except ValueError:
            triggered_at = datetime.utcnow()

        incident = models.Incident(
            district_id=target_district.id,
            type=item.get("type", "unknown"),
            severity=item.get("severity", "low"),
            description=item.get("description"),
            triggered_at=triggered_at,
        )
        db.add(incident)
        created_incidents.append(incident)

    db.commit()
    for incident in created_incidents:
        db.refresh(incident)

    correlations_created = 0
    for corr in result.get("correlations", []):
        src_idx = corr.get("source_index")
        tgt_idx = corr.get("target_index")

        if (
            src_idx is None
            or tgt_idx is None
            or not (0 <= src_idx < len(created_incidents))
            or not (0 <= tgt_idx < len(created_incidents))
        ):
            continue

        db.add(
            models.Correlation(
                source_incident_id=created_incidents[src_idx].id,
                target_incident_id=created_incidents[tgt_idx].id,
                weight=corr.get("weight", 0.5),
                relation_type=corr.get("relation_type"),
                explanation=corr.get("explanation"),
            )
        )
        correlations_created += 1

    db.commit()

    return {
        "status": "ok",
        "incidents_created": len(created_incidents),
        "correlations_created": correlations_created,
        "incidents": [
            schemas.IncidentOut(
                id=i.id,
                district_id=i.district_id,
                district_name=i.district.name if i.district else None,
                type=i.type,
                severity=i.severity,
                description=i.description,
                triggered_at=i.triggered_at,
                lat=i.district.lat if i.district else None,
                lng=i.district.lng if i.district else None,
            )
            for i in created_incidents
        ],
  }
