from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from ..models import Artist
from ..db import SessionLocal

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/")
def show_artists(request: Request, db: Session = Depends(get_db)):
    artists = db.query(Artist).all()
    return templates.TemplateResponse(
        "index.html", {"request": request, "artists": artists}
    )
