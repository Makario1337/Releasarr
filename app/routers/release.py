# app/routers/release.py
from fastapi import APIRouter, Request, Form, Depends, HTTPException, Query
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from ..db import SessionLocal
from ..models import Release, Track, Artist, ImportedFile
from ..utils.release_utils import update_release_tracks_if_changed
import math

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
    disc_numbers: list[int | None] = Form([]), 
    track_numbers: list[int | None] = Form([]),
    db: Session = Depends(get_db)
):
    release = db.query(Release).filter(Release.Id == release_id).first()
    if not release:
        raise HTTPException(status_code=404, detail="Release not found")

    release.Title = title
    release.Year = year
    release.Cover_Url = cover_url if cover_url else None

    incoming_tracks = []

    min_len = min(len(track_titles), len(track_lengths), len(disc_numbers), len(track_numbers))
    for i in range(min_len):
        track_title = track_titles[i].strip()
        track_length = track_lengths[i] if track_lengths[i] is not None else None
        disc_number = disc_numbers[i] if disc_numbers[i] is not None else 1 
        track_number = track_numbers[i] if track_numbers[i] is not None else None

        if track_title: 
            incoming_tracks.append((track_title, track_length, track_number, disc_number))

    tracks_updated = update_release_tracks_if_changed(db, release, incoming_tracks)

    if not tracks_updated:
        db.add(release) 
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
    disc_numbers: list[int | None] = Form([]),
    track_numbers: list[int | None] = Form([]),
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
        disc_number = disc_numbers[i] if disc_numbers[i] is not None else 1
        track_number = track_numbers[i] if track_numbers[i] is not None else None
        
        if track_title: 
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

@router.get("/release/get-releases")
def get_releases(
    request: Request,
    search: str = Query("", alias="search"),
    sort_by: str = Query("year_desc", alias="sort_by"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1),
    db: Session = Depends(get_db)
):
    base_releases_query = db.query(Release).options(joinedload(Release.artist))

    if search:
        base_releases_query = base_releases_query.filter(
            func.lower(Release.Title).like(f"%{search.lower()}%")
        )

    if sort_by == "title":
        base_releases_query = base_releases_query.order_by(Release.Title)
    elif sort_by == "year_asc":
        base_releases_query = base_releases_query.order_by(Release.Year.asc())
    else:
        base_releases_query = base_releases_query.order_by(Release.Year.desc())

    total_releases = base_releases_query.count()
    total_pages = math.ceil(total_releases / page_size)
    
    releases = base_releases_query.offset((page - 1) * page_size).limit(page_size).all()

    return templates.TemplateResponse(
        "release.html",
        {
            "request": request,
            "releases": releases,
            "search": search,
            "sort_by": sort_by,
            "current_page": page,
            "page_size": page_size,
            "total_releases": total_releases,
            "total_pages": total_pages,
        },
    )