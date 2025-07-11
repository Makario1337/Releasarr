from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from ..db import SessionLocal
from ..models import Release, Track, Artist
from ..utils.release_utils import update_release_tracks_if_changed

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/release/edit-release/{release_id}")
def edit_release_form(
    release_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    release = db.query(Release).filter(Release.Id == release_id).first()
    if not release:
        raise HTTPException(status_code=404, detail="Release not found")

    existing_tracks = db.query(Track).filter(Track.ReleaseId == release.Id).order_by(Track.DiscNumber, Track.TrackNumber).all()
    # Pass full Track objects to the template for easier access to all attributes
    tracks_for_template = existing_tracks

    return templates.TemplateResponse(
        "edit_release.html",
        {
            "request": request,
            "release": release,
            "tracks": tracks_for_template,
        },
    )

@router.post("/release/edit-release/{release_id}")
def update_release(
    release_id: int,
    title: str = Form(...),
    year: int = Form(None),
    cover_url: str = Form(None),
    track_titles: list[str] = Form([]),
    track_lengths: list[int | None] = Form([]),
    disc_numbers: list[int | None] = Form([]), # New: Collect disc numbers
    track_numbers: list[int | None] = Form([]), # New: Collect track numbers
    db: Session = Depends(get_db)
):
    release = db.query(Release).filter(Release.Id == release_id).first()
    if not release:
        raise HTTPException(status_code=404, detail="Release not found")

    release.Title = title
    release.Year = year
    release.Cover_Url = cover_url if cover_url else None

    incoming_tracks = []
    # Use min of all relevant lists to avoid IndexError
    min_len = min(len(track_titles), len(track_lengths), len(disc_numbers), len(track_numbers))
    for i in range(min_len):
        track_title = track_titles[i].strip()
        track_length = track_lengths[i] if track_lengths[i] is not None else None
        disc_number = disc_numbers[i] if disc_numbers[i] is not None else 1 # Default to 1 if None
        track_number = track_numbers[i] if track_numbers[i] is not None else None

        if track_title: # Only add if track has a title
            incoming_tracks.append((track_title, track_length, track_number, disc_number))

    tracks_updated = update_release_tracks_if_changed(db, release, incoming_tracks)

    if not tracks_updated:
        db.add(release) # Re-add release if tracks weren't updated, to ensure its own fields are saved
    db.commit()

    return RedirectResponse(f"/artist/get-artist/{release.ArtistId}", status_code=303)

@router.get("/release/add-release/{artist_id}")
def add_release_form(
    artist_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    artist = db.query(Artist).filter(Artist.Id == artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")

    return templates.TemplateResponse(
        "add_release.html",
        {
            "request": request,
            "artist": artist,
            "artist_id": artist_id
        },
    )

@router.post("/release/add-release/{artist_id}")
def create_release(
    artist_id: int,
    title: str = Form(...),
    year: int = Form(None),
    cover_url: str = Form(None),
    track_titles: list[str] = Form([]),
    track_lengths: list[int | None] = Form([]),
    disc_numbers: list[int | None] = Form([]), # New: Collect disc numbers
    track_numbers: list[int | None] = Form([]), # New: Collect track numbers
    db: Session = Depends(get_db)
):
    artist = db.query(Artist).filter(Artist.Id == artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")

    if not title:
        raise HTTPException(status_code=400, detail="Title is required.")

    normalized_title = title.lower().replace(" ", "").replace("'", "").replace(".", "")

    new_release = Release(
        Title=title,
        Year=year,
        Cover_Url=cover_url if cover_url else None,
        ArtistId=artist_id,
        NormalizedTitle=normalized_title,
        TrackFileCount=0
    )

    db.add(new_release)
    db.flush()

    incoming_tracks = []
    min_len = min(len(track_titles), len(track_lengths), len(disc_numbers), len(track_numbers))
    for i in range(min_len):
        track_title = track_titles[i].strip()
        track_length = track_lengths[i] if track_lengths[i] is not None else None
        disc_number = disc_numbers[i] if disc_numbers[i] is not None else 1 # Default to 1 if None
        track_number = track_numbers[i] if track_numbers[i] is not None else None
        
        if track_title: # Only add if track has a title
            incoming_tracks.append((track_title, track_length, track_number, disc_number))

    if incoming_tracks:
        update_release_tracks_if_changed(db, new_release, incoming_tracks)
    
    db.commit()

    return RedirectResponse(f"/artist/get-artist/{artist_id}", status_code=303)

@router.post("/release/delete-release/{release_id}")
def delete_release(
    release_id: int,
    db: Session = Depends(get_db)
):
    release = db.query(Release).filter(Release.Id == release_id).first()
    if not release:
        raise HTTPException(status_code=404, detail="Release not found")

    artist_id = release.ArtistId

    db.delete(release)
    db.commit()

    return RedirectResponse(f"/artist/get-artist/{artist_id}", status_code=303)

@router.post("/release/delete-multiple-releases")
def delete_multiple_releases(
    release_ids: list[int] = Form(...),
    artist_id_redirect: int = Form(...),
    db: Session = Depends(get_db)
):
    if not release_ids:
        return RedirectResponse(f"/artist/get-artist/{artist_id_redirect}", status_code=303)

    releases_to_delete = db.query(Release).filter(
        Release.Id.in_(release_ids),
        Release.ArtistId == artist_id_redirect
    ).all()

    if not releases_to_delete:
        raise HTTPException(status_code=404, detail="No valid releases found to delete.")

    for release in releases_to_delete:
        db.delete(release)
    
    db.commit()

    return RedirectResponse(f"/artist/get-artist/{artist_id_redirect}", status_code=303)
