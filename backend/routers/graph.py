from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Optional

from database import get_db
import models
import schemas

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("", response_model=schemas.GraphResponse)
def get_graph(
    min_weight: Optional[float] = 0.0,
    db: Session = Depends(get_db),
):
    """
    Incident-тердің граф түрі: nodes = incidents, edges = correlations.
    Адам 3 (Frontend) осыны graph_view.js-те тікелей рендерлей алады.
    min_weight арқылы әлсіз байланыстарды сүзуге болады (демо кезінде шу азайту).
    """
    incidents = db.query(models.Incident).all()
    correlations = db.query(models.Correlation).filter(
        models.Correlation.weight >= min_weight
    ).all()

    nodes = [
        schemas.GraphNode(
            id=i.id,
            type="incident",
            incident_type=i.type,
            severity=i.severity,
            district_name=i.district.name if i.district else "unknown",
            lat=i.district.lat if i.district else 0.0,
            lng=i.district.lng if i.district else 0.0,
            triggered_at=i.triggered_at,
        )
        for i in incidents
    ]

    edges = [
        schemas.GraphEdge(
            source=c.source_incident_id,
            target=c.target_incident_id,
            weight=c.weight,
            relation_type=c.relation_type,
            explanation=c.explanation,
        )
        for c in correlations
    ]

    return schemas.GraphResponse(nodes=nodes, edges=edges)
