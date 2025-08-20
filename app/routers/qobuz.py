# /app/routers/qobuz.py 
import asyncio
import base64
import requests
import re
import hashlib
import time
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from ..models import Release, Artist
from ..db import SessionLocal
from ..utils.release_utils import update_release_tracks_if_changed
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

QOBUZ_BASE_URL = "https://www.qobuz.com/api.json/0.2"
QOBUZ_PLAY_URL = "https://play.qobuz.com"

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_qobuz_credentials():
    try:
        login_resp = requests.get(f"{QOBUZ_PLAY_URL}/login", timeout=10)
        login_resp.raise_for_status()
        login_page_html = login_resp.text

        bundle_url_match = re.search(
            r'<script src="(/resources/\d+\.\d+\.\d+-[a-z]\d{3}/bundle\.js)"></script>',
            login_page_html,
        )
        if not bundle_url_match:
            logger.error("Could not find bundle.js URL on login page.")
            return None, None

        bundle_url = QOBUZ_PLAY_URL + bundle_url_match.group(1)

        bundle_resp = requests.get(bundle_url, timeout=10)
        bundle_resp.raise_for_status()
        bundle_js = bundle_resp.text
        
        app_id_regex = r'production:{api:{appId:"(?P<app_id>\d{9})",appSecret:"(\w{32})'
        app_id_match = re.search(app_id_regex, bundle_js)
        if not app_id_match:
            logger.error("Could not find app ID in bundle.js.")
            return None, None
        
        app_id = app_id_match.group("app_id")

        seed_timezone_regex = r'[a-z]\.initialSeed\("(?P<seed>[\w=]+)",window\.ut'
        seed_matches = re.finditer(seed_timezone_regex, bundle_js)
        
        first_match = next(seed_matches, None)
        if not first_match:
            logger.error("Could not find initial seed for secret.")
            return app_id, None
            
        seed = first_match.group("seed")
        
        info_extras_regex = r'name:"\w+/(?P<timezone>{timezones})",info:"(?P<info>[\w=]+)",extras:"(?P<extras>[\w=]+)"'
        info_extras_matches = re.finditer(info_extras_regex.format(timezones='.*'), bundle_js)
        
        first_info_extras = next(info_extras_matches, None)
        if not first_info_extras:
            logger.error("Could not find info and extras for secret.")
            return app_id, None
            
        info = first_info_extras.group("info")
        extras = first_info_extras.group("extras")

        raw_secret = "".join([seed, info, extras])
        decoded_secret = base64.b64decode(raw_secret + "==").decode("utf-8").strip()

        logger.info(f"Successfully fetched Qobuz credentials: App ID {app_id}")
        return app_id, decoded_secret

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch Qobuz credentials: {e}")
        return None, None
    except Exception as e:
        logger.error(f"Unexpected error while fetching Qobuz credentials: {e}")
        return None, None

def process_qobuz_fetch(artist_id: int):
    db = next(get_db())
    try:
        artist = db.query(Artist).filter(Artist.Id == artist_id).first()
        if not artist or not artist.QobuzId:
            logger.error(f"Background task failed: Artist {artist_id} not found or has no Qobuz ID.")
            return

        app_id, secret = get_qobuz_credentials()
        if not app_id or not secret:
            logger.error(f"Failed to retrieve dynamic Qobuz credentials for artist {artist_id}.")
            return
            
        headers = {"X-App-Id": app_id}
        
        success_messages = []
        error_messages = []
        releases_processed_count = 0
        tracks_updated_count = 0
        
        try:
            artist_url = f"{QOBUZ_BASE_URL}/artist/get?artist_id={artist.QobuzId}"
            artist_resp = requests.get(artist_url, headers=headers, timeout=10)
            artist_resp.raise_for_status()
            artist_data = artist_resp.json().get("artist", {})
            image_url = artist_data.get("image", {}).get("large_url")
            if image_url and (not artist.ImageUrl or "qobuz" in artist.ImageUrl):
                artist.ImageUrl = image_url
                db.add(artist)
                db.commit()
                success_messages.append("Artist image updated from Qobuz.")
                logger.info(f"Artist {artist.Name} (ID: {artist_id}) image updated.")
        except requests.exceptions.RequestException as e:
            error_messages.append(f"Failed to fetch artist image from Qobuz: {e}.")
            logger.error(f"Failed to fetch artist image for {artist.Name} (ID: {artist_id}) from Qobuz: {e}")

        albums = []
        url = f"{QOBUZ_BASE_URL}/artist/get?artist_id={artist.QobuzId}&extra=albums"
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json().get('artist', {}).get('albums', {})
            albums.extend(data.get('items', []))
            
            logger.info(f"Fetched {len(albums)} albums from Qobuz for {artist.Name}.")
        except requests.exceptions.RequestException as e:
            error_messages.append(f"Failed to fetch albums from Qobuz: {e}.")
            logger.error(f"Failed to fetch albums for {artist.Name} (ID: {artist_id}) from Qobuz: {e}")
            return
        except Exception as e:
            error_messages.append(f"Unexpected error during album fetching: {e}.")
            logger.error(f"Unexpected error during album fetching for {artist.Name} (ID: {artist_id}): {e}")
            return

        for album in albums:
            try:
                album_id = str(album['id'])
                title = album.get('title')
                year = album.get('release_date')[:4] if album.get('release_date') else None
                cover_url = album.get('image', {}).get('large_url')

                existing = db.query(Release).filter(Release.QobuzId == album_id).first()
                if existing:
                    existing.Title = title
                    existing.Year = year
                    if cover_url and (not existing.Cover_Url or "qobuz" in existing.Cover_Url):
                        existing.Cover_Url = cover_url
                    release = existing
                    logger.info(f"Updating existing Qobuz release: {title} (ID: {album_id})")
                else:
                    release = Release(Title=title, Year=year, QobuzId=album_id, ArtistId=artist_id, Cover_Url=cover_url)
                    db.add(release)
                    db.flush()
                    logger.info(f"Adding new Qobuz release: {title} (ID: {album_id})")
                
                unix_ts = int(time.time())
                r_sig = f"albumgettrackscatalog_id{album_id}{unix_ts}{secret}"
                r_sig_hashed = hashlib.md5(r_sig.encode("utf-8")).hexdigest()
                
                track_url = f"{QOBUZ_BASE_URL}/album/get?album_id={album_id}&extra=tracks&request_ts={unix_ts}&request_sig={r_sig_hashed}"
                resp = requests.get(track_url, headers=headers, timeout=10)
                resp.raise_for_status()

                track_data = resp.json().get("album", {}).get("tracks", {}).get("items", [])
                
                incoming_tracks = [{
                    "Title": item.get("title", "").strip(),
                    "Duration": item.get("duration"),
                    "TrackNumber": item.get("track_number"),
                    "DiscNumber": item.get("disc_number", 1)
                } for item in track_data if item.get("title") and item.get("track_number") is not None]

                if update_release_tracks_if_changed(db, release, incoming_tracks):
                    db.commit()
                    releases_processed_count += 1
                    tracks_updated_count += len(incoming_tracks)
                    logger.info(f"Tracks updated for release {title} (ID: {album_id}). Total: {len(incoming_tracks)}")
                else:
                    logger.info(f"No track changes for release {title} (ID: {album_id}).")

            except requests.exceptions.RequestException as e:
                error_messages.append(f"Failed to process Qobuz release {album.get('title', 'N/A')}: {e}.")
                logger.error(f"Failed to process Qobuz release {album.get('title', 'N/A')}: {e}")
                db.rollback()
            except Exception as e:
                error_messages.append(f"Unexpected error while processing Qobuz release {album.get('title', 'N/A')}: {e}.")
                logger.error(f"Unexpected error while processing Qobuz release {album.get('title', 'N/A')}: {e}")
                db.rollback()
    finally:
        db.close()

@router.post("/artist/fetch-qobuz-releases/{artist_id}")
def fetch_qobuz_releases(artist_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    artist = db.query(Artist).filter(Artist.Id == artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    
    if not artist.QobuzId:
        return RedirectResponse(
            url=f"/artist/get-artist/{artist_id}?error=Artist Qobuz ID is not set.",
            status_code=303
        )
    
    background_tasks.add_task(process_qobuz_fetch, artist_id)
    
    return RedirectResponse(
        url=f"/artist/get-artist/{artist_id}?message=Qobuz fetch started in the background. It may take a few moments for changes to appear.",
        status_code=303
    )
