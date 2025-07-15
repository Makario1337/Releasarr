# app/routers/import_router.py
import os
import logging
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from ..db import SessionLocal
from ..models import Config, UnmatchedFile
from ..utils import importer

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger(__name__)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

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
            unmatched_files = importer.get_unmatched_files(db)
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
async def scan_import_folder(request: Request, db: Session = Depends(get_db)):

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

        newly_found_unmatched_files = importer.scan_import_folder(db)

        return RedirectResponse(
            url=f"/import?message=Scan complete. {len(newly_found_unmatched_files)} new files added for matching.",
            status_code=303
        )

    except Exception as e:
        db.rollback()
        logger.error(f"Error during import folder scan: {e}", exc_info=True)
        return RedirectResponse(
            url=f"/import?error_message=An error occurred during scan: {e}",
            status_code=303
        )

@router.post("/import/match/{file_id}")
async def match_file_endpoint(file_id: int, db: Session = Depends(get_db)):
    try:
        success = importer.match_unmatched_file(db, file_id)
        if success:
            return RedirectResponse(url="/import?message=File successfully matched and imported!", status_code=303)
        else:
            return RedirectResponse(url="/import?error_message=Could not find a direct match for the file. Manual intervention may be needed.", status_code=303)
    except Exception as e:
        db.rollback()
        logger.error(f"Error matching file ID {file_id}: {e}", exc_info=True)
        return RedirectResponse(url=f"/import?error_message=Error matching file: {e}", status_code=303)

@router.post("/import/ignore/{file_id}")
async def ignore_file_endpoint(file_id: int, db: Session = Depends(get_db)):
    try:
        success = importer.ignore_unmatched_file(db, file_id)
        if success:
            return RedirectResponse(url="/import?message=File successfully ignored!", status_code=303)
        else:
            return RedirectResponse(url="/import?error_message=Failed to ignore file.", status_code=303)
    except Exception as e:
        db.rollback()
        logger.error(f"Error ignoring file ID {file_id}: {e}", exc_info=True)
        return RedirectResponse(url=f"/import?error_message=Error ignoring file: {e}", status_code=303)
