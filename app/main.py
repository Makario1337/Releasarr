from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .db import Base, engine
from .routers import index, artist, release, deezer
Base.metadata.create_all(bind=engine)

app = FastAPI()
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(index.router)
app.include_router(artist.router)
app.include_router(release.router)
app.include_router(deezer.router)
