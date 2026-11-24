from fastapi import APIRouter,Request

router=APIRouter(prefix="/api/v1/validation",tags=["validation"])

@router.get("/status")
async def status(request: Request):
    return request.app.state.validation.status()
