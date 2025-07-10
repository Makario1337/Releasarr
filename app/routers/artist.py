from fastapi import APIRouter, Request, Form, Depends, HTTPException, Query
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

@router.get("/artist/get-artist/{artist_id}")
def show_releases_by_artist(
    artist_id: int,
    request: Request,
    search: str = Query("", alias="search"),
    sort_by: str = Query("title", alias="sort_by"),
    db: Session = Depends(get_db),
):
    artist = db.query(Artist).filter_by(Id=artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")

    releases = db.query(Release).filter_by(ArtistId=artist_id)
    if search:
        releases = releases.filter(Release.Title.ilike(f"%{search}%"))
    releases = releases.all()

    sort_map = {
        "title": lambda r: (r.Title or "").lower(),
        "year": lambda r: -(r.Year or 0),
        "tracks": lambda r: -(r.TrackFileCount or 0),
    }
    releases.sort(key=sort_map.get(sort_by, sort_map["title"]))

    return templates.TemplateResponse(
        "artist.html",
        {
            "request": request,
            "artist": artist,
            "releases": releases,
            "search": search,
            "sort_by": sort_by,
            "artist_id": artist_id,
        },
    )

@router.post("/artist/add-artist")
def add_artist(name: str = Form(...), db: Session = Depends(get_db)):
    db.add(Artist(Name=name))
    db.commit()
    return RedirectResponse("/", status_code=303)

@router.post("/artist/delete-artist/{artist_id}")
def delete_artist(artist_id: int, db: Session = Depends(get_db)):
    artist = db.query(Artist).filter_by(Id=artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    db.delete(artist)
    db.commit()
    return RedirectResponse("/", status_code=303)

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
    artist = db.query(Artist).filter_by(Id=artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")

    def norm(val): return val.strip() if val and val.strip() else None

    artist.AppleMusicId = norm(applemusic_id)
    artist.DeezerId = norm(deezer_id)
    artist.DiscogsId = norm(discogs_id)
    artist.MusicbrainzId = norm(musicbrainz_id)
    artist.SpotifyId = norm(spotify_id)
    artist.TidalId = norm(tidal_id)

    db.commit()
    return RedirectResponse(f"/artist/get-artist/{artist_id}", status_code=303)

@router.post('/artist/update-cover/{artist_id}')
def update_artist_cover(artist_id: int, cover_url: str = Form(...), db: Session = Depends(get_db)):
    artist = db.query(Artist).filter_by(Id=artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    artist.ImageUrl = cover_url
    db.commit()
    return RedirectResponse(f"/artist/get-artist/{artist_id}", status_code=303)
