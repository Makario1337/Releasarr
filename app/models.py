from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from .db import Base

class Artist(Base):
    __tablename__ = "artist"
    
    Id = Column(Integer, primary_key=True, index=True)
    Name = Column(String, index=True, nullable=False)
    StartYear = Column(Integer)
    EndYear = Column(Integer)
    Disambiguation = Column(String)
    MusicbrainzId = Column(String, unique=True, index=True)
    DeezerId = Column(String, unique=True, index=True)
    DiscogsId = Column(String, unique=True, index=True)
    SpotifyId = Column(String, unique=True, index=True)  # changed from Integer
    AlbumCount = Column(Integer)
    TrackFileCount = Column(Integer)
    TotalTrackFileCount = Column(Integer)
    
    releases = relationship("Release", back_populates="artist", cascade="all, delete-orphan")


class Release(Base):
    __tablename__ = "release"
    
    Id = Column(Integer, primary_key=True, unique=True, index=True)
    Title = Column(String, nullable=False)
    Year = Column(Integer)
    ArtistId = Column(Integer, ForeignKey("artist.Id"), nullable=False)
    cover_url = Column(String, nullable=True)
    
    artist = relationship("Artist", back_populates="releases")
    tracks = relationship("Track", back_populates="release", cascade="all, delete-orphan")


class Track(Base):
    __tablename__ = "track"
    
    Id = Column(Integer, primary_key=True)
    Title = Column(String, nullable=False)
    Length = Column(Integer)
    Featured_Artists = Column(String)
    SizeOnDisk = Column(Integer)
    
    ReleaseId = Column(Integer, ForeignKey("release.Id"), nullable=False)
    release = relationship("Release", back_populates="tracks")