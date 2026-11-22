from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from src.geography.contracts import IntersectionView

router=APIRouter(prefix="/api/v1/intersections",tags=["intersections"])

def view(row):
    return IntersectionView(code=row.code,name=row.name,district=row.district,
        latitude=row.latitude,longitude=row.longitude,enabled=row.enabled,
        has_coordinates=row.latitude is not None and row.longitude is not None)

@router.get("",response_model=list[IntersectionView])
async def intersections(request: Request,include_disabled: bool=False,
                        district: str | None=Query(None,min_length=2,max_length=120),
                        with_coordinates: bool | None=None):
    try:
        rows=await run_in_threadpool(request.app.state.geography.store.list,
            include_disabled,district,with_coordinates)
        return [view(row) for row in rows]
    except SQLAlchemyError:
        raise HTTPException(503,"geography_unavailable") from None

@router.get("/{code}",response_model=IntersectionView)
async def intersection(code: str,request: Request,include_disabled: bool=False):
    try:
        row=await run_in_threadpool(request.app.state.geography.store.get,code,include_disabled)
    except SQLAlchemyError:
        raise HTTPException(503,"geography_unavailable") from None
    if row is None:
        raise HTTPException(404,"intersection_not_found")
    return view(row)
