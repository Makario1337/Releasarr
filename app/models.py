from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from .db import Base

class Artist(Base):
    __tablename__ = "artists"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    
    releases = relationship("Release", back_populates="artist", cascade="all, delete-orphan")

class Release(Base):
    __tablename__ = "releases"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    year = Column(Integer, nullable=True)
    artist_id = Column(Integer, ForeignKey("artists.id"), nullable=False)
    cover_url = Column(String, nullable=True)  # Optional URL or image path
    artist = relationship("Artist", back_populates="releases")
    songs = relationship("Song", back_populates="release", cascade="all, delete-orphan")  # New relationship


class Song(Base):
    __tablename__ = "songs"

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    length = Column(Integer)  # in seconds
    featured_artists = Column(String)  # optional
    release_id = Column(Integer, ForeignKey("releases.id"))

    release = relationship("Release", back_populates="songs")