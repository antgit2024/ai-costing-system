from collections import defaultdict
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..dependencies import PaginationParams, get_db_session

router = APIRouter(tags=["Packages"])


def _build_tree(packages: List[models.CostPackage]) -> List[schemas.PackageRead]:
    by_id: Dict[str, schemas.PackageRead] = {}
    children_map: Dict[Optional[str], List[schemas.PackageRead]] = defaultdict(list)

    for pkg in packages:
        package_schema = schemas.PackageRead.from_orm(pkg)
        package_schema.children = []
        by_id[package_schema.id] = package_schema
        children_map[pkg.parent_package_id].append(package_schema)

    def attach_children(node: schemas.PackageRead):
        node.children = children_map.get(node.id, [])
        for child in node.children:
            attach_children(child)

    roots = children_map.get(None, []) + children_map.get("", [])
    for root in roots:
        attach_children(root)
    return roots


@router.get("/packages", response_model=schemas.PaginatedPackageResponse)
def list_packages(
    initiative_id: Optional[str] = None,
    owner_id: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db_session),
):
    query = db.query(models.CostPackage).filter(models.CostPackage.is_archived.is_(False))

    if initiative_id:
        query = query.filter(models.CostPackage.initiative_id == initiative_id)
    if owner_id:
        query = query.filter(models.CostPackage.owner_id == owner_id)
    if status_filter:
        query = query.filter(models.CostPackage.status == status_filter)

    total = query.count()
    items = (
        query.order_by(models.CostPackage.created_at.desc())
        .offset((pagination.page - 1) * pagination.page_size)
        .limit(pagination.page_size)
        .all()
    )

    return schemas.PaginatedPackageResponse(
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        items=items,
    )


@router.get("/packages/tree", response_model=List[schemas.PackageRead])
def package_tree(
    initiative_id: str = Query(..., description="Initiative id for the package tree"),
    db: Session = Depends(get_db_session),
):
    packages = (
        db.query(models.CostPackage)
        .filter(
            models.CostPackage.initiative_id == initiative_id,
            models.CostPackage.is_archived.is_(False),
        )
        .order_by(models.CostPackage.created_at.asc())
        .all()
    )
    return _build_tree(packages)


@router.post(
    "/packages",
    response_model=schemas.PackageRead,
    status_code=status.HTTP_201_CREATED,
)
def create_package(payload: schemas.PackageCreate, db: Session = Depends(get_db_session)):
    initiative = db.get(models.CostInitiative, payload.initiative_id)
    if not initiative or initiative.is_archived:
        raise HTTPException(status_code=400, detail="Initiative does not exist")

    new_package = models.CostPackage(**payload.dict())
    db.add(new_package)
    db.commit()
    db.refresh(new_package)
    return new_package


@router.get("/packages/{package_id}", response_model=schemas.PackageRead)
def get_package(package_id: str, db: Session = Depends(get_db_session)):
    package = db.get(models.CostPackage, package_id)
    if not package or package.is_archived:
        raise HTTPException(status_code=404, detail="Package not found")
    return package


@router.put("/packages/{package_id}", response_model=schemas.PackageRead)
def update_package(
    package_id: str,
    payload: schemas.PackageUpdate,
    db: Session = Depends(get_db_session),
):
    package = db.get(models.CostPackage, package_id)
    if not package or package.is_archived:
        raise HTTPException(status_code=404, detail="Package not found")

    update_data = payload.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(package, key, value)

    db.commit()
    db.refresh(package)
    return package


@router.delete("/packages/{package_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_package(package_id: str, db: Session = Depends(get_db_session)):
    package = db.get(models.CostPackage, package_id)
    if not package or package.is_archived:
        raise HTTPException(status_code=404, detail="Package not found")

    package.is_archived = True
    db.commit()
    return None
