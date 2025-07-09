from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from ..models import Artist, Release
from ..db import SessionLocal
import requests
import json

# Load custom headers for requests (e.g., MusicBrainz User-Agent)
with open("headers.json") as f:
    headers = json.load(f)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Dependency: get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Show all artists
@router.get("/artists")
def show_artists(request: Request, db: Session = Depends(get_db)):
    artists = db.query(Artist).all()
    return templates.TemplateResponse("artists.html", {
        "request": request,
        "artists": artists
    })

# Add an artist
@router.post("/artists")
def add_artist(name: str = Form(...), db: Session = Depends(get_db)):
    db.add(Artist(name=name))
    db.commit()
    return RedirectResponse("/artists", status_code=303)

# Show a single artist and their releases
@router.get("/artists/{artist_id}")
def artist_detail(artist_id: int, request: Request, db: Session = Depends(get_db)):
    artist = db.query(Artist).filter(Artist.id == artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    return templates.TemplateResponse("artist_detail.html", {
        "request": request,
        "artist": artist,
        "releases": artist.releases  # Use the relationship instead of manual query
    })

# Delete an artist
@router.post("/artists/{artist_id}/delete")
def delete_artist(artist_id: int, db: Session = Depends(get_db)):
    artist = db.query(Artist).filter(Artist.id == artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    db.delete(artist)
    db.commit()
    return RedirectResponse("/artists", status_code=303)

# Import releases from MusicBrainz
@router.post("/artists/{artist_id}/mb_releases")
def import_mb_releases(artist_id: int, db: Session = Depends(get_db)):
    artist = db.query(Artist).filter(Artist.id == artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")

    # Search MusicBrainz for MBID
    search_url = "https://musicbrainz.org/ws/2/artist/"
    search_params = {"query": artist.name, "fmt": "json"}
    search_resp = requests.get(search_url, params=search_params, headers=headers)
    search_data = search_resp.json()

    if not search_data.get("artists"):
        raise HTTPException(status_code=404, detail="Artist not found on MusicBrainz")

    mbid = search_data["artists"][0]["id"]

    # Fetch releases by MBID
    releases_url = "https://musicbrainz.org/ws/2/release/"
    releases_params = {"artist": mbid, "fmt": "json", "limit": 50}
    releases_resp = requests.get(releases_url, params=releases_params, headers=headers)
    releases_data = releases_resp.json()

    existing_titles = {r.title for r in artist.releases}

    for release in releases_data.get("releases", []):
        title = release.get("title")
        date = release.get("date", "")
        year = int(date[:4]) if date and date[:4].isdigit() else None

        if title and title not in existing_titles:
            db.add(Release(title=title, year=year, artist_id=artist.id))

    db.commit()
    return RedirectResponse(f"/artists/{artist_id}", status_code=303)
####################################################
# External IDs
####################################################
# Deezer
@router.post("/artists/{artist_id}/id_deezer")
def update_deezer_id(
    artist_id: int,
    id_deezer: str = Form(...),
    db: Session = Depends(get_db)
):
    artist = db.query(Artist).filter(Artist.id == artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    
    artist.id_deezer = id_deezer  # Update existing artist
    db.commit()
    return RedirectResponse(f"/artists/{artist_id}", status_code=303)

# Discogs
@router.post("/artists/{artist_id}/id_discogs")
def update_discogs_id(
    artist_id: str,
    id_discogs: str = Form(...),
    db: Session = Depends(get_db)
):
    artist = db.query(Artist).filter(Artist.id == artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    
    artist.id_discogs = id_discogs
    db.commit()
    return RedirectResponse(f"/artists/{artist_id}", status_code=303)

#Spotify
@router.post("/artists/{artist_id}/id_spotify")
def update_discogs_id(
    artist_id: str,
    id_spotify: str = Form(...),
    db: Session = Depends(get_db)
):
    artist = db.query(Artist).filter(Artist.id == artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    
    artist.id_spotify = id_spotify
    db.commit()
    return RedirectResponse(f"/artists/{artist_id}", status_code=303)

#Musicbrainz
@router.post("/artists/{artist_id}/id_musicbrainz")
def update_discogs_id(
    artist_id: str,
    id_musicbrainz: str = Form(...),
    db: Session = Depends(get_db)
):
    artist = db.query(Artist).filter(Artist.id == artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    
    artist.id_musicbrainz = id_musicbrainz
    db.commit()
    return RedirectResponse(f"/artists/{artist_id}", status_code=303)