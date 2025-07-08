from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .db import Base, engine
from .routers import artists, home, releases

Base.metadata.create_all(bind=engine)

app = FastAPI()
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(home.router)
app.include_router(artists.router)
app.include_router(releases.router)
