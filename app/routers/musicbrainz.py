# /app/routers/musicbrainz.py
import requests
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
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

def process_musicbrainz_fetch(artist_id: int):
    db = next(get_db())
    try:
        artist = db.query(Artist).filter(Artist.Id == artist_id).first()
        if not artist or not artist.MusicbrainzId:
            logger.error(f"Background task failed: Artist {artist_id} not found or has no MusicBrainz ID.")
            return

        mbid = artist.MusicbrainzId
        headers = {"User-Agent": "Releasarr/1.0"}

        artist_url = f"https://musicbrainz.org/ws/2/artist/{mbid}?inc=url-rels&fmt=json"
        try:
            resp = requests.get(artist_url, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            if disamb := data.get("disambiguation"):
                artist.Disambiguation = disamb

            for rel in data.get("relations", []):
                url = rel.get("url", {}).get("resource", "").lower()
                if "apple" in url:
                    artist.AppleMusicId = url.split("/")[-1]
                elif "deezer" in url:
                    artist.DeezerId = url.split("/")[-1]
                elif "spotify" in url:
                    artist.SpotifyId = url.split("/")[-1]
                elif "tidal" in url:
                    artist.TidalId = url.split("/")[-1]
                elif "discogs" in url:
                    artist.DiscogsId = url.split("/")[-1]

            db.add(artist)
            db.commit()
            logger.info(f"Artist {artist.Name} (ID: {artist_id}) metadata updated from MusicBrainz.")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch artist metadata for {artist.Name} (ID: {artist_id}): {e}")
            db.rollback()
            return
        except Exception as e:
            logger.error(f"Unexpected error with artist metadata for {artist.Name} (ID: {artist_id}): {e}")
            db.rollback()
            return

        offset = 0
        all_releases = []
        while True:
            url = f"https://musicbrainz.org/ws/2/release?artist={mbid}&fmt=json&limit=100&offset={offset}"
            try:
                resp = requests.get(url, headers=headers, timeout=10)
                resp.raise_for_status()
                release_data = resp.json()
                releases = release_data.get("releases", [])
                all_releases.extend(releases)
                offset += 100
                if len(all_releases) >= release_data.get("release-count", 0) or not releases:
                    break
            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to fetch releases for {artist.Name} (ID: {artist_id}): {e}")
                return
        
        logger.info(f"Fetched {len(all_releases)} releases from MusicBrainz for {artist.Name}.")

        release_groups = {}
        for r in all_releases:
            release_group_id = r.get("release-group", {}).get("id")
            if not release_group_id:
                continue
            
            release_id = r.get("id")
            
            track_count = 0
            tracks_data = None
            try:
                track_resp = requests.get(
                    f"https://musicbrainz.org/ws/2/release/{release_id}?inc=recordings&fmt=json",
                    headers=headers, timeout=10
                )
                if track_resp.status_code == 200:
                    tracks_data = track_resp.json()
                    for medium in tracks_data.get("media", []):
                        track_count += len(medium.get("tracks", []))
            except Exception as e:
                logger.error(f"Error fetching tracks for release {release_id}: {e}")
                pass

            if release_group_id not in release_groups or track_count > release_groups[release_group_id]["track_count"]:
                release_groups[release_group_id] = {
                    "release": r,
                    "track_count": track_count,
                    "tracks_data": tracks_data,
                }
        
        for group_id, info in release_groups.items():
            r = info["release"]
            tracks_data = info["tracks_data"]

            release_id = r.get("id")
            title = r.get("title")
            date = r.get("date")
            year = int(date[:4]) if date and len(date) >= 4 else None

            cover_url = None
            try:
                cover_resp = requests.get(f"http://coverartarchive.org/release/{release_id}", timeout=10)
                if cover_resp.status_code == 200:
                    img_data = cover_resp.json()
                    if img_data.get("images"):
                        img = img_data["images"][0]
                        cover_url = img.get("thumbnails", {}).get("large") or img.get("image")
            except Exception as e:
                logger.error(f"Error fetching cover art for release {release_id}: {e}")
                pass

            existing = db.query(Release).filter(Release.MusicbrainzReleaseId == release_id).first()
            if existing:
                existing.Title = title
                existing.Year = year
                if cover_url:
                    existing.Cover_Url = cover_url
                release = existing
            else:
                release = Release(
                    Title=title,
                    Year=year,
                    MusicbrainzReleaseId=release_id,
                    ArtistId=artist_id,
                    Cover_Url=cover_url,
                )
                db.add(release)
                db.flush()

            incoming_tracks = []
            if tracks_data:
                for medium in tracks_data.get("media", []):
                    disc_number = medium.get("position", 1)
                    for t in medium.get("tracks", []):
                        track_title = t.get("title")
                        length = int(t.get("length", 0) / 1000) if t.get("length") else None
                        track_number = t.get("position")
                        if track_title and track_number is not None:
                            incoming_tracks.append({
                                "Title": track_title,
                                "Duration": length,
                                "TrackNumber": track_number,
                                "DiscNumber": disc_number
                            })

            if update_release_tracks_if_changed(db, release, incoming_tracks):
                db.commit()
    finally:
        db.close()


@router.post("/artist/fetch-musicbrainz-releases/{artist_id}")
def fetch_musicbrainz_releases(
    artist_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    artist = db.query(Artist).filter(Artist.Id == artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    if not artist.MusicbrainzId:
        return RedirectResponse(
            f"/artist/get-artist/{artist_id}?error=Artist MusicBrainz ID is not set",
            status_code=303
        )

    background_tasks.add_task(process_musicbrainz_fetch, artist_id)
    
    return RedirectResponse(
        f"/artist/get-artist/{artist_id}?message=MusicBrainz fetch started in the background. It may take a few moments for changes to appear.",
        status_code=303
    )