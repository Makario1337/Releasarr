# app/routers/tasks.py
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/tasks", response_class=HTMLResponse)
def about_page(request: Request):
    return templates.TemplateResponse(
        "tasks.html",
        {"request": request}
    )
