from fastapi import APIRouter, HTTPException, Form, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from ..models import Release, Artist, Track, Config
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

@router.post("/artist/fetch-discogs-releases/{artist_id}")
def fetch_discogs_releases(artist_id: int, db: Session = Depends(get_db)):
    artist = db.query(Artist).filter(Artist.Id == artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    if not artist.DiscogsId:
        raise HTTPException(status_code=400, detail="Artist Discogs ID is not set")

    # Get Discogs API key from config
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

    # Fetch releases from Discogs API (artist releases endpoint)
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
        # We want only official albums/releases, not appearances, compilations, etc.
        if item.get('type') != 'release' or item.get('role') != 'Main':
            continue

        release_id = str(item.get('id'))
        title = item.get('title')
        year = item.get('year') if item.get('year') else None
        cover_url = item.get('thumb') or item.get('cover_image')

        existing = db.query(Release).filter(Release.DiscogsReleaseId == release_id).first()

        if existing:
            # Update existing release
            existing.Title = title
            existing.Year = year
            if cover_url and (not existing.Cover_Url or "cover" in existing.Cover_Url):
                existing.Cover_Url = cover_url
            release = existing
        else:
            # Create new release
            release = Release(
                Title=title,
                Year=year,
                DiscogsReleaseId=release_id,
                ArtistId=artist_id,
                Cover_Url=cover_url,
            )
            db.add(release)
            db.flush()

        # Discogs API does not have a single endpoint for tracks per release; you fetch release details separately
        # Delete old tracks
        db.query(Track).filter(Track.ReleaseId == release.Id).delete()

        # Fetch release tracklist
        release_url = f"https://api.discogs.com/releases/{release_id}"
        release_resp = requests.get(release_url, headers=headers)
        if release_resp.status_code != 200:
            continue

        release_data = release_resp.json()
        tracklist = release_data.get('tracklist', [])
        track_count = 0

        for track_item in tracklist:
            title = track_item.get('title')
            duration_str = track_item.get('duration')  # e.g. "4:35"
            length = None
            if duration_str and ":" in duration_str:
                parts = duration_str.split(":")
                try:
                    length = int(parts[0]) * 60 + int(parts[1])
                except ValueError:
                    length = None

            track = Track(
                Title=title,
                Length=length,
                SizeOnDisk=None,
                ReleaseId=release.Id,
            )
            db.add(track)
            track_count += 1

        release.TrackFileCount = track_count
        db.add(release)

    db.commit()
    return RedirectResponse(f"/artist/get-artist/{artist_id}", status_code=303)
