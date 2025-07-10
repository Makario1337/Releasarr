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
    return templates.TemplateResponse(
        "artist.html", {"request": request, "artists": artists}
    )


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


###############################################################
# External Services for Artist Information
###############################################################


# Deezer Integration
@router.post("/artist/{artist_id}/set-deezer_id")
def set_deezer_id(
    artist_id: int, deezer_id: str = Form(...), db: Session = Depends(get_db)
):
    artist = db.query(Artist).filter(Artist.Id == artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    artist.DeezerId = deezer_id
    db.commit()
    return RedirectResponse(f"/release/{artist_id}/", status_code=303)


# Spotify Integration
@router.post("/artist/{artist_id}/set-spotify_id")
def set_spotify_id(
    artist_id: int, spotify_id: str = Form(...), db: Session = Depends(get_db)
):
    artist = db.query(Artist).filter(Artist.Id == artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    artist.SpotifyId = spotify_id
    db.commit()
    return RedirectResponse(f"/release/{artist_id}/", status_code=303)


# Discogs Integration
@router.post("/artist/{artist_id}/set-discogs_id")
def set_discogs_id(
    artist_id: int, discogs_id: str = Form(...), db: Session = Depends(get_db)
):
    artist = db.query(Artist).filter(Artist.Id == artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    artist.DiscogsId = discogs_id
    db.commit()
    return RedirectResponse(f"/release/{artist_id}/", status_code=303)


# MusicBrainz Integration
@router.post("/artist/{artist_id}/set-musicbrainz_id")
def set_musicbrainz_id(
    artist_id: int,
    musicbrainz_id: str = Form(...),
    db: Session = Depends(get_db)
):
    artist = db.query(Artist).filter(Artist.Id == artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    
    artist.MusicbrainzId = musicbrainz_id  # ✅ Match your SQLAlchemy model
    db.commit()
    return RedirectResponse(f"/release/{artist_id}/", status_code=303)


# Apple Music Integration
@router.post("/artist/{artist_id}/set-applemusic_id")
def set_apple_music_id(
    artist_id: int, applemusic_id: str = Form(...), db: Session = Depends(get_db)
):
    artist = db.query(Artist).filter(Artist.Id == artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    artist.AppleMusicId = applemusic_id
    db.commit()
    return RedirectResponse(f"/release/{artist_id}/", status_code=303)


# Tidal Integration
@router.post("/artist/{artist_id}/set-tidal_id")
def set_tidal_id(
    artist_id: int, tidal_id: str = Form(...), db: Session = Depends(get_db)
):
    artist = db.query(Artist).filter(Artist.Id == artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    artist.TidalId = tidal_id
    db.commit()
    return RedirectResponse(f"/release/{artist_id}/", status_code=303)
