from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.models.schemas import HealthResponse
from app.services.blockchain import blockchain_service
from app.routers import markets, evidence, predictions, users


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup — init database
    from app.services.database import init_db
    init_db()

    if not settings.use_mock_mirofish:
        from app.services.mirofish_scheduler import mirofish_scheduler
        mirofish_scheduler.start()
    yield
    # Shutdown
    if not settings.use_mock_mirofish:
        from app.services.mirofish_scheduler import mirofish_scheduler
        mirofish_scheduler.stop()


app = FastAPI(
    title="PDX Prediction Market API",
    description="Backend API for the PDX evidence-driven prediction market",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(markets.router)
app.include_router(evidence.router)
app.include_router(predictions.router)
app.include_router(users.router)


@app.get("/api/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        status="ok",
        chain_connected=blockchain_service.is_connected,
        market_address=settings.pdx_market_address or "not configured",
    )
