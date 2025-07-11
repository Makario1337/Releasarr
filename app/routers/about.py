from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/about", response_class=HTMLResponse)
def about_page(request: Request):
    """
    Renders the about page for the application.
    """
    return templates.TemplateResponse(
        "about.html",
        {"request": request}
    )
