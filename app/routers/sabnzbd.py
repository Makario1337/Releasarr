# app/routers/sabnzbd.py
import requests
import os
import shutil
import logging
from fastapi import APIRouter, Request, Form, Depends, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from ..db import SessionLocal
from ..models import SabnzbdConfig

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

logger = logging.getLogger(__name__)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

SABNZBD_SETTINGS_DEFAULTS = {
    "SabnzbdPathMapping": "",
    "SabnzbdIP": "",
    "SabnzbdPort": "",
    "SabnzbdAPIKey": "",
}

@router.get("/settings/sabnzbd", response_class=HTMLResponse, name="get_sabnzbd_settings")
def get_sabnzbd_settings(request: Request, db: Session = Depends(get_db)):
    configs = {c.Key: c.Value for c in db.query(SabnzbdConfig).all()}

    settings = {key: configs.get(key, value) for key, value in SABNZBD_SETTINGS_DEFAULTS.items()}

    free_space_gb = None
    total_space_gb = None
    path_error = None
    path_mapping_value = settings.get("SabnzbdPathMapping")

    if path_mapping_value and os.path.exists(path_mapping_value):
        try:
            total, _, free = shutil.disk_usage(path_mapping_value)
            free_space_gb = round(free / (1024**3), 2)
            total_space_gb = round(total / (1024**3), 2)
        except FileNotFoundError:
            path_error = "Path not found or accessible."
            logger.error(f"SABnzbd path mapping error: {path_mapping_value} not found.")
        except OSError as e:
            path_error = f"Error accessing path: {e}"
            logger.error(f"SABnzbd path mapping OS error for {path_mapping_value}: {e}")
        except Exception as e:
            path_error = f"An unexpected error occurred: {e}"
            logger.error(f"SABnzbd path mapping unexpected error for {path_mapping_value}: {e}")
    elif path_mapping_value:
        path_error = "Path is not set or does not exist."

    return templates.TemplateResponse(
        "sabnzbd.html",
        {
            "request": request,
            "path_mapping": settings["SabnzbdPathMapping"],
            "ip_address": settings["SabnzbdIP"],
            "port": settings["SabnzbdPort"],
            "api_key": settings["SabnzbdAPIKey"],
            "free_space_gb": free_space_gb,
            "total_space_gb": total_space_gb,
            "path_error": path_error,
            "message": request.query_params.get("message"),
            "error": request.query_params.get("error"),
        }
    )

@router.post("/settings/sabnzbd", response_class=RedirectResponse)
def save_sabnzbd_settings(
    request: Request,
    path_mapping: str = Form(""),
    ip_address: str = Form(""),
    port: str = Form(""),
    api_key: str = Form(""),
    db: Session = Depends(get_db)
):
    settings_to_save = {
        "SabnzbdPathMapping": path_mapping.strip(),
        "SabnzbdIP": ip_address.strip(),
        "SabnzbdPort": port.strip(),
        "SabnzbdAPIKey": api_key.strip(),
    }
    
    for key, value in settings_to_save.items():
        config = db.query(SabnzbdConfig).filter(SabnzbdConfig.Key == key).first()
        if config:
            config.Value = value
        else:
            db.add(SabnzbdConfig(Key=key, Value=value))
    db.commit()

    return RedirectResponse(
        url=router.url_path_for("get_sabnzbd_settings") + "?message=SABnzbd settings saved successfully!",
        status_code=303,
    )

def _send_sabnzbd_test_request(ip: str, port: str, api_key: str):
    if not (ip and port and api_key):
        logger.warning("SABnzbd test initiated without complete configuration.")
        return
    try:
        url = f"http://{ip}:{port}/api?mode=version&output=json&apikey={api_key}"
        response = requests.get(url, timeout=5)
        if response.status_code == 200 and "version" in response.json():
            logger.info(f"SABnzbd connected successfully (Version: {response.json()['version']})")
        else:
            logger.error(f"SABnzbd test failed: Unexpected response or status code {response.status_code}. Response: {response.text[:200]}")
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
        logger.error(f"SABnzbd test failed: Connection error - {e}")
    except Exception as e:
        logger.error(f"SABnzbd test failed: An unexpected error occurred - {e}")

@router.post("/settings/sabnzbd/test-connection", name="test_sabnzbd_connection")
def test_sabnzbd_connection(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    configs = {c.Key: c.Value for c in db.query(SabnzbdConfig).all()}
    ip = configs.get("SabnzbdIP")
    port = configs.get("SabnzbdPort")
    api_key = configs.get("SabnzbdAPIKey")

    if not (ip and port and api_key):
        return RedirectResponse(
            url=router.url_path_for("get_sabnzbd_settings") + "?error=Please configure IP, Port, and API Key before testing.",
            status_code=303,
        )

    background_tasks.add_task(_send_sabnzbd_test_request, ip, port, api_key)

    return RedirectResponse(
        url=router.url_path_for("get_sabnzbd_settings") + "?message=SABnzbd connection test initiated. Check server logs for details.",
        status_code=303,
    )

def _perform_path_test(path: str):
    if not path:
        return "error", "No path configured for testing."

    test_file_name = ".sabnzbd_test_file.tmp"
    test_file_path = os.path.join(path, test_file_name)

    try:
        if not os.path.isdir(path):
            return "error", "Path does not exist or is not a directory."

        os.makedirs(path, exist_ok=True)
        with open(test_file_path, 'w') as f:
            f.write("This is a test.")
        os.remove(test_file_path)
        return "message", "Path is accessible and writeable!"
    except PermissionError:
        return "error", "Permission denied: Cannot write to this path."
    except FileNotFoundError:
        return "error", "Path not found."
    except OSError as e:
        return "error", f"Operating system error: {e}"
    except Exception as e:
        return "error", f"An unexpected error occurred: {e}"

@router.post("/settings/sabnzbd/test-path", name="test_sabnzbd_path")
def test_sabnzbd_path(db: Session = Depends(get_db)):
    path_mapping_config = db.query(SabnzbdConfig).filter(SabnzbdConfig.Key == "SabnzbdPathMapping").first()
    path_val = path_mapping_config.Value if path_mapping_config else ""
    
    status_type, status_message = _perform_path_test(path_val)

    return RedirectResponse(
        url=router.url_path_for("get_sabnzbd_settings") + f"?{status_type}={status_message}",
        status_code=303,
    )