from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc
from ..models import Artist, Release
from ..db import SessionLocal
from typing import List

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# (vorherige Künstler-Routen hier...)

@router.get("/releases")
def show_releases(request: Request, db: Session = Depends(get_db)):
    releases = db.query(Release).order_by(
    case((Release.year == None, 1), else_=0),  # None years last
    desc(Release.year)
    ).all()
    artists = db.query(Artist).all()
    return templates.TemplateResponse("releases.html", {"request": request, "releases": releases, "artists": artists})

@router.post("/releases")
def add_release(title: str = Form(...), artist_id: int = Form(...), db: Session = Depends(get_db)):
    release = Release(title=title, artist_id=artist_id)
    db.add(release)
    db.commit()
    return RedirectResponse("/releases", status_code=303)

@router.post("/releases/{release_id}/delete")
def delete_release(release_id: int, db: Session = Depends(get_db)):
    release = db.query(Release).filter(Release.id == release_id).first()
    if not release:
        raise HTTPException(status_code=404, detail="Release not found")
    artist_id = release.artist_id
    db.delete(release)
    db.commit()
    return RedirectResponse(f"/artists/{artist_id}", status_code=303)

@router.post("/releases/delete-multiple")
def delete_multiple_releases(
    release_ids: List[int] = Form(...),
    db: Session = Depends(get_db)
):
    releases = db.query(Release).filter(Release.id.in_(release_ids)).all()
    
    if not releases:
        raise HTTPException(status_code=404, detail="No releases found")

    artist_ids = {r.artist_id for r in releases}
    for release in releases:
        db.delete(release)
    db.commit()

    artist_id = artist_ids.pop() if artist_ids else None
    return RedirectResponse(f"/artists/{artist_id}" if artist_id else "/artists", status_code=303)