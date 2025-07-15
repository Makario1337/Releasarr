# app/routers/index.py
from fastapi import APIRouter, Request, Form, Depends, HTTPException, Query
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from ..models import Artist, ImportedFile, Track, Release
from ..db import SessionLocal

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        

@router.get("/")
def show_artists(
    request: Request,
    search: str = Query(default=""),
    db: Session = Depends(get_db)
):
    artists = db.query(Artist).filter(Artist.Name.ilike(f"%{search}%")).all()
    
    artist_file_count_total = (
    db.query(Release.ArtistId, func.count(Track.Id))
    .join(Release, Track.ReleaseId == Release.Id)
    .group_by(Release.ArtistId)
    .all()
    )
    artist_file_count_total_dict = dict(artist_file_count_total)
      
    imported_file_counts = (
    db.query(ImportedFile.ArtistId, func.count(ImportedFile.Id))
    .group_by(ImportedFile.ArtistId)
    .all()
    )
    imported_file_counts_dict = dict(imported_file_counts)
    
    artist_file_size_total = (
    db.query(ImportedFile.ArtistId, func.sum(ImportedFile.FileSize))
    .group_by(ImportedFile.ArtistId)
    .all()
    )
    artist_file_size_total_dict = dict(artist_file_size_total)
    print(artist_file_size_total_dict)


    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "artists": artists,
            "search": search,
            "imported_file_counts": imported_file_counts_dict,
            "artist_file_count_total": artist_file_count_total_dict,
            "artist_file_size_total": artist_file_size_total_dict
        }
    )