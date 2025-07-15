# app/routers/artist.py
from fastapi import APIRouter, Request, Form, Depends, HTTPException, Query
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from collections import defaultdict
from ..models import Release, Artist, Config, ImportedFile, Track
from ..db import SessionLocal
import math

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/artist/add-artist")
def add_artist(name: str = Form(...), db: Session = Depends(get_db)):
    if not name.strip():
        raise HTTPException(status_code=400, detail="Artist name cannot be empty.")
    
    existing_artist = db.query(Artist).filter(Artist.Name.ilike(name.strip())).first()
    if existing_artist:
        raise HTTPException(status_code=400, detail="Artist with this name already exists.")

    new_artist = Artist(Name=name.strip())
    db.add(new_artist)
    db.commit()
    db.refresh(new_artist)
    return RedirectResponse("/", status_code=303)

@router.get("/artist/get-artist/{artist_id}")
def show_releases_by_artist(
    artist_id: int,
    request: Request,
    search: str = Query("", alias="search", description="Search term for release titles"),
    sort_by: str = Query("title", alias="sort_by", description="Field to sort releases by (title, year, tracks)"),
    page: int = Query(1, ge=1, description="Current page number for pagination"),
    page_size: int = Query(5, ge=1, description="Number of releases per page"),
    db: Session = Depends(get_db),
):
    artist = db.query(Artist).filter_by(Id=artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")

    base_releases_query = db.query(Release).filter_by(ArtistId=artist_id)
    if search:
        base_releases_query = base_releases_query.filter(Release.Title.ilike(f"%{search}%"))

    total_releases = base_releases_query.count()
    total_pages = math.ceil(total_releases / page_size)

    if sort_by == "title":
        releases = base_releases_query.order_by(Release.Title.asc())
    elif sort_by == "year":
        releases = base_releases_query.order_by(Release.Year.desc())
    elif sort_by == "tracks":
        releases = base_releases_query.order_by(Release.TrackFileCount.desc())
    else:
        releases = base_releases_query.order_by(Release.Title.asc())

    releases = releases.offset((page - 1) * page_size).limit(page_size).all()

    settings = db.query(Config).all()

    imported_files = db.query(ImportedFile).filter_by(ArtistId=artist_id).all()

    imported_file_counts = defaultdict(int)
    for file in imported_files:
        imported_file_counts[file.ReleaseId] += 1

    return templates.TemplateResponse(
        "artist.html",
        {
            "request": request,
            "artist": artist,
            "releases": releases,
            "search": search,
            "sort_by": sort_by,
            "current_page": page,
            "total_pages": total_pages,
            "page_size": page_size,
            "total_releases": total_releases,
            "settings": settings,
            "imported_file_counts": dict(imported_file_counts),
        },
    )

@router.get("/artist/set-external-ids/{artist_id}")
def show_set_external_ids_page(
    artist_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    artist = db.query(Artist).filter_by(Id=artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    return templates.TemplateResponse(
        "set_external_ids.html",
        {"request": request, "artist": artist}
    )

@router.post("/artist/delete-artist/{artist_id}")
def delete_artist(artist_id: int, db: Session = Depends(get_db)):
    artist = db.query(Artist).filter_by(Id=artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    db.delete(artist)
    db.commit()
    return RedirectResponse("/", status_code=303)

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
    artist = db.query(Artist).filter_by(Id=artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")

    def norm(val): return val.strip() if val and val.strip() else None

    artist.AppleMusicId = norm(applemusic_id)
    artist.DeezerId = norm(deezer_id)
    artist.DiscogsId = norm(discogs_id)
    artist.MusicbrainzId = norm(musicbrainz_id)
    artist.SpotifyId = norm(spotify_id)
    artist.TidalId = norm(tidal_id)

    db.commit()
    return RedirectResponse(f"/artist/get-artist/{artist_id}", status_code=303)

@router.post('/artist/update-cover/{artist_id}')
def update_artist_cover(artist_id: int, cover_url: str = Form(...), db: Session = Depends(get_db)):
    artist = db.query(Artist).filter_by(Id=artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    artist.ImageUrl = cover_url
    db.commit()
    return RedirectResponse(f"/artist/get-artist/{artist_id}", status_code=303)