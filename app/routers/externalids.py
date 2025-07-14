# app/routers/externalids.py
from fastapi import APIRouter, Depends, HTTPException, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from fastapi.templating import Jinja2Templates
from ..models import Artist
from ..db import SessionLocal
from ..utils.release_utils import update_release_tracks_if_changed

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

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