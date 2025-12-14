from fastapi import Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db


class PaginationParams:
    def __init__(
        self,
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
    ):
        self.page = page
        self.page_size = page_size


def get_db_session(db: Session = Depends(get_db)) -> Session:
    return db
