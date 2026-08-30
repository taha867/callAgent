import logging.config
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.actions.router import router as actions_router
from src.calls.router import router as calls_router
from src.claims.router import router as claims_router
from src.complaints.router import router as complaints_router
from src.database import get_db
from src.exceptions import CallAgentError, ErrorResponse, status_for
from src.middlewares import register_middlewares
from src.qa.router import router as qa_router
from src.reporting.router import router as reporting_router

_logging_ini = Path(__file__).resolve().parent.parent / "logging.ini"
if _logging_ini.exists():
    logging.config.fileConfig(_logging_ini, disable_existing_loggers=False)

app = FastAPI(title="Insurance Outbound AI Call Center")
register_middlewares(app)
app.include_router(claims_router, prefix="/claims", tags=["claims"])
# actions_router's own routes are "/{claim_id}/actions" and "/{claim_id}/escalations" —
# same /claims prefix as claims_router, per spec §27's "POST /claims/{claimId}/actions".
app.include_router(actions_router, prefix="/claims", tags=["actions"])
app.include_router(calls_router, prefix="/calls", tags=["calls"])
app.include_router(complaints_router, prefix="/complaints", tags=["complaints"])
app.include_router(reporting_router, prefix="/reporting", tags=["reporting"])
app.include_router(qa_router, prefix="/qa", tags=["qa"])


@app.exception_handler(CallAgentError)
async def handle_call_agent_error(request: Request, exc: CallAgentError) -> JSONResponse:
    return JSONResponse(
        status_code=status_for(exc),
        content=ErrorResponse(error=type(exc).__name__, detail=str(exc)).model_dump(),
    )


class HealthRead(BaseModel):
    status: str


@app.get("/health", response_model=HealthRead)
async def health(db: Annotated[AsyncSession, Depends(get_db)]) -> HealthRead:
    await db.execute(text("SELECT 1"))
    return HealthRead(status="ok")
