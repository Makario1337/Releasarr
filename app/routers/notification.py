# app/routers/notification.py
from fastapi import APIRouter, Request, Form, Depends, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from ..db import SessionLocal
from ..models import Config
import apprise
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

APPRISE_URL_CONFIG_KEY = "AppriseURL"

@router.get("/settings/notifications", response_class=HTMLResponse, name="get_notification_settings")
def get_notification_settings(request: Request, db: Session = Depends(get_db)):
    config = db.query(Config).filter(Config.Key == APPRISE_URL_CONFIG_KEY).first()
    apprise_url = config.Value if config else ""
    return templates.TemplateResponse(
        "notification.html",
        {
            "request": request,
            "apprise_url": apprise_url,
            "message": request.query_params.get("message"),
            "error": None,
        }
    )

@router.post("/settings/notifications", response_class=HTMLResponse)
def save_notification_settings(request: Request, apprise_url: str = Form(""), db: Session = Depends(get_db)):
    apprise_url = apprise_url.strip()
    config = db.query(Config).filter(Config.Key == APPRISE_URL_CONFIG_KEY).first()
    if config:
        config.Value = apprise_url
    else:
        config = Config(Key=APPRISE_URL_CONFIG_KEY, Value=apprise_url)
        db.add(config)
    db.commit()
    message = "Apprise URL saved successfully!"
    logger.info(f"Apprise URL settings saved: {apprise_url}")
    return templates.TemplateResponse(
        "notification.html",
        {
            "request": request,
            "apprise_url": apprise_url,
            "message": message,
            "error": None,
        },
    )

def send_test_notification_background(apprise_url: str):
    if not apprise_url:
        logger.warning("Test notification attempted without a configured Apprise URL.")
        return
    try:
        apobj = apprise.Apprise()
        apobj.add(apprise_url)
        apobj.notify(
            body="This is a test notification from Releasarr!",
            title="Releasarr Test Notification"
        )
        logger.info(f"Test notification successfully sent to Apprise URL: {apprise_url}")
    except Exception as e:
        logger.error(f"Failed to send test notification to Apprise URL {apprise_url}: {e}")

@router.post("/settings/notifications/test")
def test_notification(background_tasks: BackgroundTasks, apprise_url: str = Form(""), db: Session = Depends(get_db)):
    if not apprise_url:
        logger.error("Test notification request received without Apprise URL in form data.")
        raise HTTPException(status_code=400, detail="No Apprise URL provided for testing.")
    
    background_tasks.add_task(send_test_notification_background, apprise_url)
    logger.info("Test notification initiated as background task.")
    return RedirectResponse(
        url=router.url_path_for("get_notification_settings") + "?message=Test notification sent! Check your notification service and server logs.",
        status_code=303
    )
