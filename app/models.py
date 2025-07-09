from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from .db import Base

class Artist(Base):
    __tablename__ = "Artist"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    id_musicbrainz = Column(String, unique=True, index=True)
    id_discogs = Column(String, unique=True, index=True)
    id_spotify = Column(String, unique=True, index=True)
    id_deezer = Column(Integer, unique=True, index=True)
    
    releases = relationship("Release", back_populates="artist", cascade="all, delete-orphan")
    release_groups = relationship("ReleaseGroup", back_populates="artist")


class ReleaseGroup(Base):
    __tablename__ = "ReleaseGroup"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    artist_id = Column(Integer, ForeignKey("Artist.id"))
    releases = relationship("Release", back_populates="release_group")
    artist = relationship("Artist", back_populates="release_groups")


class Release(Base):
    __tablename__ = "Release"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    year = Column(Integer, nullable=True)
    artist_id = Column(Integer, ForeignKey("Artist.id"), nullable=False)
    release_group_id = Column(Integer, ForeignKey("ReleaseGroup.id"), nullable=True)
    cover_url = Column(String, nullable=True)
    artist = relationship("Artist", back_populates="releases")
    release_group = relationship("ReleaseGroup", back_populates="releases")
    tracks = relationship("Track", back_populates="release", cascade="all, delete-orphan")


class Track(Base):
    __tablename__ = "Track"
    
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    length = Column(Integer)
    featured_artists = Column(String)
    release_id = Column(Integer, ForeignKey("Release.id"))
    
    release = relationship("Release", back_populates="tracks")
