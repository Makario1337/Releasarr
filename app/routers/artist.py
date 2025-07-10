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

################################################################
# Routers
################################################################

@router.get("/artist/get-artist/{artist_id}")
def show_releases_by_artist(
    artist_id: int, request: Request, db: Session = Depends(get_db)
):
    releases = db.query(Release).filter(Release.ArtistId == artist_id).all()
    artist = db.query(Artist).filter(Artist.Id == artist_id).first()
    return templates.TemplateResponse(
        "artist.html", 
        {
            "request": request,
            "releases": releases, 
            "artist": artist,
            "artist_id": artist_id,            
            }
    )

@router.post("/artist/add-artist")
def add_artist(name: str = Form(...), db: Session = Depends(get_db)):
    db.add(Artist(Name=name))
    db.commit()
    return RedirectResponse("/", status_code=303)

@router.post("/artist/delete-artist/{artist_id}")
def delete_artist(artist_id: int, db: Session = Depends(get_db)):
    artist = db.query(Artist).filter(Artist.Id == artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    db.delete(artist)
    db.commit()
    return RedirectResponse("/", status_code=303)

###############################################################
# Set External Services for Artist Information
###############################################################

@router.post("/artist/set-external-ids/{artist_id}")
def set_all_ids(
    artist_id: int,
    applemusic_id: str = Form(None),
    deezer_id: str = Form(None),
    discogs_id: str = Form(None),
    musicbrainz_id: str = Form(None),
    spotify_id: str = Form(None),
    tidal_id: str = Form(None),
    db: Session = Depends(get_db)
):
    artist = db.query(Artist).filter(Artist.Id == artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")

    def normalize(value: str | None) -> str | None:
        value = value.strip() if value else None
        return value or None

    artist.AppleMusicId = normalize(applemusic_id)
    artist.DeezerId = normalize(deezer_id)
    artist.DiscogsId = normalize(discogs_id)
    artist.MusicbrainzId = normalize(musicbrainz_id)
    artist.SpotifyId = normalize(spotify_id)
    artist.TidalId = normalize(tidal_id)

    db.commit()
    return RedirectResponse(f"/artist/get-artist/{artist_id}", status_code=303)