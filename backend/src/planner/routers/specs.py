from fastapi import APIRouter

from .. import schemas
from ..services import spec_parser_service


router = APIRouter(prefix="/spec", tags=["Spec Parser"])


@router.post(
    "/parse",
    response_model=schemas.SpecParseResponse,
)
def parse_spec(payload: schemas.SpecParseRequest) -> schemas.SpecParseResponse:
    result = spec_parser_service.parse_spec(payload.spec_text)
    return schemas.SpecParseResponse(**result)

