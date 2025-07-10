# deezer.py

import requests
from fastapi import APIRouter, HTTPException, Form, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from ..models import Release, Artist
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

###############################################################
# Deezer Artist External IDs
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
# Deezer Release + Track Fetching
###############################################################

@router.post("/artist/fetch-deezer-releases/{artist_id}")
def fetch_deezer_releases(artist_id: int, db: Session = Depends(get_db)):
    artist = db.query(Artist).filter(Artist.Id == artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    if not artist.DeezerId:
        raise HTTPException(status_code=400, detail="Artist Deezer ID is not set")

    # Fetch artist image
    artist_url = f"https://api.deezer.com/artist/{artist.DeezerId}"
    artist_resp = requests.get(artist_url)
    if artist_resp.status_code == 200:
        artist_data = artist_resp.json()
        image_url = (
            artist_data.get("picture_xl")
            or artist_data.get("picture_big")
            or artist_data.get("picture_medium")
            or artist_data.get("picture_small")
            or artist_data.get("picture")
        )
        if image_url and (not artist.ImageUrl or "picture" in artist.ImageUrl):
            artist.ImageUrl = image_url
            db.add(artist)

    # Fetch albums
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
        title = album['title']
        release_date = album.get('release_date')
        year = int(release_date[:4]) if release_date else None
        cover_url = (
            album.get('cover_xl')
            or album.get('cover_big')
            or album.get('cover_medium')
            or album.get('cover_small')
            or album.get('cover')
        )

        existing = db.query(Release).filter(Release.DeezerAlbumId == album_id).first()
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
                DeezerAlbumId=album_id,
                ArtistId=artist_id,
                Cover_Url=cover_url,
            )
            db.add(release)
            db.flush()

        # Fetch tracks
        track_url = f"https://api.deezer.com/album/{album_id}/tracks"
        resp = requests.get(track_url)
        if resp.status_code != 200:
            continue

        track_data = resp.json().get("data", [])
        incoming_tracks = [
            (item.get("title").strip(), item.get("duration")) for item in track_data if item.get("title")
        ]

        if update_release_tracks_if_changed(db, release, incoming_tracks):
            db.commit()

    db.commit()
    return RedirectResponse(f"/artist/get-artist/{artist_id}", status_code=303)
