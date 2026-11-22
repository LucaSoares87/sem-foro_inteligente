from typing import Literal
from fastapi import APIRouter, HTTPException, Request
from src.decision.contracts import Comparison,SimulationScenario
from src.decision.engine import compare
from src.decision.service import eligibility,scenario_for,status

router=APIRouter(prefix="/api/v1/decision",tags=["decision"])

@router.get("/status")
async def get_status():
    return status()

@router.get("/demo",response_model=Comparison)
def demo(preset: Literal["balanced","asymmetric","surge","overload","empty"]="asymmetric"):
    return compare(scenario_for(preset))

@router.post("/simulate",response_model=Comparison)
def simulate(scenario: SimulationScenario):
    return compare(scenario)

@router.get("/sources/{source}/eligibility")
async def source_eligibility(source: str,request: Request):
    if source not in request.app.state.video.sessions:
        raise HTTPException(404,"source_not_registered")
    return eligibility(request.app.state.analytics,request.app.state.history,source)
