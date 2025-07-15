import os
import datetime
import shutil
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.id3 import ID3NoHeaderError
from sqlalchemy.orm import Session
from ..models import UnmatchedFile, Config, Artist, Release, Track, ImportedFile
from typing import List, Dict, Optional, Tuple

import logging

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = ('.mp3', '.flac', '.ogg', '.wav', '.m4a')

def get_config_value(db: Session, key: str, default: Optional[str] = None) -> Optional[str]:
    config_entry = db.query(Config).filter(Config.Key == key).first()
    return config_entry.Value if config_entry else default

def resolve_path(path: Optional[str]) -> Optional[str]:
    if path is None:
        logger.debug("Path is None, returning None.")
        return None
    if not os.path.isabs(path):
        resolved_path = os.path.abspath(path)
        logger.debug(f"Resolved relative path '{path}' to absolute path '{resolved_path}'.")
        return resolved_path
    logger.debug(f"Path '{path}' is already absolute.")
    return path

def get_library_folder_path(db: Session) -> Optional[str]:
    path = get_config_value(db, "LibraryFolderPath")
    resolved_path = resolve_path(path)
    if resolved_path:
        if os.path.isdir(resolved_path):
            logger.info(f"Library folder path '{path}' resolved to valid directory: '{resolved_path}'.")
            return resolved_path
        else:
            logger.warning(f"Resolved library path '{resolved_path}' does not exist or is not a directory. Original config: '{path}'.")
    else:
        logger.warning(f"Library folder path '{path}' not configured or could not be resolved.")
    return None

def get_import_folder_path(db: Session) -> Optional[str]:
    path = get_config_value(db, "ImportFolderPath")
    resolved_path = resolve_path(path)
    if resolved_path:
        if os.path.isdir(resolved_path):
            logger.info(f"Import folder path '{path}' resolved to valid directory: '{resolved_path}'.")
            return resolved_path
        else:
            logger.warning(f"Resolved import path '{resolved_path}' does not exist or is not a directory. Original config: '{path}'.")
    else:
        logger.warning(f"Import folder path '{path}' not configured or could not be resolved.")
    return None

def get_file_naming_settings(db: Session) -> Dict[str, str]:
    return {
        "file_rename_pattern": get_config_value(db, "FileRenamePattern", "{tracknumber} {title} - {artist}"),
        "folder_structure_pattern": get_config_value(db, "FolderStructurePattern", "{artist}/{album}"),
    }

def format_path_string(pattern: str, metadata: Dict[str, Optional[str]]) -> str:
    """Formats a path string using metadata, replacing placeholders."""
    formatted_string = pattern
    for key, value in metadata.items():
        placeholder = "{" + key + "}"
        formatted_string = formatted_string.replace(placeholder, str(value or 'Unknown').strip())
    formatted_string = formatted_string.replace("{tracknumber}", "00")
    formatted_string = formatted_string.replace("{artist}", "Unknown Artist")
    formatted_string = formatted_string.replace("{album}", "Unknown Album")
    formatted_string = formatted_string.replace("{title}", "Unknown Title")
    
    invalid_chars = r'[<>:"/\\|?*]'
    formatted_string = "".join(c if c.isalnum() or c in [' ', '-', '_', '.', '/'] else '_' for c in formatted_string)
    
    return formatted_string.strip()


def extract_metadata(file_path: str) -> Dict[str, Optional[str]]:
    metadata = {
        "artist": None,
        "album": None,
        "title": None,
        "tracknumber": None,
        "discnumber": None
    }
    try:
        if file_path.lower().endswith('.mp3'):
            audio = MP3(file_path)
            metadata["artist"] = str(audio.get('TPE1', [None])[0] or audio.get('artist', [None])[0]) if audio.get('TPE1') or audio.get('artist') else None
            metadata["album"] = str(audio.get('TALB', [None])[0] or audio.get('album', [None])[0]) if audio.get('TALB') or audio.get('album') else None
            metadata["title"] = str(audio.get('TIT2', [None])[0] or audio.get('title', [None])[0]) if audio.get('TIT2') or audio.get('title') else None
            track_num = audio.get('TRCK', [None])[0]
            if track_num:
                try: metadata["tracknumber"] = int(str(track_num).split('/')[0])
                except (ValueError, TypeError): pass
            disc_num = audio.get('TPOS', [None])[0]
            if disc_num:
                try: metadata["discnumber"] = int(str(disc_num).split('/')[0])
                except (ValueError, TypeError): pass
        elif file_path.lower().endswith('.flac'):
            audio = FLAC(file_path)
            metadata["artist"] = str(audio.get('artist', [None])[0]) if audio.get('artist') else None
            metadata["album"] = str(audio.get('album', [None])[0]) if audio.get('album') else None
            metadata["title"] = str(audio.get('title', [None])[0]) if audio.get('title') else None
            track_num = audio.get('tracknumber', [None])[0]
            if track_num:
                try: metadata["tracknumber"] = int(str(track_num).split('/')[0])
                except (ValueError, TypeError): pass
            disc_num = audio.get('discnumber', [None])[0]
            if disc_num:
                try: metadata["discnumber"] = int(str(disc_num).split('/')[0])
                except (ValueError, TypeError): pass
    except ID3NoHeaderError:
        logger.info(f"No ID3 tag found for {file_path}. Attempting filename parse.")
        filename_without_ext = os.path.splitext(os.path.basename(file_path))[0]
        parts = filename_without_ext.split(' - ')
        if len(parts) >= 3:
            metadata["artist"] = parts[0].strip()
            metadata["album"] = parts[1].strip()
            metadata["title"] = parts[2].strip()
        elif len(parts) == 2:
            metadata["artist"] = parts[0].strip()
            metadata["title"] = parts[1].strip()
        else:
            metadata["title"] = filename_without_ext.strip()
    except Exception as e:
        logger.error(f"Error extracting metadata from {file_path}: {e}", exc_info=True)
    for key, value in metadata.items():
        if value is not None:
            metadata[key] = str(value)

    return metadata

def scan_import_folder(db: Session) -> Tuple[List[UnmatchedFile], int]:
    import_path = get_import_folder_path(db)
    if not import_path or not os.path.isdir(import_path):
        logger.warning(f"Import folder path '{import_path}' not configured or invalid, skipping scan.")
        return [], 0

    unmatched_files_found = []
    auto_matched_count = 0
    current_time = datetime.datetime.now().isoformat()

    existing_unmatched_paths = {uf.FilePath for uf in db.query(UnmatchedFile).all()}
    existing_imported_paths = {imf.FilePath for imf in db.query(ImportedFile).all()}

    for root, _, files in os.walk(import_path):
        for file_name in files:
            if not file_name.lower().endswith(AUDIO_EXTENSIONS):
                continue

            full_path = os.path.join(root, file_name)

            if full_path in existing_unmatched_paths or full_path in existing_imported_paths:
                continue

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
                            track_query = db.query(Track).filter(
                                Track.Title == metadata["title"],
                                Track.ReleaseId == release.Id
                            )
                            if metadata["tracknumber"]:
                                track_query = track_query.filter(Track.TrackNumber == metadata["tracknumber"])
                            matched_track = track_query.first()
                except Exception as e:
                    logger.error(f"Error during simplified auto-match for {full_path} during scan: {e}", exc_info=True)

            if matched_track:
                library_root_path = get_library_folder_path(db)
                if library_root_path:
                    naming_settings = get_file_naming_settings(db)
                    file_rename_pattern = naming_settings["file_rename_pattern"]
                    folder_structure_pattern = naming_settings["folder_structure_pattern"]

                    if metadata.get("tracknumber") is not None:
                        metadata["tracknumber"] = f"{int(metadata['tracknumber']):02d}"

                    relative_folder_path = format_path_string(folder_structure_pattern, metadata)
                    new_file_name_base = format_path_string(file_rename_pattern, metadata)
                    new_file_name = f"{new_file_name_base}{os.path.splitext(file_name)[1]}"
                    destination_dir = os.path.join(library_root_path, relative_folder_path)
                    destination_full_path = os.path.join(destination_dir, new_file_name)

                    try:
                        os.makedirs(destination_dir, exist_ok=True)
                        shutil.move(full_path, destination_full_path)

                        imported_file = ImportedFile(
                            FilePath=destination_full_path,
                            FileName=new_file_name,
                            FileSize=file_size,
                            TrackId=matched_track.Id,
                            ImportTimestamp=current_time,
                            ArtistId=matched_track.release.ArtistId
                        )
                        db.add(imported_file)
                        auto_matched_count += 1
                    except (OSError, shutil.Error) as e:
                        unmatched_file = UnmatchedFile(
                            FilePath=full_path,
                            FileName=file_name,
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
                else:
                    unmatched_file = UnmatchedFile(
                        FilePath=full_path,
                        FileName=file_name,
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
            else:
                unmatched_file = UnmatchedFile(
                    FilePath=full_path,
                    FileName=file_name,
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

    db.commit()
    logger.info(f"Import folder scan completed. Found {len(unmatched_files_found)} new unmatched files and auto-matched {auto_matched_count} files.")
    return unmatched_files_found, auto_matched_count


def get_unmatched_files(db: Session) -> List[UnmatchedFile]:
    return db.query(UnmatchedFile).filter(UnmatchedFile.IsMatched == False).all()

def ignore_unmatched_file(db: Session, file_id: int) -> bool:
    """Deletes an unmatched file entry from the database."""
    unmatched_file = db.query(UnmatchedFile).filter(UnmatchedFile.Id == file_id).first()
    if unmatched_file:
        db.delete(unmatched_file)
        db.commit()
        logger.info(f"Ignored and removed unmatched file ID {file_id}: {unmatched_file.FileName}.")
        return True
    else:
        logger.warning(f"Attempted to ignore file ID {file_id}, but it was not found in unmatched_files.")
        return False

def match_unmatched_file(db: Session, file_id: int) -> bool:
    unmatched_file = db.query(UnmatchedFile).filter(UnmatchedFile.Id == file_id).first()
    if not unmatched_file:
        logger.warning(f"Attempted to match file ID {file_id}, but it was not found in unmatched_files.")
        return False

    logger.info(f"Attempting to match and import file: {unmatched_file.FileName}")
    
    library_root_path = get_library_folder_path(db)
    if not library_root_path:
        logger.error("Library folder path is not configured or invalid. Cannot move file.")
        return False

    naming_settings = get_file_naming_settings(db)
    file_rename_pattern = naming_settings["file_rename_pattern"]
    folder_structure_pattern = naming_settings["folder_structure_pattern"]

    metadata = {
        "artist": unmatched_file.DetectedArtist,
        "album": unmatched_file.DetectedAlbum,
        "title": unmatched_file.DetectedTitle,
        "tracknumber": unmatched_file.DetectedTrackNumber,
    }

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
            logger.error(f"Error during database lookup for {unmatched_file.FileName}: {e}", exc_info=True)

    if not matched_track:
        logger.info(f"Could not find a direct database match for {unmatched_file.FileName} using detected metadata. File not moved.")
        return False

    file_extension = os.path.splitext(unmatched_file.FileName)[1]
    
    if metadata.get("tracknumber") is not None:
        metadata["tracknumber"] = f"{int(metadata['tracknumber']):02d}"
    
    relative_folder_path = format_path_string(folder_structure_pattern, metadata)
    new_file_name_base = format_path_string(file_rename_pattern, metadata)
    new_file_name = f"{new_file_name_base}{file_extension}"

    destination_dir = os.path.join(library_root_path, relative_folder_path)
    destination_full_path = os.path.join(destination_dir, new_file_name)

    try:
        logger.info(f"Attempting to create destination directory: {destination_dir}")
        os.makedirs(destination_dir, exist_ok=True)
        logger.info(f"Ensured destination directory exists: {destination_dir}")
    except OSError as e:
        logger.error(f"Error creating destination directory {destination_dir}: {e}", exc_info=True)
        return False

    try:
        logger.info(f"Attempting to move file from '{unmatched_file.FilePath}' to '{destination_full_path}'")
        shutil.move(unmatched_file.FilePath, destination_full_path)
        logger.info(f"Successfully moved file from '{unmatched_file.FilePath}' to '{destination_full_path}'")
    except shutil.Error as e:
        logger.error(f"ShutilError moving file {unmatched_file.FilePath} to {destination_full_path}: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred during file move for {unmatched_file.FileName}: {e}", exc_info=True)
        return False

    try:
        imported_file = ImportedFile(
            FilePath=destination_full_path,
            FileName=new_file_name,
            FileSize=unmatched_file.FileSize,
            TrackId=matched_track.Id,
            ImportTimestamp=datetime.datetime.now().isoformat(),
            ArtistId=matched_track.release.ArtistId,
            ReleaseId=matched_track.ReleaseId
        )
        db.add(imported_file)
        db.delete(unmatched_file)
        db.commit()
        logger.info(f"Successfully updated database records for {unmatched_file.FileName} (Track ID {matched_track.Id}) at {destination_full_path}")
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating database after file move for {unmatched_file.FileName}: {e}. File might be moved but not recorded correctly.", exc_info=True)
        return False
