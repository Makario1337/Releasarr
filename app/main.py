import importlib
import pkgutil
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .db import Base, engine

app = FastAPI()

app.mount("/static", StaticFiles(directory="app/static"), name="static")

routers_path = os.path.join(os.path.dirname(__file__), "routers")

for finder, name, ispkg in pkgutil.iter_modules([routers_path]):
    module_path = f"app.routers.{name}"
    try:
        module = importlib.import_module(module_path)
        if hasattr(module, "router"):
            app.include_router(module.router)
            print(f"Successfully included router: {module_path}")
    except Exception as e:
        print(f"Failed to include router {module_path}: {e}")

Base.metadata.create_all(bind=engine)

