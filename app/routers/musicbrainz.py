import requests
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from ..models import Release, Artist, Track
from ..db import SessionLocal
import time

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/artist/fetch-musicbrainz-releases/{artist_id}")
async def fetch_musicbrainz_releases_trigger(
    artist_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    artist = db.query(Artist).filter(Artist.Id == artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    if not artist.MusicbrainzId:
        raise HTTPException(status_code=400, detail="Artist MusicBrainz ID is not set")

    background_tasks.add_task(fetch_musicbrainz_releases_background, artist_id)

    return RedirectResponse(f"/artist/get-artist/{artist_id}", status_code=303)


def fetch_musicbrainz_releases_background(artist_id: int):
    db = SessionLocal()
    try:
        artist = db.query(Artist).filter(Artist.Id == artist_id).first()
        if not artist:
            return

        mbid = artist.MusicbrainzId
        headers = {"User-Agent": "Releasarr/1.0"}

        artist_url = f"https://musicbrainz.org/ws/2/artist/{mbid}?inc=url-rels&fmt=json"
        resp = requests.get(artist_url, headers=headers)
        if resp.status_code != 200:
            return
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
        db.flush()
        db.commit()

        offset = 0
        all_releases = []
        while True:
            url = f"https://musicbrainz.org/ws/2/release?artist={mbid}&fmt=json&limit=100&offset={offset}"
            resp = requests.get(url, headers=headers)
            if resp.status_code != 200:
                break
            release_data = resp.json()
            releases = release_data.get("releases", [])
            all_releases.extend(releases)
            offset += 100
            if len(all_releases) >= release_data.get("release-count", 0):
                break
            time.sleep(0.1)

        release_groups = {}

        for r in all_releases:
            release_group_id = r.get("release-group", {}).get("id")
            if not release_group_id:
                continue

            release_id = r.get("id")

            track_count = 0
            tracks_data = None
            try:
                time.sleep(0.1)
                track_resp = requests.get(
                    f"https://musicbrainz.org/ws/2/release/{release_id}?inc=recordings&fmt=json",
                    headers=headers,
                )
                if track_resp.status_code == 200:
                    tracks_data = track_resp.json()
                    for medium in tracks_data.get("media", []):
                        track_count += len(medium.get("tracks", []))
            except Exception:
                pass

            if release_group_id not in release_groups or track_count > release_groups[release_group_id]["track_count"]:
                release_groups[release_group_id] = {
                    "release": r,
                    "track_count": track_count,
                    "tracks_data": tracks_data,
                }

        for group_id, info in release_groups.items():
            r = info["release"]
            track_count = info["track_count"]
            tracks_data = info["tracks_data"]

            release_id = r.get("id")
            title = r.get("title")
            date = r.get("date")
            year = int(date[:4]) if date and len(date) >= 4 else None

            cover_url = None
            try:
                time.sleep(0.1)
                cover_resp = requests.get(f"http://coverartarchive.org/release/{release_id}")
                if cover_resp.status_code == 200:
                    img_data = cover_resp.json()
                    img = img_data.get("images", [])[0]
                    cover_url = img.get("thumbnails", {}).get("large") or img.get("image")
            except Exception:
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

            db.query(Track).filter(Track.ReleaseId == release.Id).delete()

            track_count = 0
            if tracks_data:
                for medium in tracks_data.get("media", []):
                    for t in medium.get("tracks", []):
                        t_title = t.get("title")
                        length = int(t.get("length", 0) / 1000) if t.get("length") else None
                        track = Track(
                            Title=t_title,
                            Length=length,
                            SizeOnDisk=None,
                            ReleaseId=release.Id,
                        )
                        db.add(track)
                        track_count += 1

            release.TrackFileCount = track_count
            db.add(release)
            db.commit()
            time.sleep(0.1)

    finally:
        db.close()