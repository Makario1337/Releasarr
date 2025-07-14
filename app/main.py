import importlib
import pkgutil
import os
import logging
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .db import Base, engine

log_directory = "logs"
log_file_path = os.path.join(log_directory, "app.log")

os.makedirs(log_directory, exist_ok=True)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

handler = RotatingFileHandler(log_file_path, maxBytes=1024 * 1024, backupCount=5, encoding='utf-8')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

app = FastAPI()

app.mount("/static", StaticFiles(directory="app/static"), name="static")

routers_path = os.path.join(os.path.dirname(__file__), "routers")

for finder, name, ispkg in pkgutil.iter_modules([routers_path]):
    module_path = f"app.routers.{name}"
    try:
        module = importlib.import_module(module_path)
        if hasattr(module, "router"):
            app.include_router(module.router)
            logger.info(f"Successfully included router: {module_path}")
    except Exception as e:
        logger.error(f"Failed to include router {module_path}: {e}")

Base.metadata.create_all(bind=engine)
