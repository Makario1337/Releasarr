from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from ..models import Release, Artist
from ..db import SessionLocal

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/release/{artist_id}/")
def show_releases_by_artist(
    artist_id: int, request: Request, db: Session = Depends(get_db)
):
    releases = db.query(Release).filter(Release.ArtistId == artist_id).all()
    artist = db.query(Artist).filter(Artist.Id == artist_id).first()
    return templates.TemplateResponse(
        "release.html", {"request": request, "releases": releases, "artist": artist}
    )
