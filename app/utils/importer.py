# app/utils/importer.py
import os
import datetime
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.id3 import ID3NoHeaderError
from sqlalchemy.orm import Session
from ..models import UnmatchedFile, Config, Artist, Release, Track, ImportedFile
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = ('.mp3', '.flac', '.ogg', '.wav', '.m4a')

def get_library_folder_path(db: Session) -> Optional[str]:
    config = db.query(Config).filter(Config.Key == "LibraryFolderPath").first()
    if config and config.Value:
        if os.path.isabs(config.Value) and os.path.isdir(config.Value):
            return config.Value
    logger.warning("Library folder path not configured or is invalid (not absolute or not a directory).")
    return None

def extract_metadata(file_path: str) -> Dict[str, Optional[str]]:
    metadata = {
        "artist": None,
        "album": None,
        "title": None,
        "tracknumber": None
    }
    try:
        if file_path.lower().endswith('.mp3'):
            audio = MP3(file_path)
            metadata["artist"] = audio.get('TPE1', [None])[0] or audio.get('artist', [None])[0]
            metadata["album"] = audio.get('TALB', [None])[0] or audio.get('album', [None])[0]
            metadata["title"] = audio.get('TIT2', [None])[0] or audio.get('title', [None])[0]
            track_num = audio.get('TRCK', [None])[0]
            if track_num:
                try: metadata["tracknumber"] = int(str(track_num).split('/')[0])
                except (ValueError, TypeError): pass
        elif file_path.lower().endswith('.flac'):
            audio = FLAC(file_path)
            metadata["artist"] = audio.get('artist', [None])[0]
            metadata["album"] = audio.get('album', [None])[0]
            metadata["title"] = audio.get('title', [None])[0]
            track_num = audio.get('tracknumber', [None])[0]
            if track_num:
                try: metadata["tracknumber"] = int(str(track_num).split('/')[0])
                except (ValueError, TypeError): pass
    except ID3NoHeaderError:
        logger.info(f"No ID3 tag found for {file_path}. Attempting filename parse.")
        filename = os.path.basename(file_path)
        parts = filename.split(' - ')
        if len(parts) >= 3:
            metadata["artist"] = parts[0].strip()
            metadata["album"] = parts[1].strip()
            metadata["title"] = parts[2].split('.')[0].strip()
        elif len(parts) == 2:
            metadata["artist"] = parts[0].strip()
            metadata["title"] = parts[1].split('.')[0].strip()
    except Exception as e:
        logger.error(f"Error extracting metadata from {file_path}: {e}", exc_info=True)

    for key, value in metadata.items():
        if value is not None:
            metadata[key] = str(value)

    return metadata

def scan_library(db: Session) -> List[UnmatchedFile]:
    library_path = get_library_folder_path(db)
    if not library_path:
        logger.warning("Library folder path not configured or invalid, skipping scan.")
        return []

    unmatched_files_found = []
    current_time = datetime.datetime.now().isoformat()

    existing_unmatched_paths = {uf.FilePath for uf in db.query(UnmatchedFile).all()}
    existing_imported_paths = {imf.FilePath for imf in db.query(ImportedFile).all()}


    for root, _, files in os.walk(library_path):
        for file in files:
            if file.lower().endswith(AUDIO_EXTENSIONS):
                full_path = os.path.join(root, file)

                if full_path in existing_unmatched_paths or full_path in existing_imported_paths:
                    logger.debug(f"Skipping already processed file: {full_path}")
                    continue

                logger.info(f"Found new file: {full_path}")
                file_size = os.path.getsize(full_path)
                metadata = extract_metadata(full_path)

                matched_track = None
                if metadata["artist"] and metadata["album"] and metadata["title"]:
                    try:
                        artist = db.query(Artist).filter(Artist.Name == metadata["artist"]).first()
                        if artist:
                            release = db.query(Release).filter(
                                Release.Title == metadata["album"],
                                Release.ArtistId == artist.Id
                            ).first()
                            if release:
                                track = db.query(Track).filter(
                                    Track.Title == metadata["title"],
                                    Track.ReleaseId == release.Id,
                                    Track.TrackNumber == metadata["tracknumber"] if metadata["tracknumber"] else None
                                ).first()
                                if track:
                                    matched_track = track
                    except Exception as e:
                        logger.error(f"Error during simplified auto-match for {full_path}: {e}", exc_info=True)

                if matched_track:
                    imported_file = ImportedFile(
                        FilePath=full_path,
                        FileName=file,
                        FileSize=file_size,
                        TrackId=matched_track.Id,
                        ImportTimestamp=current_time
                    )
                    db.add(imported_file)
                    logger.info(f"Auto-matched and imported: {full_path} to Track ID {matched_track.Id}")
                else:
                    unmatched_file = UnmatchedFile(
                        FilePath=full_path,
                        FileName=file,
                        FileSize=file_size,
                        DetectedArtist=metadata["artist"],
                        DetectedAlbum=metadata["album"],
                        DetectedTitle=metadata["title"],
                        DetectedTrackNumber=metadata["tracknumber"],
                        ScanTimestamp=current_time,
                        IsMatched=False
                    )
                    db.add(unmatched_file)
                    unmatched_files_found.append(unmatched_file)
                    logger.info(f"Added new unmatched file: {full_path}")

    db.commit()
    logger.info(f"Library scan completed. Found {len(unmatched_files_found)} new unmatched files.")
    return unmatched_files_found

def get_unmatched_files(db: Session) -> List[UnmatchedFile]:
    return db.query(UnmatchedFile).filter(UnmatchedFile.IsMatched == False).all()

def mark_file_as_matched(db: Session, file_id: int):
    unmatched_file = db.query(UnmatchedFile).filter(UnmatchedFile.Id == file_id).first()
    if unmatched_file:
        unmatched_file.IsMatched = True
        db.commit()
        logger.info(f"Marked unmatched file ID {file_id} as matched.")
    else:
        logger.warning(f"Attempted to mark unmatched file ID {file_id} as matched, but it was not found.")

