from contextlib import asynccontextmanager
from statistics import median

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.models import Hotel, JobResult, RateObservation
from app.settings import Settings, get_settings
from config.loader import load_hotels
from jobs.daily_rates import run_daily_rates
from storage.factory import get_store

templates = Jinja2Templates(directory="app/templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    store = get_store(settings)
    if settings.demo_mode and not store.read_all():
        # A recognizable first run without mutating Google Sheets.
        if settings.storage_backend == "local":
            await run_daily_rates(settings)
    yield


app = FastAPI(title="Luxury Hotel Pricing Intelligence System", version="0.1.0", lifespan=lifespan)


def filtered_rates(
    settings: Settings,
    hotel_id: str | None = None,
    size_band: str | None = None,
    lead_days: int | None = None,
) -> list[RateObservation]:
    rows = get_store(settings).read_all()
    if hotel_id:
        rows = [r for r in rows if r.hotel_id == hotel_id]
    if size_band:
        rows = [r for r in rows if r.size_band == size_band]
    if lead_days is not None:
        rows = [r for r in rows if r.lead_days == lead_days]
    return rows


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={})


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/api/hotels", response_model=list[Hotel])
def hotels():
    return load_hotels()


@app.get("/api/rates", response_model=list[RateObservation])
def rates(
    hotel_id: str | None = None,
    size_band: str | None = None,
    lead_days: int | None = Query(default=None, ge=0),
    settings: Settings = Depends(get_settings),
):
    return filtered_rates(settings, hotel_id, size_band, lead_days)


@app.get("/api/market-summary")
def market_summary(
    hotel_id: str | None = None,
    size_band: str | None = None,
    lead_days: int | None = Query(default=None, ge=0),
    settings: Settings = Depends(get_settings),
):
    rows = filtered_rates(settings, hotel_id, size_band, lead_days)
    twd = [float(r.total_twd) for r in rows if r.total_twd is not None]
    per_sqm = [float(r.price_per_sqm) for r in rows if r.price_per_sqm is not None]
    cpi = [float(r.cpi_adjusted_twd) for r in rows if r.cpi_adjusted_twd is not None]
    return {
        "observations": len(rows),
        "hotels": len({r.hotel_id for r in rows}),
        "median_adr_twd": round(median(twd), 0) if twd else None,
        "median_per_sqm_twd": round(median(per_sqm), 0) if per_sqm else None,
        "median_cpi_adjusted_twd": round(median(cpi), 0) if cpi else None,
        "demo_mode": settings.demo_mode,
    }


@app.post("/jobs/daily-rates", response_model=JobResult)
async def daily_job(
    x_job_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
):
    if settings.job_token and x_job_token != settings.job_token:
        raise HTTPException(status_code=401, detail="Invalid job token")
    return await run_daily_rates(settings)
