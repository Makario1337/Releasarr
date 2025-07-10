from fastapi import APIRouter,HTTPException, Form, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from ..models import Release, Artist, Track
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

###############################################################
# Deezer Artist Information
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

###############################################################
# Deezer Release + Track Information
###############################################################

# Deezer
@router.post("/artist/fetch-deezer-releases/{artist_id}")
def fetch_deezer_releases(artist_id: int, db: Session = Depends(get_db)):
    artist = db.query(Artist).filter(Artist.Id == artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    if not artist.DeezerId:
        raise HTTPException(status_code=400, detail="Artist Deezer ID is not set")

    albums = []
    url = f"https://api.deezer.com/artist/{artist.DeezerId}/albums"
    while url:
        response = requests.get(url)
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to fetch from Deezer")
        data = response.json()
        albums.extend(data.get('data', []))
        url = data.get('next')

    for album in albums:
        album_id = str(album['id'])
        cover_url = (
            album.get('cover_xl')
            or album.get('cover_big')
            or album.get('cover_medium')
            or album.get('cover_small')
            or album.get('cover')
        )
        release_date = album.get('release_date')
        year = int(release_date[:4]) if release_date else None
        title = album['title']

        existing = db.query(Release).filter(Release.DeezerAlbumId == album_id).first()

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
                DeezerAlbumId=album_id,
                ArtistId=artist_id,
                Cover_Url=cover_url,
            )
            db.add(release)
            db.flush()

        # Delete old tracks
        db.query(Track).filter(Track.ReleaseId == release.Id).delete()

        # Fetch and import tracks
        track_url = f"https://api.deezer.com/album/{album_id}/tracks"
        resp = requests.get(track_url)
        if resp.status_code != 200:
            continue

        track_data = resp.json().get("data", [])
        track_count = 0

        for item in track_data:
            title = item.get("title")
            length = item.get("duration")
            
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