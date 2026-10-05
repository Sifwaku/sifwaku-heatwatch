"""
SIFWAKU HeatWatch — FastAPI application entry point.
Phase 1–2: API discovery, connectivity testing, normalization, storage, baseline risk.
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from backend.api.routes import router
from backend.database.session import init_db

app = FastAPI(
    title="SIFWAKU HeatWatch",
    description=(
        "Zambia weather dashboard with provider-supplied current conditions, forecasts, "
        "historical context, and an illustrative heat-risk screen. Weather values are estimates, "
        "not local station readings or official warnings."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")

# Frontend static files
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")


@app.on_event("startup")
def on_startup():
    # Ensure data directory exists for SQLite
    Path("data").mkdir(exist_ok=True)
    init_db()


@app.get("/")
async def index():
    # Make the public entry point useful immediately: visitors land on weather.
    return RedirectResponse(url="/dashboard", status_code=307)


@app.get("/api-lab")
async def api_lab_page():
    p = FRONTEND_DIR / "api-lab.html"
    if p.exists():
        return FileResponse(p)
    return {"error": "api-lab.html not found"}


@app.get("/dashboard")
async def dashboard_page():
    p = FRONTEND_DIR / "dashboard.html"
    if p.exists():
        return FileResponse(p)
    return {"error": "dashboard.html not found"}


@app.get("/history")
async def history_page():
    p = FRONTEND_DIR / "history.html"
    if p.exists():
        return FileResponse(p)
    return {"error": "history.html not found"}


@app.get("/api-sources-page")
async def api_sources_page():
    p = FRONTEND_DIR / "api-sources.html"
    if p.exists():
        return FileResponse(p)
    return {"error": "api-sources.html not found"}
