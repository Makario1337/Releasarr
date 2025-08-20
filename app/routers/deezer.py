# /app/routers/deezer.py 
import requests
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from ..models import Release, Artist
from ..db import SessionLocal
from ..utils.release_utils import update_release_tracks_if_changed
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def process_deezer_fetch(artist_id: int):
    db = next(get_db())
    try:
        artist = db.query(Artist).filter(Artist.Id == artist_id).first()
        if not artist or not artist.DeezerId:
            logger.error(f"Background task failed: Artist {artist_id} not found or has no Deezer ID.")
            return

        success_messages = []
        error_messages = []
        releases_processed_count = 0
        tracks_updated_count = 0

        try:
            artist_url = f"https://api.deezer.com/artist/{artist.DeezerId}"
            artist_resp = requests.get(artist_url, timeout=10)
            artist_resp.raise_for_status()
            artist_data = artist_resp.json()
            image_url = artist_data.get("picture_xl") or artist_data.get("picture_big")
            if image_url and (not artist.ImageUrl or "picture" in artist.ImageUrl):
                artist.ImageUrl = image_url
                db.add(artist)
                db.commit()
                success_messages.append("Artist image updated from Deezer.")
                logger.info(f"Artist {artist.Name} (ID: {artist_id}) image updated.")
        except requests.exceptions.RequestException as e:
            error_messages.append(f"Failed to fetch artist image from Deezer: {e}.")
            logger.error(f"Failed to fetch artist image for {artist.Name} (ID: {artist_id}): {e}")
        except Exception as e:
            error_messages.append(f"Unexpected error with artist image: {e}.")
            logger.error(f"Unexpected error with artist image for {artist.Name} (ID: {artist_id}): {e}")

        albums = []
        url = f"https://api.deezer.com/artist/{artist.DeezerId}/albums"
        try:
            while url:
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                data = response.json()
                albums.extend(data.get('data', []))
                url = data.get('next')
            success_messages.append(f"Fetched {len(albums)} albums from Deezer for {artist.Name}.")
            logger.info(f"Fetched {len(albums)} albums from Deezer for {artist.Name}.")
        except requests.exceptions.RequestException as e:
            error_messages.append(f"Failed to fetch albums from Deezer: {e}.")
            logger.error(f"Failed to fetch albums for {artist.Name} (ID: {artist_id}) from Deezer: {e}")
            return
        except Exception as e:
            error_messages.append(f"Unexpected error during album fetching: {e}.")
            logger.error(f"Unexpected error during album fetching for {artist.Name} (ID: {artist_id}): {e}")
            return

        for album in albums:
            try:
                album_id = str(album['id'])
                title = album['title']
                release_date = album.get('release_date')
                year = int(release_date[:4]) if release_date else None
                cover_url = album.get('cover_xl') or album.get('cover_big') or album.get('cover_medium')

                existing = db.query(Release).filter(Release.DeezerId == album_id).first()
                if existing:
                    existing.Title = title
                    existing.Year = year
                    if cover_url and (not existing.Cover_Url or "cover" in existing.Cover_Url):
                        existing.Cover_Url = cover_url
                    release = existing
                    logger.info(f"Updating existing Deezer release: {title} (ID: {album_id})")
                else:
                    release = Release(Title=title, Year=year, DeezerId=album_id, ArtistId=artist_id, Cover_Url=cover_url)
                    db.add(release)
                    db.flush()
                    logger.info(f"Adding new Deezer release: {title} (ID: {album_id})")

                track_url = f"https://api.deezer.com/album/{album_id}/tracks"
                resp = requests.get(track_url, timeout=10)
                resp.raise_for_status()

                track_data = resp.json().get("data", [])
                incoming_tracks = [{
                    "Title": item.get("title", "").strip(),
                    "Duration": item.get("duration"),
                    "TrackNumber": item.get("track_position"),
                    "DiscNumber": item.get("disk_number", 1)
                } for item in track_data if item.get("title") and item.get("track_position") is not None]

                if update_release_tracks_if_changed(db, release, incoming_tracks):
                    db.commit()
                    releases_processed_count += 1
                    tracks_updated_count += len(incoming_tracks)
                    logger.info(f"Tracks updated for release {title} (ID: {album_id}). Total: {len(incoming_tracks)}")
                else:
                    logger.info(f"No track changes for release {title} (ID: {album_id}).")

            except requests.exceptions.RequestException as e:
                error_messages.append(f"Failed to process Deezer release {album.get('title', 'N/A')}: {e}.")
                logger.error(f"Failed to process Deezer release {album.get('title', 'N/A')}: {e}")
                db.rollback()
            except Exception as e:
                error_messages.append(f"Unexpected error while processing Deezer release {album.get('title', 'N/A')}: {e}.")
                logger.error(f"Unexpected error while processing Deezer release {album.get('title', 'N/A')}: {e}")
                db.rollback()
    finally:
        db.close()

@router.post("/artist/fetch-deezer-releases/{artist_id}")
def fetch_deezer_releases(artist_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    artist = db.query(Artist).filter(Artist.Id == artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")

    if not artist.DeezerId:
        return RedirectResponse(
            url=f"/artist/get-artist/{artist_id}?error=Artist Deezer ID is not set.",
            status_code=303
        )
    
    background_tasks.add_task(process_deezer_fetch, artist_id)

    return RedirectResponse(
        url=f"/artist/get-artist/{artist_id}?message=Deezer fetch started in the background. It may take a few moments for changes to appear.",
        status_code=303
    )