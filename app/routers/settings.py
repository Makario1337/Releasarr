# app/routers/settings.py 
import logging
import os
import shutil
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

def _perform_path_test(path: str):
    if not path:
        return "error_message", "No path provided for testing."

    if not os.path.isdir(path):
        return "error_message", "Path does not exist or is not a directory."

    test_file_name = ".releasarr_test_file.tmp"
    test_file_path = os.path.join(path, test_file_name)

    try:
        with open(test_file_path, 'w') as f:
            f.write("This is a test file to check write permissions.")
            
        os.remove(test_file_path)
        return "message", "Path is accessible and writeable!"
    except PermissionError:
        return "error_message", "Permission denied: Cannot write to this path."
    except FileNotFoundError:
        return "error_message", "Path not found during write test."
    except OSError as e:
        return "error_message", f"Operating system error during write test: {e}"
    except Exception as e:
        return "error_message", f"An unexpected error occurred during path test: {e}"

@router.get("/settings", response_class=HTMLResponse)
async def get_settings_page(request: Request, db: Session = Depends(get_db)):

    message = request.query_params.get('message')
    error_message = request.query_params.get('error_message')

    configs_from_db = {c.Key: c.Value for c in db.query(Config).all()}
    
    expected_keys = {
        "LibraryFolderPath",
        "ImportFolderPath",
        "FileRenamePattern",
        "FolderStructurePattern", 
        "SpotifyApiKey",
        "DeezerARLKey",
        "DiscogsApiKey",
    }
    
    configs_for_template = []
    
    for key in expected_keys:
        value = configs_from_db.get(key, "")
        
        config_entry = {
            "Key": key,
            "Value": value,
            "free_space_gb": None,
            "total_space_gb": None,
            "path_error": None
        }

        if key == "FileRenamePattern" and not value:
            config_entry["Value"] = "{tracknumber} {title} - {artist}"
        elif key == "FolderStructurePattern" and not value:
            config_entry["Value"] = "{artist}/{album}"
            
        if key in ["LibraryFolderPath", "ImportFolderPath"] and config_entry["Value"]:
            try:
                if os.path.exists(config_entry["Value"]):
                    total, _, free = shutil.disk_usage(config_entry["Value"])
                    config_entry["free_space_gb"] = round(free / (1024**3), 2)
                    config_entry["total_space_gb"] = round(total / (1024**3), 2)
                else:
                    config_entry["path_error"] = "Path not found or accessible."
            except FileNotFoundError:
                config_entry["path_error"] = "Path not found."
                logger.error(f"Settings path error: {config_entry['Value']} not found for {key}.")
            except OSError as e:
                config_entry["path_error"] = f"Error accessing path: {e}"
                logger.error(f"Settings path OS error for {config_entry['Value']}: {e}")
            except Exception as e:
                config_entry["path_error"] = f"An unexpected error occurred: {e}"
                logger.error(f"Settings path unexpected error for {config_entry['Value']}: {e}")

        configs_for_template.append(config_entry)

    configs_for_template.sort(key=lambda c: c["Key"])

    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "configs": configs_for_template,
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

@router.post("/settings/test-path", response_class=RedirectResponse)
async def test_general_path(
    request: Request,
    key: str = Form(...),
    value: str = Form(...),
    db: Session = Depends(get_db) 
):
    if key not in ["LibraryFolderPath", "ImportFolderPath"]:
        return RedirectResponse(
            url=f"/settings?error_message=Invalid key for path test: {key}",
            status_code=303
        )
    
    status_param, status_message = _perform_path_test(value)
    
    full_message = f"{key} test result: {status_message}"

    return RedirectResponse(
        url=f"/settings?{status_param}={full_message}",
        status_code=303
    )