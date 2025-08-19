# app/routers/settings.py 
import logging
import os
import shutil
import requests
from fastapi import APIRouter, Request, Form, Depends, HTTPException, BackgroundTasks
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
        return "error_message", "Path not found during write test (unexpected)."
    except OSError as e:
        return "error_message", f"Operating system error during write test: {e}"
    except Exception as e:
        return "error_message", f"An unexpected error occurred during path test: {e}"

def _send_sabnzbd_test_request(ip: str, port: str, api_key: str, ssl: str):
    if not (ip and port and api_key):
        logger.warning("SABnzbd test initiated without complete configuration.")
        return

    try:
        url = f"{ssl}://{ip}:{port}/api?mode=version&output=json&apikey={api_key}"
        logger.info(f"SABnzbd connection with following URL:{ssl}://{ip}:{port}/api?mode=version&output=json&apikey=redacted")
        response = requests.get(url, timeout=5)
        if response.status_code == 200 and "version" in response.json():
            logger.info(f"SABnzbd connected successfully (Version: {response.json()['version']})")
        else:
            logger.error(f"SABnzbd test failed: Unexpected response or status code {response.status_code}. Response: {response.text[:200]}")
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
        logger.error(f"SABnzbd test failed: Connection error - {e}")
    except Exception as e:
        logger.error(f"SABnzbd test failed: An unexpected error occurred - {e}")

DEEZER_QUALITIES = ["FLAC", "MP3_320", "MP3_256", "MP3_128"]
SABNZBD_SSL_OPTIONS = ["http", "https"]

@router.get("/settings", response_class=HTMLResponse, name="get_settings_page")
async def get_settings_page(request: Request, db: Session = Depends(get_db)):
    message = request.query_params.get('message')
    error_message = request.query_params.get('error_message')

    configs_from_db = {c.Key: c.Value for c in db.query(Config).all()}
    
    grouped_settings_schema = {
        "API Keys": ["DiscogsApiKey", "SpotifyApiKey"],
        "Import/Library Paths": ["LibraryFolderPath", "ImportFolderPath"],
        "Deezer Settings": ["DeezerARLKey", "DeezerDownloadQuality"],
        "SABnzbd Settings": ["SabnzbdIP", "SabnzbdPort", "SabnzbdAPIKey", "SabnzbdPathMapping", "SabnzbdSSL"],
        "File Naming": ["FileRenamePattern", "FolderStructurePattern"]
    }

    grouped_configs = {group: [] for group in grouped_settings_schema.keys()}
    
    for group_name, keys in grouped_settings_schema.items():
        for key in keys:
            value = configs_from_db.get(key, "")
            
            config_entry = {
                "Key": key,
                "Value": value,
                "free_space_gb": None,
                "total_space_gb": None,
                "path_error": None,
                "options": None,
            }

            if key == "FileRenamePattern" and not value:
                config_entry["Value"] = "{tracknumber} {title} - {artist}"
            elif key == "FolderStructurePattern" and not value:
                config_entry["Value"] = "{artist}/{year} - {type} - {album}"
            elif key == "DeezerDownloadQuality":
                config_entry["options"] = DEEZER_QUALITIES
                if not value or value not in DEEZER_QUALITIES:
                    config_entry["Value"] = "MP3_320"
            elif key == "SabnzbdSSL":
                config_entry["options"] = SABNZBD_SSL_OPTIONS
                if not value or value not in SABNZBD_SSL_OPTIONS:
                    config_entry["Value"] = "http"
                
            if key in ["LibraryFolderPath", "ImportFolderPath", "SabnzbdPathMapping"] and config_entry["Value"]:
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

            grouped_configs[group_name].append(config_entry)
    
    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "grouped_configs": grouped_configs,
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
        if key == "DeezerDownloadQuality" and value not in DEEZER_QUALITIES:
            raise HTTPException(status_code=400, detail=f"Invalid value for DeezerDownloadQuality: {value}")
        if key == "SabnzbdSSL" and value not in SABNZBD_SSL_OPTIONS:
            raise HTTPException(status_code=400, detail=f"Invalid value for SabnzbdSSL: {value}")

        config_entry = db.query(Config).filter(Config.Key == key).first()
        if config_entry:
            config_entry.Value = value
            logger.info(f"Updated setting: {key} = {value}")
        else:
            new_config = Config(Key=key, Value=value)
            db.add(new_config)
            logger.info(f"Added new setting: {key} = {value}")
        
        db.commit()
        return RedirectResponse(url=f"{request.url_for('get_settings_page')}?message=Setting saved successfully!", status_code=303)
    except HTTPException as e:
        db.rollback()
        logger.error(f"Validation error saving setting {key}: {e.detail}", exc_info=True)
        return RedirectResponse(url=f"{request.url_for('get_settings_page')}?error_message=Failed to save setting {key}: {e.detail}", status_code=303)
    except Exception as e:
        db.rollback()
        logger.error(f"Error saving setting {key}: {e}", exc_info=True)
        return RedirectResponse(url=f"{request.url_for('get_settings_page')}?error_message=Failed to save setting {key}: {e}", status_code=303)

@router.post("/settings/test-path", response_class=RedirectResponse)
async def test_general_path(
    request: Request,
    key: str = Form(...),
    value: str = Form(...),
    db: Session = Depends(get_db)
):
    if key not in ["LibraryFolderPath", "ImportFolderPath", "SabnzbdPathMapping"]:
        return RedirectResponse(
            url=f"{request.url_for('get_settings_page')}?error_message=Invalid key for path test: {key}",
            status_code=303
        )
    
    status_param, status_message = _perform_path_test(value)
    
    full_message = f"{key} test result: {status_message}"

    return RedirectResponse(
        url=f"{request.url_for('get_settings_page')}?{status_param}={full_message}",
        status_code=303
    )

@router.post("/settings/test-connection", response_class=RedirectResponse)
def test_connection(
    request: Request, 
    background_tasks: BackgroundTasks, 
    db: Session = Depends(get_db)
):
    configs = {c.Key: c.Value for c in db.query(Config).all()}
    ip = configs.get("SabnzbdIP")
    port = configs.get("SabnzbdPort")
    api_key = configs.get("SabnzbdAPIKey")
    ssl = configs.get("SabnzbdSSL")

    if not (ip and port and api_key):
        return RedirectResponse(
            url=f"{request.url_for('get_settings_page')}?error_message=Please configure SABnzbd IP, Port, and API Key before testing.",
            status_code=303,
        )

    background_tasks.add_task(_send_sabnzbd_test_request, ip, port, api_key, ssl)
    return RedirectResponse(
        url=f"{request.url_for('get_settings_page')}?message=SABnzbd connection test initiated. Check server logs for details.",
        status_code=303,
    )