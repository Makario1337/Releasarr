from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from ..models import Artist, Release
from ..db import SessionLocal
import requests

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/artists")
def show_artists(request: Request, db: Session = Depends(get_db)):
    artists = db.query(Artist).all()
    return templates.TemplateResponse("artists.html", {"request": request, "artists": artists})

@router.post("/artists")
def add_artist(name: str = Form(...), db: Session = Depends(get_db)):
    db.add(Artist(name=name))
    db.commit()
    return RedirectResponse("/artists", status_code=303)

@router.get("/artists/{artist_id}")
def artist_detail(artist_id: int, request: Request, db: Session = Depends(get_db)):
    artist = db.query(Artist).filter(Artist.id == artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    releases = db.query(Release).filter(Release.artist_id == artist_id).all()
    return templates.TemplateResponse("artist_detail.html", {"request": request, "artist": artist, "releases": releases})

@router.post("/artists/{artist_id}/delete")
def delete_artist(artist_id: int, db: Session = Depends(get_db)):
    artist = db.query(Artist).filter(Artist.id == artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    db.delete(artist)
    db.commit()
    return RedirectResponse("/artists", status_code=303)



@router.post("/artists/{artist_id}/mb_releases")
def import_mb_releases(artist_id: int, db: Session = Depends(get_db)):
    artist = db.query(Artist).filter(Artist.id == artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")

    # Search MusicBrainz for artist MBID by name
    search_url = "https://musicbrainz.org/ws/2/artist/"
    params = {"query": artist.name, "fmt": "json"}
    response = requests.get(search_url, params=params)
    data = response.json()

    if not data.get("artists"):
        raise HTTPException(status_code=404, detail="Artist not found on MusicBrainz")

    mb_artist = data["artists"][0]
    mbid = mb_artist["id"]

    # Get releases by MBID
    releases_url = f"https://musicbrainz.org/ws/2/release/"
    params = {"artist": mbid, "fmt": "json", "limit": 50}
    releases_resp = requests.get(releases_url, params=params)
    releases_data = releases_resp.json()

    existing_titles = {r.title for r in db.query(Release).filter(Release.artist_id == artist_id).all()}

    for release in releases_data.get("releases", []):
        title = release.get("title")
        date = release.get("date", "")
        year = int(date[:4]) if date else None

        if title not in existing_titles:
            new_release = Release(title=title, year=year, artist_id=artist_id)
            db.add(new_release)

    db.commit()
    return RedirectResponse(f"/artists/{artist_id}", status_code=303)