import requests
from fastapi import APIRouter, Request, Form, Depends, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from ..db import SessionLocal
from ..models import Config
import logging

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

logger = logging.getLogger(__name__)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

SABNZBD_PATH_MAPPING_KEY = "SABnzbdPathMapping"
SABNZBD_IP_KEY = "SABnzbdIP"
SABNZBD_PORT_KEY = "SABNZbdPort"
SABNZBD_API_KEY = "SABNZbdAPIKey"

@router.get("/settings/sabnzbd", response_class=HTMLResponse, name="get_sabnzbd_settings")
def get_sabnzbd_settings(request: Request, db: Session = Depends(get_db)):
    path_mapping = db.query(Config).filter(Config.Key == SABNZBD_PATH_MAPPING_KEY).first()
    ip_address = db.query(Config).filter(Config.Key == SABNZBD_IP_KEY).first()
    port = db.query(Config).filter(Config.Key == SABNZBD_PORT_KEY).first()
    api_key = db.query(Config).filter(Config.Key == SABNZBD_API_KEY).first()

    return templates.TemplateResponse(
        "sabnzbd.html",
        {
            "request": request,
            "path_mapping": path_mapping.Value if path_mapping else "",
            "ip_address": ip_address.Value if ip_address else "",
            "port": port.Value if port else "",
            "api_key": api_key.Value if api_key else "",
            "message": request.query_params.get("message"),
            "error": request.query_params.get("error"),
        }
    )

@router.post("/settings/sabnzbd", response_class=HTMLResponse)
def save_sabnzbd_settings(
    request: Request,
    path_mapping: str = Form(""),
    ip_address: str = Form(""),
    port: str = Form(""),
    api_key: str = Form(""),
    db: Session = Depends(get_db)
):
    settings = {
        SABNZBD_PATH_MAPPING_KEY: path_mapping.strip(),
        SABNZBD_IP_KEY: ip_address.strip(),
        SABNZBD_PORT_KEY: port.strip(),
        SABNZBD_API_KEY: api_key.strip(),
    }
    for key, value in settings.items():
        config = db.query(Config).filter(Config.Key == key).first()
        if config:
            config.Value = value
        else:
            db.add(Config(Key=key, Value=value))
    db.commit()

    return templates.TemplateResponse(
        "sabnzbd.html",
        {
            "request": request,
            "path_mapping": settings[SABNZBD_PATH_MAPPING_KEY],
            "ip_address": settings[SABNZBD_IP_KEY],
            "port": settings[SABNZBD_PORT_KEY],
            "api_key": settings[SABNZBD_API_KEY],
            "message": "SABnzbd settings saved successfully!",
            "error": None,
        }
    )

def _send_sabnzbd_test_request(ip: str, port: str, api_key: str):
    if not (ip and port and api_key):
        logger.warning("SABnzbd test initiated without complete configuration (IP, Port, or API Key missing).")
        return
    try:
        url = f"http://{ip}:{port}/api?mode=version&output=json&apikey={api_key}"
        response = requests.get(url, timeout=5)
        if response.status_code == 200 and "version" in response.json():
            logger.info(f"SABnzbd connected successfully (Version: {response.json()['version']})")
        else:
            logger.error(f"SABnzbd test failed: Unexpected response or status code {response.status_code}. Response: {response.text[:200]}")
    except requests.exceptions.Timeout:
        logger.error("SABnzbd test failed: Connection timed out.")
    except requests.exceptions.ConnectionError as e:
        logger.error(f"SABnzbd test failed: Connection error - {e}")
    except Exception as e:
        logger.error(f"SABnzbd test failed: An unexpected error occurred - {e}")

@router.post("/settings/sabnzbd/test")
def test_sabnzbd_connection(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    ip = db.query(Config).filter(Config.Key == SABNZBD_IP_KEY).first()
    port = db.query(Config).filter(Config.Key == SABNZBD_PORT_KEY).first()
    api_key = db.query(Config).filter(Config.Key == SABNZBD_API_KEY).first()

    ip_val = ip.Value if ip else ""
    port_val = port.Value if port else ""
    api_key_val = api_key.Value if api_key else ""

    if not (ip_val and port_val and api_key_val):
        return RedirectResponse(
            url=router.url_path_for("get_sabnzbd_settings") + "?error=Please configure IP, Port, and API Key before testing.",
            status_code=303,
        )

    background_tasks.add_task(_send_sabnzbd_test_request, ip_val, port_val, api_key_val)

    return RedirectResponse(
        url=router.url_path_for("get_sabnzbd_settings") + "?message=SABnzbd test initiated. Check server logs for details.",
        status_code=303,
    )
