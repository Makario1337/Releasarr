# app/routers/settings.py 
import logging
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from ..db import SessionLocal
from ..models import Config

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger(__name__)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/settings", response_class=HTMLResponse)
async def get_settings_page(request: Request, db: Session = Depends(get_db)):

    message = request.query_params.get('message')
    error_message = request.query_params.get('error_message')

    configs = db.query(Config).order_by(Config.Key).all()
    

    expected_keys = {
        "LibraryFolderPath",
        "ImportFolderPath",
        "FileRenamePattern",
        "FolderStructurePattern", 
        "SpotifyApiKey",
        "DeezerARLKey",
        "DiscogsApiKey",
    }
    
    existing_keys = {c.Key for c in configs}
    
    for key in expected_keys:
        if key not in existing_keys:
            default_value = ""
            if key == "FileRenamePattern":
                default_value = "{tracknumber} {title} - {artist}"
            elif key == "FolderStructurePattern":
                default_value = "{artist}/{album}"
            configs.append(Config(Key=key, Value=default_value))

    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "configs": configs,
            "message": message,
            "error_message": error_message,
        }
    )

@router.post("/settings", response_class=RedirectResponse)
async def save_setting(
    request: Request,
    key: str = Form(...),
    value: str = Form(...),
    db: Session = Depends(get_db)
):
    """
    Saves a single configuration key-value pair to the database.
    """
    try:
        config_entry = db.query(Config).filter(Config.Key == key).first()
        if config_entry:
            config_entry.Value = value
            logger.info(f"Updated setting: {key} = {value}")
        else:
            new_config = Config(Key=key, Value=value)
            db.add(new_config)
            logger.info(f"Added new setting: {key} = {value}")
        
        db.commit()
        return RedirectResponse(url="/settings?message=Setting saved successfully!", status_code=303)
    except Exception as e:
        db.rollback()
        logger.error(f"Error saving setting {key}: {e}", exc_info=True)
        return RedirectResponse(url=f"/settings?error_message=Failed to save setting {key}: {e}", status_code=303)

