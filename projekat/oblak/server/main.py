from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from db import Base, engine
from routes.admin import router as admin_router
from routes.auth import router as auth_router
from routes.functions import router as functions_router
from routes.invoke import router as invoke_router

from models.analysis import AnalysisResult # noqa: F401

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Oblak", description="Serverless Python execution platform", version="0.1.0")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


app.include_router(auth_router)
app.include_router(functions_router)
app.include_router(invoke_router)
app.include_router(admin_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
