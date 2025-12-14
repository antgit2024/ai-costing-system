import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..dependencies import get_db_session
from ..integrations import benchmark_client

router = APIRouter(tags=["Benchmarks"])

logger = logging.getLogger(__name__)


@router.get("/benchmarks/suggest")
def suggest_benchmarks(
    category: str = Query("materials"),
    metric: str = Query("unit_cost"),
    db: Session = Depends(get_db_session),
):
    client = benchmark_client.get_client()
    try:
        data = client.fetch(category, metric)
    except RuntimeError:
        logger.warning("Benchmark provider unavailable, returning fallback response.")
        data = {
            "category": category,
            "metric": metric,
            "items": [],
            "source": "fallback",
        }
    return data


@router.get("/benchmarks/favorites", response_model=list[schemas.BenchmarkFavoriteRead])
def list_benchmark_favorites(user_id: str = Query(...), db: Session = Depends(get_db_session)):
    favorites = (
        db.query(models.BenchmarkFavorite)
        .filter(models.BenchmarkFavorite.user_id == user_id)
        .order_by(models.BenchmarkFavorite.created_at.desc())
        .all()
    )
    return favorites


@router.post(
    "/benchmarks/favorites",
    response_model=schemas.BenchmarkFavoriteRead,
    status_code=status.HTTP_201_CREATED,
)
def create_benchmark_favorite(
    payload: schemas.BenchmarkFavoriteCreate,
    db: Session = Depends(get_db_session),
):
    existing = (
        db.query(models.BenchmarkFavorite)
        .filter(
            models.BenchmarkFavorite.user_id == payload.user_id,
            models.BenchmarkFavorite.benchmark_key == payload.benchmark_key,
        )
        .first()
    )
    if existing:
        db.delete(existing)
        db.flush()
    favorite = models.BenchmarkFavorite(
        benchmark_key=payload.benchmark_key,
        user_id=payload.user_id,
        payload=payload.payload,
    )
    db.add(favorite)
    db.commit()
    db.refresh(favorite)
    return favorite


@router.delete("/benchmarks/favorites/{favorite_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_benchmark_favorite(
    favorite_id: str,
    user_id: str = Query(...),
    db: Session = Depends(get_db_session),
):
    favorite = db.get(models.BenchmarkFavorite, favorite_id)
    if not favorite or favorite.user_id != user_id:
        raise HTTPException(status_code=404, detail="Favorite not found")
    db.delete(favorite)
    db.commit()
    return None
