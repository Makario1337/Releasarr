# app/routers/import_router.py
import os
import logging
from datetime import datetime
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from ..db import SessionLocal
from ..models import Config, UnmatchedFile, ImportedFile

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger(__name__)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

AUDIO_EXTENSIONS = ('.mp3', '.flac', '.wav', '.aac', '.ogg', '.m4a', '.alac')

@router.get("/import", response_class=HTMLResponse)
async def get_import_page(request: Request, db: Session = Depends(get_db)):
    library_folder_path = None
    import_folder_path = None
    message = request.query_params.get('message')
    error_message = request.query_params.get('error_message')
    unmatched_files = []

    try:
        lib_config_entry = db.query(Config).filter(Config.Key == "LibraryFolderPath").first()
        if lib_config_entry and lib_config_entry.Value:
            library_folder_path = lib_config_entry.Value

        import_config_entry = db.query(Config).filter(Config.Key == "ImportFolderPath").first()
        if import_config_entry and import_config_entry.Value:
            import_folder_path = import_config_entry.Value

        if not import_folder_path:
            error_message = error_message or "Import folder path is not set in settings. Please configure it under Settings."
            logger.warning("Import folder path is not set in the database (Config table).")
        elif not os.path.isdir(import_folder_path):
            error_message = error_message or f"Configured import folder path does not exist or is not a directory: {import_folder_path}. Please check your settings."
            logger.warning(f"Configured import folder path does not exist: {import_folder_path}")
        else:
            unmatched_files = db.query(UnmatchedFile).filter(UnmatchedFile.IsMatched == False).all()
            logger.info(f"Found {len(unmatched_files)} unmatched files.")
    except Exception as e:
        error_message = f"An unexpected error occurred while retrieving settings or unmatched files: {e}"
        logger.error(f"Error in import page: {e}", exc_info=True)

    return templates.TemplateResponse(
        "import.html",
        {
            "request": request,
            "library_folder_path": library_folder_path,
            "import_folder_path": import_folder_path,
            "message": message,
            "error_message": error_message,
            "unmatched_files": unmatched_files
        }
    )

@router.post("/import/scan")
async def scan_library(request: Request, db: Session = Depends(get_db)):
    import_folder_path = None
    try:
        import_config_entry = db.query(Config).filter(Config.Key == "ImportFolderPath").first()
        if import_config_entry and import_config_entry.Value:
            import_folder_path = import_config_entry.Value

        if not import_folder_path:
            return RedirectResponse(
                url="/import?error_message=Import folder path is not configured. Please set it in settings.",
                status_code=303
            )
        if not os.path.isdir(import_folder_path):
            return RedirectResponse(
                url=f"/import?error_message=Configured import folder path does not exist or is not a directory: {import_folder_path}.",
                status_code=303
            )

        found_files_count = 0
        new_unmatched_files_count = 0

        for root, _, files in os.walk(import_folder_path):
            for file_name in files:
                if file_name.lower().endswith(AUDIO_EXTENSIONS):
                    file_path = os.path.join(root, file_name)
                    found_files_count += 1

                    existing_unmatched = db.query(UnmatchedFile).filter(UnmatchedFile.FilePath == file_path).first()
                    existing_imported = db.query(ImportedFile).filter(ImportedFile.FilePath == file_path).first()

                    if not existing_unmatched and not existing_imported:
                        detected_artist = "Unknown Artist"
                        detected_album = "Unknown Album"
                        detected_title = os.path.splitext(file_name)[0]
                        file_size = os.path.getsize(file_path)
                        scan_timestamp = datetime.now().isoformat()

                        new_unmatched = UnmatchedFile(
                            FilePath=file_path,
                            FileName=file_name,
                            FileSize=file_size,
                            DetectedArtist=detected_artist,
                            DetectedAlbum=detected_album,
                            DetectedTitle=detected_title,
                            ScanTimestamp=scan_timestamp,
                            IsMatched=False
                        )
                        db.add(new_unmatched)
                        new_unmatched_files_count += 1
                        logger.info(f"Found new audio file: {file_path}")
        
        db.commit()
        logger.info(f"Scan complete. Found {found_files_count} audio files, {new_unmatched_files_count} new unmatched files added.")
        return RedirectResponse(
            url=f"/import?message=Scan complete. Found {found_files_count} audio files. {new_unmatched_files_count} new files added for matching.",
            status_code=303
        )

    except Exception as e:
        db.rollback()
        logger.error(f"Error during library scan: {e}", exc_info=True)
        return RedirectResponse(
            url=f"/import?error_message=An error occurred during scan: {e}",
            status_code=303
        )
