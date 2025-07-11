from fastapi import APIRouter, Request, Form, Depends, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from ..db import SessionLocal
from ..models import Config, Indexer
import requests

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/settings/indexer", response_class=HTMLResponse)
def get_indexers_settings(request: Request, db: Session = Depends(get_db)):
    indexers = db.query(Indexer).order_by(Indexer.Name).all()
    return templates.TemplateResponse(
        "indexer.html",
        {
            "request": request,
            "indexers": indexers,
            "message": request.query_params.get('message'),
            "error": request.query_params.get('error')
        }
    )

@router.post("/settings/indexer/add")
def add_indexer(
    name: str = Form(...),
    url: str = Form(...),
    api_key: str = Form(...),
    db: Session = Depends(get_db)
):
    if not name.strip() or not url.strip() or not api_key.strip():
        raise HTTPException(status_code=400, detail="Name, URL, and API Key are required.")

    existing_indexer = db.query(Indexer).filter(Indexer.Name == name.strip()).first()
    if existing_indexer:
        return RedirectResponse(
            url=router.url_path_for("get_indexers_settings") + "?error=Indexer with this name already exists.",
            status_code=303
        )

    new_indexer = Indexer(Name=name.strip(), Url=url.strip(), ApiKey=api_key.strip())
    db.add(new_indexer)
    db.commit()
    db.refresh(new_indexer)
    
    return RedirectResponse(
        url=router.url_path_for("get_indexers_settings") + "?message=Indexer added successfully!",
        status_code=303
    )

@router.post("/settings/indexer/update/{indexer_id}")
def update_indexer(
    indexer_id: int,
    name: str = Form(...),
    url: str = Form(...),
    api_key: str = Form(...),
    db: Session = Depends(get_db)
):
    indexer = db.query(Indexer).filter(Indexer.Id == indexer_id).first()
    if not indexer:
        raise HTTPException(status_code=404, detail="Indexer not found")

    if not name.strip() or not url.strip() or not api_key.strip():
        raise HTTPException(status_code=400, detail="Name, URL, and API Key are required.")

    existing_by_name = db.query(Indexer).filter(Indexer.Name == name.strip(), Indexer.Id != indexer_id).first()
    if existing_by_name:
        return RedirectResponse(
            url=router.url_path_for("get_indexers_settings") + "?error=Another indexer with this name already exists.",
            status_code=303
        )

    indexer.Name = name.strip()
    indexer.Url = url.strip()
    indexer.ApiKey = api_key.strip()
    db.commit()
    db.refresh(indexer)

    return RedirectResponse(
        url=router.url_path_for("get_indexers_settings") + "?message=Indexer updated successfully!",
        status_code=303
    )

@router.post("/settings/indexer/delete/{indexer_id}")
def delete_indexer(indexer_id: int, db: Session = Depends(get_db)):
    indexer = db.query(Indexer).filter(Indexer.Id == indexer_id).first()
    if not indexer:
        raise HTTPException(status_code=404, detail="Indexer not found")
    
    db.delete(indexer)
    db.commit()

    return RedirectResponse(
        url=router.url_path_for("get_indexers_settings") + "?message=Indexer deleted successfully!",
        status_code=303
    )

def _send_indexer_test_request(indexer_url: str, indexer_api_key: str):
    if not (indexer_url and indexer_api_key):
        return False, "Indexer URL or API Key is missing in configuration."

    try:
        test_url = f"{indexer_url.rstrip('/')}/api?t=caps&apikey={indexer_api_key}"
        response = requests.get(test_url, timeout=10)

        if response.status_code == 200:
            if "caps" in response.text.lower() or "error" not in response.text.lower():
                return True, "Successfully connected to indexer."
            else:
                return False, f"Connected to indexer, but received an unexpected response: {response.text[:100]}..."
        else:
            return False, f"Failed to connect to indexer. Status code: {response.status_code}"
    except requests.exceptions.ConnectionError:
        return False, "Failed to connect to indexer. Check URL and ensure it's reachable."
    except requests.exceptions.Timeout:
        return False, "Connection to indexer timed out."
    except Exception as e:
        return False, f"An unexpected error occurred during test: {e}"

@router.post("/settings/indexer/test/{indexer_id}")
def test_indexer_connection(
    indexer_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    indexer = db.query(Indexer).filter(Indexer.Id == indexer_id).first()
    if not indexer:
        raise HTTPException(status_code=404, detail="Indexer not found")
    
    indexer_url = indexer.Url
    indexer_api_key = indexer.ApiKey

    if not (indexer_url and indexer_api_key):
        return RedirectResponse(
            url=router.url_path_for("get_indexers_settings") + "?error=Indexer URL or API Key is missing for testing.",
            status_code=303
        )

    background_tasks.add_task(_send_indexer_test_request, indexer_url, indexer_api_key)

    return RedirectResponse(
        url=router.url_path_for("get_indexers_settings") + f"?message=Test initiated for indexer '{indexer.Name}'. Check server logs.",
        status_code=303
    )
