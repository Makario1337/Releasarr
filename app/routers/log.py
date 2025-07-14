import os
import logging
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

LOG_DIR = "logs"
LOG_FILE_PATH = os.path.join(LOG_DIR, "app.log")

os.makedirs(LOG_DIR, exist_ok=True)

if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE_PATH, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
logger = logging.getLogger(__name__)

def read_log_file():
    try:
        if not os.path.exists(LOG_FILE_PATH):
            return "Log file not found."
        with open(LOG_FILE_PATH, 'r', encoding='utf-8') as f:
            return f.read()
    except UnicodeDecodeError as e:
        logger.error(f"UnicodeDecodeError when reading log file: {e}")
        return f"Error reading log file: {e}. It might contain non-UTF-8 characters."
    except Exception as e:
        logger.error(f"An unexpected error occurred while reading the log file: {e}")
        return f"An error occurred: {e}"

def clear_log_file():
    try:
        with open(LOG_FILE_PATH, 'w', encoding='utf-8') as f:
            f.truncate(0)
        logger.info("Log file cleared successfully.")
        return True
    except Exception as e:
        logger.error(f"Error clearing log file: {e}")
        return False

@router.get("/logs", response_class=HTMLResponse)
async def get_logs(request: Request):
    logs_content = read_log_file()
    return templates.TemplateResponse(
        "log.html",
        {"request": request, "logs_content": logs_content}
    )

@router.post("/logs/clear")
async def clear_logs_endpoint():
    if clear_log_file():
        return RedirectResponse(url="/logs?message=Logs cleared successfully!", status_code=303)
    return RedirectResponse(url="/logs?error=Failed to clear logs.", status_code=303)

@router.get("/logs/download")
async def download_log_file():
    if not os.path.exists(LOG_FILE_PATH):
        raise HTTPException(status_code=404, detail="Log file not found.")
    return FileResponse(
        path=LOG_FILE_PATH,
        media_type="text/plain",
        filename="app.log",
    )
