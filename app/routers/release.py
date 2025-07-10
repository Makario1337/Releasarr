from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from ..db import SessionLocal

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")