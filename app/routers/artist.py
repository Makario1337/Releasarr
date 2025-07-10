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
        
        
@router.get("/artist")
def show_artists(request: Request, db: Session = Depends(get_db)):
    artists = db.query(Artist).all()
    return templates.TemplateResponse("artist.html", {"request": request, "artists": artists})


@router.post("/artist/add-artist")
def add_artist(name: str = Form(...), db: Session = Depends(get_db)):
    db.add(Artist(Name=name))
    db.commit()
    return RedirectResponse("/artist", status_code=303)

@router.post("/artist/{artist_id}/delete-artist")
def delete_artist(artist_id: int, db: Session = Depends(get_db)):
    artist = db.query(Artist).filter(Artist.Id == artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    db.delete(artist)
    db.commit()
    return RedirectResponse("/artist", status_code=303)