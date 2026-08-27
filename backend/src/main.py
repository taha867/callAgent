import logging.config
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.exceptions import CallAgentError, ErrorResponse, status_for
from src.middlewares import register_middlewares

_logging_ini = Path(__file__).resolve().parent.parent / "logging.ini"
if _logging_ini.exists():
    logging.config.fileConfig(_logging_ini, disable_existing_loggers=False)

app = FastAPI(title="Insurance Outbound AI Call Center")
register_middlewares(app)


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
