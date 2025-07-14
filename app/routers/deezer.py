import requests
from fastapi import APIRouter, HTTPException, Form, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from ..models import Release, Artist, Track
from ..db import SessionLocal
from ..utils.release_utils import update_release_tracks_if_changed
import logging

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


logger = logging.getLogger(__name__)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/artist/fetch-deezer-releases/{artist_id}")
def fetch_deezer_releases(artist_id: int, db: Session = Depends(get_db)):
    artist = db.query(Artist).filter(Artist.Id == artist_id).first()
    if not artist:
        logger.error(f"Artist with ID {artist_id} not found for Deezer fetch.")
        raise HTTPException(status_code=404, detail="Artist not found")
    if not artist.DeezerId:
        logger.warning(f"Artist {artist.Name} (ID: {artist_id}) does not have a Deezer ID set.")
        return RedirectResponse(
            url=f"/artist/get-artist/{artist_id}?error=Artist Deezer ID is not set.",
            status_code=303
        )

    success_messages = []
    error_messages = []
    releases_processed_count = 0
    tracks_updated_count = 0

    try:
        artist_url = f"https://api.deezer.com/artist/{artist.DeezerId}"
        artist_resp = requests.get(artist_url, timeout=10)
        artist_resp.raise_for_status()

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
            db.flush()
            db.commit()
            success_messages.append("Artist image updated from Deezer.")
            logger.info(f"Artist {artist.Name} (ID: {artist_id}) image updated from Deezer.")
    except requests.exceptions.RequestException as e:
        error_messages.append(f"Failed to fetch artist image from Deezer: {e}.")
        logger.error(f"Failed to fetch artist image for {artist.Name} (ID: {artist_id}) from Deezer: {e}")
    except Exception as e:
        error_messages.append(f"An unexpected error occurred while processing artist image: {e}.")
        logger.error(f"An unexpected error occurred while processing artist image for {artist.Name} (ID: {artist_id}): {e}")

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
        return RedirectResponse(
            url=f"/artist/get-artist/{artist_id}?message={' '.join(success_messages)}&error={' '.join(error_messages)}",
            status_code=303
        )
    except Exception as e:
        error_messages.append(f"An unexpected error occurred during album fetching: {e}.")
        logger.error(f"An unexpected error occurred during album fetching for {artist.Name} (ID: {artist_id}): {e}")
        return RedirectResponse(
            url=f"/artist/get-artist/{artist_id}?message={' '.join(success_messages)}&error={' '.join(error_messages)}",
            status_code=303
        )


    for album in albums:
        try:
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

            existing = db.query(Release).filter(Release.DeezerId == album_id).first()
            if existing:
                existing.Title = title
                existing.Year = year
                if cover_url and (not existing.Cover_Url or "cover" in existing.Cover_Url):
                    existing.Cover_Url = cover_url
                release = existing
                logger.info(f"Updating existing Deezer release: {title} (ID: {album_id})")
            else:
                release = Release(
                    Title=title,
                    Year=year,
                    DeezerId=album_id,
                    ArtistId=artist_id,
                    Cover_Url=cover_url,
                )
                db.add(release)
                db.flush()
                logger.info(f"Adding new Deezer release: {title} (ID: {album_id})")

            track_url = f"https://api.deezer.com/album/{album_id}/tracks"
            resp = requests.get(track_url, timeout=10)
            resp.raise_for_status()

            track_data = resp.json().get("data", [])
            incoming_tracks = []
            for item in track_data:
                track_title = item.get("title").strip() if item.get("title") else None
                track_duration = item.get("duration")
                track_number = item.get("track_position")
                disc_number = item.get("disk_number", 1)

                if track_title and track_number is not None:
                    incoming_tracks.append({
                        "Title": track_title,
                        "Duration": track_duration,
                        "TrackNumber": track_number,
                        "DiscNumber": disc_number
                    })

            if update_release_tracks_if_changed(db, release, incoming_tracks):
                db.commit()
                releases_processed_count += 1
                tracks_updated_count += len(incoming_tracks)
                logger.info(f"Tracks updated for release {title} (ID: {album_id}). Total tracks: {len(incoming_tracks)}")
            else:
                logger.info(f"No track changes for release {title} (ID: {album_id}).")

        except requests.exceptions.RequestException as e:
            error_messages.append(f"Failed to process Deezer release {album.get('title', 'N/A')} (ID: {album.get('id', 'N/A')}): {e}.")
            logger.error(f"Failed to process Deezer release {album.get('title', 'N/A')} (ID: {album.get('id', 'N/A')}): {e}")
            db.rollback()
        except Exception as e:
            error_messages.append(f"An unexpected error occurred while processing Deezer release {album.get('title', 'N/A')} (ID: {album.get('id', 'N/A')}): {e}.")
            logger.error(f"An unexpected error occurred while processing Deezer release {album.get('title', 'N/A')} (ID: {album.get('id', 'N/A')}): {e}")
            db.rollback()

    db.commit()

    final_message = []
    if releases_processed_count > 0:
        final_message.append(f"Successfully processed {releases_processed_count} releases and {tracks_updated_count} tracks from Deezer.")
    if success_messages:
        final_message.extend(success_messages)
    if error_messages:
        final_message.append("Errors occurred: " + " ".join(error_messages))

    if final_message:
        return RedirectResponse(
            url=f"/artist/get-artist/{artist_id}?message={' '.join(final_message)}",
            status_code=303
        )
    else:
        return RedirectResponse(f"/artist/get-artist/{artist_id}", status_code=303)
