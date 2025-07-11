from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy import UniqueConstraint
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
    SpotifyId = Column(String, unique=True, index=True)
    AppleMusicId = Column(String, unique=True, index=True)
    TidalId = Column(String, unique=True, index=True)
    ImageUrl = Column(String, nullable=True)
    AlbumCount = Column(Integer)    

    releases = relationship(
        "Release", back_populates="artist", cascade="all, delete-orphan"
    )


class Release(Base):
    __tablename__ = "release"

    Id = Column(Integer, primary_key=True, unique=True, index=True)
    Title = Column(String, nullable=False)
    Year = Column(Integer)
    TrackFileCount = Column(Integer)
    ArtistId = Column(Integer, ForeignKey("artist.Id"), nullable=False)
    Cover_Url = Column(String, nullable=True)
    DeezerAlbumId = Column(String, unique=True, index=False)
    DiscogsReleaseId = Column(String, unique=True, index=False)
    MusicbrainzReleaseId = Column(String, unique=True, index=False)
    SpotifyAlbumId = Column(String, unique=True, index=False)
    TidalAlbumId = Column(String, unique=True, index=False)
    AppleMusicAlbumId = Column(String, unique=True, index=False)
    NormalizedTitle = Column(String, index=True)
    

    artist = relationship("Artist", back_populates="releases")
    tracks = relationship(
        "Track", back_populates="release", cascade="all, delete-orphan"
    )
    __table_args__ = (
    UniqueConstraint("ArtistId", "NormalizedTitle", "Year", name="uq_release_dedupe"),
)


class Track(Base):
    __tablename__ = "track"

    Id = Column(Integer, primary_key=True)
    TrackNumber = Column(Integer, nullable=False)
    DiscNumber = Column(Integer, nullable=False)
    Title = Column(String, nullable=False)
    Length = Column(Integer)
    Featured_Artists = Column(String)
    SizeOnDisk = Column(Integer)
    ReleaseId = Column(Integer, ForeignKey("release.Id"), nullable=False)
    
    release = relationship("Release", back_populates="tracks")
    
    __table_args__ = (
        UniqueConstraint('ReleaseId', 'DiscNumber', 'TrackNumber', name='uq_release_disc_track'),
    )

class Config(Base):
    __tablename__ = "config"

    Id = Column(Integer, primary_key=True, index=True)
    Key = Column(String, unique=True, nullable=False)
    Value = Column(String, nullable=False)

    def __repr__(self):
        return f"<Config(Id={self.Id}, Key={self.Key}, Value={self.Value})>"