from cartia_shared import SearchRequest, SearchResponse
from fastapi import APIRouter, Depends

from ..core.db import SessionDep
from ..core.deps import require_internal_token
from ..services.retrieval import hybrid_search

router = APIRouter(
    prefix="/search",
    tags=["search"],
    dependencies=[Depends(require_internal_token)],
)


@router.post("", response_model=SearchResponse)
async def search(payload: SearchRequest, session: SessionDep) -> SearchResponse:
    return await hybrid_search(session, payload)
