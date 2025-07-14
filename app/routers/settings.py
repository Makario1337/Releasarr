# app/routers/settings.py 
from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from ..db import SessionLocal
from ..models import Config

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

ALLOWED_KEYS = ["DiscogsApiKey", "SpotifyApiKey", "LibraryFolderPath", "ImportFolderPath"]

@router.get("/settings", response_class=templates.TemplateResponse)
async def settings_page(request: Request, db: Session = Depends(get_db)):

    configs = {c.Key: c for c in db.query(Config).filter(Config.Key.in_(ALLOWED_KEYS)).all()}

    settings = []
    for key in ALLOWED_KEYS:
        if key in configs:
            settings.append(configs[key])
        else:
            settings.append(Config(Key=key, Value=""))

    return templates.TemplateResponse("settings.html", {"request": request, "configs": settings})

@router.post("/settings")
async def save_setting(
    key: str = Form(...),
    value: str = Form(...),
    db: Session = Depends(get_db)
):
    if key not in ALLOWED_KEYS:
        raise HTTPException(status_code=400, detail="Invalid configuration key.")

    existing = db.query(Config).filter(Config.Key == key).first()
    if existing:
        existing.Value = value
    else:
        db.add(Config(Key=key, Value=value))
    db.commit()
    return RedirectResponse("/settings", status_code=303)

@router.post("/settings/delete")
async def delete_setting(
    key: str = Form(...),
    db: Session = Depends(get_db)
):
    existing = db.query(Config).filter(Config.Key == key).first()
    if existing:
        db.delete(existing)
    db.commit()
    return RedirectResponse("/settings", status_code=303)