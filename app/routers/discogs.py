# app/routers/discogs.py
from fastapi import APIRouter, HTTPException, Form, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from ..models import Release, Artist, Track, Config
from ..db import SessionLocal
import requests
from ..utils.release_utils import update_release_tracks_if_changed

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/artist/fetch-discogs-releases/{artist_id}")
def fetch_discogs_releases(artist_id: int, db: Session = Depends(get_db)):
    artist = db.query(Artist).filter(Artist.Id == artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    if not artist.DiscogsId:
        raise HTTPException(status_code=400, detail="Artist Discogs ID is not set")

    api_key_config = db.query(Config).filter(Config.Key == "DiscogsApiKey").first()
    if not api_key_config or not api_key_config.Value:
        raise HTTPException(status_code=400, detail="Discogs API key not configured")

    discogs_api_key = api_key_config.Value.strip()
    if not discogs_api_key:
        raise HTTPException(status_code=400, detail="Discogs API key is empty")

    headers = {
        "User-Agent": "Releasarr/1.0",
        "Authorization": f"Discogs token={discogs_api_key}",
    }

    releases = []
    page = 1
    per_page = 100
    while True:
        url = f"https://api.discogs.com/artists/{artist.DiscogsId}/releases?page={page}&per_page={per_page}"
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail=f"Failed to fetch releases from Discogs (status {response.status_code})")

        data = response.json()
        releases.extend(data.get('releases', []))

        pagination = data.get('pagination', {})
        if not pagination.get('pages') or page >= pagination.get('pages'):
            break
        page += 1

    for item in releases:
        if item.get('type') != 'release' or item.get('role') != 'Main':
            continue

        release_id = str(item.get('id'))
        title = item.get('title')
        year = item.get('year') if item.get('year') else None
        cover_url = item.get('thumb') or item.get('cover_image')

        existing = db.query(Release).filter(Release.DiscogsReleaseId == release_id).first()

        if existing:
            existing.Title = title
            existing.Year = year
            if cover_url and (not existing.Cover_Url or "cover" in existing.Cover_Url):
                existing.Cover_Url = cover_url
            release = existing
        else:
            release = Release(
                Title=title,
                Year=year,
                DiscogsReleaseId=release_id,
                ArtistId=artist_id,
                Cover_Url=cover_url,
            )
            db.add(release)
            db.flush()

        release_url = f"https://api.discogs.com/releases/{release_id}"
        release_resp = requests.get(release_url, headers=headers)
        if release_resp.status_code != 200:
            continue

        release_data = release_resp.json()
        tracklist = release_data.get('tracklist', [])
        
        incoming_tracks = []
        for track_item in tracklist:
            track_title = track_item.get('title')
            duration_str = track_item.get('duration')
            length = None
            if duration_str and ":" in duration_str:
                parts = duration_str.split(":")
                try:
                    length = int(parts[0]) * 60 + int(parts[1])
                except ValueError:
                    length = None

            position_str = track_item.get('position')
            track_number = None
            disc_number = 1

            if position_str:
                if '-' in position_str:
                    try:
                        disc_part, track_part = position_str.split('-')
                        disc_number = int(disc_part)
                        track_number = int(track_part)
                    except ValueError:
                        track_number = None
                        disc_number = 1
                elif position_str.isdigit():
                    track_number = int(position_str)
                elif position_str.isalpha() and len(position_str) == 1:
                    track_number = None
                    disc_number = 1
                else:
                    numeric_part = ''.join(filter(str.isdigit, position_str))
                    if numeric_part:
                        track_number = int(numeric_part)
                    disc_number = 1

            if track_title:
                incoming_tracks.append((track_title, length, track_number, disc_number))

        if update_release_tracks_if_changed(db, release, incoming_tracks):
            db.commit()

    db.commit()
    return RedirectResponse(f"/artist/get-artist/{artist_id}", status_code=303)
