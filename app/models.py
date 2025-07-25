# app/models.py

from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from .db import Base


class Config(Base):
    __tablename__ = "config"

    Id = Column(Integer, primary_key=True, index=True)
    Key = Column(String, unique=True, nullable=False)
    Value = Column(String, nullable=False)

    def __repr__(self):
        return f"<Config(Id={self.Id}, Key={self.Key}, Value={self.Value})>"


class SabnzbdConfig(Base):
    __tablename__ = "sabnzbd_config"

    Id = Column(Integer, primary_key=True, index=True)
    Key = Column(String, unique=True, nullable=False)
    Value = Column(String, nullable=False)

    def __repr__(self):
        return f"<SabnzbdConfig(Id={self.Id}, Key={self.Key}, Value={self.Value})>"


class Artist(Base):
    __tablename__ = "artist"

    Id = Column(Integer, primary_key=True, index=True)
    Name = Column(String, unique=True, nullable=False)
    StartYear = Column(Integer, nullable=True)
    EndYear = Column(Integer, nullable=True)
    Disambiguation = Column(String, nullable=True)
    MusicbrainzId = Column(String, nullable=True, unique=True)
    DeezerId = Column(String, nullable=True, unique=True)
    DiscogsId = Column(String, nullable=True, unique=True)
    SpotifyId = Column(String, nullable=True, unique=True)
    AppleMusicId = Column(String, nullable=True, unique=True)
    TidalId = Column(String, nullable=True, unique=True)
    ImageUrl = Column(String, nullable=True)
    AlbumCount = Column(Integer, default=0)

    releases = relationship("Release", back_populates="artist", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Artist(Id={self.Id}, Name={self.Name})>"


class Release(Base):
    __tablename__ = "release"

    Id = Column(Integer, primary_key=True, index=True)
    ArtistId = Column(Integer, ForeignKey("artist.Id"), nullable=False)
    Title = Column(String, nullable=False)
    Year = Column(Integer, nullable=True)
    Type = Column(String, nullable=True)
    MusicbrainzId = Column(String, nullable=True, unique=True)
    DeezerId = Column(String, nullable=True, unique=True)
    DiscogsId = Column(String, nullable=True, unique=True)
    SpotifyId = Column(String, nullable=True, unique=True)
    AppleMusicId = Column(String, nullable=True, unique=True)
    TidalId = Column(String, nullable=True, unique=True)
    Cover_Url = Column(String, nullable=True)
    TrackFileCount = Column(Integer, default=0)

    artist = relationship("Artist", back_populates="releases")
    tracks = relationship("Track", back_populates="release", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Release(Id={self.Id}, Title={self.Title}, ArtistId={self.ArtistId})>"


class Track(Base):
    __tablename__ = "track"

    Id = Column(Integer, primary_key=True, index=True)
    ReleaseId = Column(Integer, ForeignKey("release.Id"), nullable=False)
    Title = Column(String, nullable=False)
    TrackNumber = Column(Integer, nullable=True)
    DiscNumber = Column(Integer, nullable=True)
    Duration = Column(Integer, nullable=True)

    release = relationship("Release", back_populates="tracks")

    def __repr__(self):
        return f"<Track(Id={self.Id}, Title={self.Title}, ReleaseId={self.ReleaseId})>"


class Indexer(Base):
    __tablename__ = "indexers"

    Id = Column(Integer, primary_key=True, index=True)
    Name = Column(String, unique=True, nullable=False)
    Url = Column(String, nullable=False)
    ApiKey = Column(String, nullable=False)

    def __repr__(self):
        return f"<Indexer(Id={self.Id}, Name={self.Name}, Url={self.Url})>"


class UnmatchedFile(Base):
    __tablename__ = "unmatched_files"

    Id = Column(Integer, primary_key=True, index=True)
    FilePath = Column(String, unique=True, nullable=False, index=True)
    FileName = Column(String, nullable=False)
    FileSize = Column(Integer)
    DetectedArtist = Column(String)
    DetectedAlbum = Column(String)
    DetectedTitle = Column(String)
    DetectedTrackNumber = Column(Integer)
    ScanTimestamp = Column(String)
    IsMatched = Column(Boolean, default=False)
    Ignored = Column(Boolean, default=False)

    def __repr__(self):
        return f"<UnmatchedFile(Id={self.Id}, FileName='{self.FileName}', DetectedArtist='{self.DetectedArtist}')>"


class ImportedFile(Base):
    __tablename__ = "imported_files"
    Id = Column(Integer, primary_key=True, index=True)
    FilePath = Column(String, unique=True, nullable=False, index=True)
    FileName = Column(String, nullable=False)
    FileSize = Column(Integer)
    ImportTimestamp = Column(String)
    TrackId = Column(Integer, ForeignKey("track.Id"), nullable=False)
    ReleaseId = Column(Integer, ForeignKey("release.Id"), nullable=False)
    ArtistId = Column(Integer, ForeignKey("artist.Id"), nullable=False)
    track = relationship("Track")

    def __repr__(self):
        return f"<ImportedFile(Id={self.Id}, FileName='{self.FileName}', TrackId={self.TrackId})>"