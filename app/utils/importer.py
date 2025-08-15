# /app/utils/importer.py
import os
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import shutil
import re

from ..models import Config, Artist, Release, Track, ImportedFile, UnmatchedFile

try:
    from mutagen.mp3 import MP3
    from mutagen.flac import FLAC
    from mutagen.id3 import ID3NoHeaderError
    MUTAGEN_AVAILABLE = True
except ImportError:
    logging.warning("Mutagen library not found. File metadata extraction will be limited.")
    MUTAGEN_AVAILABLE = False

logger = logging.getLogger(__name__)

def _get_config_value(db: Session, key: str) -> str | None:
    config_entry = db.query(Config).filter(Config.Key == key).first()
    return config_entry.Value if config_entry else None

def get_primary_artist_name(artist_name: str) -> str:
    if not artist_name:
        return 'Unknown Artist'
    
    if ' feat. ' in artist_name:
        return artist_name.split(' feat. ')[0].strip()
    if ' ft. ' in artist_name:
        return artist_name.split(' ft. ')[0].strip()
    if ' & ' in artist_name:
        return artist_name.split(' & ')[0].strip()
    if ' with ' in artist_name:
        return artist_name.split(' with ')[0].strip()

    return artist_name

def _get_or_create_artist(db: Session, artist_name: str) -> Artist:
    artist = db.query(Artist).filter(Artist.Name == artist_name).first()
    
    if not artist:
        logger.info(f"Artist '{artist_name}' not found, creating new artist.")
        artist = Artist(Name=artist_name)
        db.add(artist)
        db.flush()
        logger.debug(f"Created new artist: {artist.Name} (ID: {artist.Id})")
    
    return artist

def _get_or_create_release(db: Session, artist_id: int, release_title: str, release_year: int = None, release_type: str = 'Album') -> Release:
    release = db.query(Release).filter(
        Release.ArtistId == artist_id,
        Release.Title == release_title
    ).first()

    if not release:
        logger.info(f"Release '{release_title}' for Artist ID {artist_id} not found, creating new release.")
        release = Release(
            ArtistId=artist_id,
            Title=release_title,
            Year=release_year,
            Type=release_type
        )
        db.add(release)
        db.flush()
        logger.debug(f"Created new release: {release.Title} (ID: {release.Id}) for Artist ID {artist_id}")
    return release

def _get_or_create_track(db: Session, release_id: int, artist_id: int, track_title: str, track_number: int = None, duration: int = None) -> Track:
    track = db.query(Track).filter(
        Track.ReleaseId == release_id,
        Track.Title == track_title
    ).first()
    if not track:
        logger.info(f"Track '{track_title}' for Release ID {release_id} not found, creating new track.")
        track = Track(
            ReleaseId=release_id,
            Title=track_title,
            TrackNumber=track_number,
            Duration=duration
        )
        db.add(track)
        db.flush()
        logger.debug(f"Created new track: {track.Title} (ID: {track.Id}) for Release ID {release_id}")
    return track

def sanitize_path_component(name: str) -> str:
    if not isinstance(name, str):
        name = str(name)
    invalid_chars = r'[<>:"/\\|?*\x00-\x1f]'
    sanitized_name = re.sub(invalid_chars, '', name).strip()
    sanitized_name = sanitized_name.replace(':', ' - ')
    sanitized_name = sanitized_name.replace('/', '_')
    sanitized_name = sanitized_name.replace('\\', '_')
    return sanitized_name

def _extract_metadata(file_path: str) -> dict:
    metadata = {
        'artist': None,
        'album': None,
        'title': None,
        'track_number': None,
        'track_total': None,
        'duration': None,
        'year': None,
        'is_single': False,
        'release_type': 'Unknown Type',
        'disknumber': None,
        'cover_path': None,
        'albumartist': None,
    }

    file_name = os.path.basename(file_path)
    current_filename_no_ext = os.path.splitext(file_name)[0]
    source_dir = os.path.dirname(file_path)

    try:
        for f in os.listdir(source_dir):
            if f.lower().startswith('cover.') and f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                metadata['cover_path'] = os.path.join(source_dir, f)
                logger.debug(f"Found local cover art: {metadata['cover_path']}")
                break
    except Exception as e:
        logger.warning(f"Could not scan for cover art in {source_dir}: {e}")

    metadata['title'] = current_filename_no_ext

    if MUTAGEN_AVAILABLE:
        try:
            audio = None
            if file_path.lower().endswith('.mp3'):
                audio = MP3(file_path)
            elif file_path.lower().endswith('.flac'):
                audio = FLAC(file_path)
            
            if audio:
                def get_tag_value(audio_obj, keys):
                    for key in keys:
                        if key in audio_obj:
                            val = audio_obj[key]
                            if isinstance(val, list) and val:
                                return str(val[0]).strip()
                            return str(val).strip()
                    return None

                metadata['artist'] = get_tag_value(audio, ['artist', 'TPE1'])
                metadata['albumartist'] = get_tag_value(audio, ['albumartist', 'TPE2'])
                metadata['album'] = get_tag_value(audio, ['album', 'TALB'])
                metadata['title'] = get_tag_value(audio, ['title', 'TIT2', 'TITLE'])
                
                track_num_str = get_tag_value(audio, ['tracknumber', 'TRCK', 'TRACKNUMBER'])
                if track_num_str:
                    try:
                        parts = track_num_str.split('/')
                        metadata['track_number'] = int(parts[0])
                        if len(parts) > 1:
                            metadata['track_total'] = int(parts[1])
                    except (ValueError, IndexError):
                        pass
                
                year_str = get_tag_value(audio, ['date', 'TDRC', 'TYER', 'YEAR'])
                if year_str:
                    try:
                        metadata['year'] = int(year_str.split('-')[0])
                    except (ValueError, IndexError):
                        pass

                disc_num_str = get_tag_value(audio, ['discnumber', 'TPOS'])
                if disc_num_str:
                    try:
                        metadata['disknumber'] = int(disc_num_str.split('/')[0])
                    except (ValueError, IndexError):
                        pass

                if audio.info and audio.info.length:
                    metadata['duration'] = int(audio.info.length)

        except ID3NoHeaderError:
            logging.warning(f"No ID3 header found for MP3 file: {file_path}")
        except Exception as e:
            logging.error(f"Error extracting metadata from {file_path} using mutagen: {e}", exc_info=True)
    else:
        logging.warning(f"Mutagen not available, cannot extract rich metadata for {file_path}. Relying on filename/folder structure.")
    
    parent_dir = os.path.basename(os.path.dirname(file_path))
    grandparent_dir = os.path.basename(os.path.dirname(os.path.dirname(file_path)))
    
    if not metadata['artist']:
        if " - " in parent_dir:
            match = re.match(r"^(.*?)\s*-\s*.*$", parent_dir)
            if match:
                metadata['artist'] = match.group(1).strip()
        elif grandparent_dir and parent_dir != grandparent_dir:
            metadata['artist'] = grandparent_dir.strip()
        
        if not metadata['artist']:
            metadata['artist'] = 'Unknown Artist'
        logger.debug(f"Fallback: Artist set to: {metadata['artist']}")

    if not metadata['album']:
        if " - " in parent_dir:
            match = re.match(r"^.*?\s*-\s*(.*)$", parent_dir)
            if match:
                metadata['album'] = match.group(1).strip()
        elif parent_dir:
            metadata['album'] = parent_dir.strip()
        
        if not metadata['album']:
            metadata['album'] = 'Unknown Album'
        logger.debug(f"Fallback: Album set to: {metadata['album']}")

    if not metadata['title']:
        metadata['title'] = current_filename_no_ext.strip()
        logger.debug(f"Fallback: Title set to filename: {metadata['title']}")

    if metadata['track_number'] is not None and metadata['title']:
        patterns = [
            re.compile(r"^{:02d}\s*-\s*(.*)$".format(metadata['track_number']), re.IGNORECASE),
            re.compile(r"^{}\s*-\s*(.*)$".format(metadata['track_number']), re.IGNORECASE),
            re.compile(r"^{:02d}\s*(.*)$".format(metadata['track_number']), re.IGNORECASE),
            re.compile(r"^{}\s*(.*)$".format(metadata['track_number']), re.IGNORECASE),
        ]
        for pattern in patterns:
            match = pattern.match(metadata['title'])
            if match:
                metadata['title'] = match.group(1).strip()
                logger.debug(f"Refined title by removing track prefix: {metadata['title']}")
                break
    
    if metadata['track_total'] is not None:
        if metadata['track_total'] <= 1:
            metadata['is_single'] = True
            metadata['release_type'] = 'Single'
    elif metadata['album'] and metadata['title'] and \
       (metadata['album'].lower() == metadata['title'].lower() or \
        metadata['album'].lower().replace("single", "").strip() == metadata['title'].lower().replace("single", "").strip()):
        metadata['is_single'] = True
        metadata['release_type'] = 'Single'
    else:
        metadata['release_type'] = 'Album'

    metadata['artist'] = metadata['artist'] if metadata['artist'] else 'Unknown Artist'
    metadata['album'] = metadata['album'] if metadata['album'] else 'Unknown Album'
    metadata['title'] = metadata['title'] if metadata['title'] else os.path.splitext(file_name)[0]

    return metadata

def get_unmatched_files(db: Session) -> list[UnmatchedFile]:
    return db.query(UnmatchedFile).filter(UnmatchedFile.Ignored == False).all()

def _clean_import_directory(import_folder_path: str):
    logger.info(f"Starting cleanup of import directory: {import_folder_path}")
    if not os.path.isdir(import_folder_path):
        logger.warning(f"Import directory '{import_folder_path}' does not exist for cleanup.")
        return

    for dirpath, dirnames, filenames in os.walk(import_folder_path, topdown=False):
        try:
            if not os.listdir(dirpath) and dirpath != import_folder_path:
                os.rmdir(dirpath)
                logger.info(f"Removed empty directory: {dirpath}")
        except OSError as e:
            logger.error(f"Error removing directory {dirpath}: {e}")
    logger.info(f"Finished cleanup of import directory: {import_folder_path}")

def _import_file_logic(db: Session, file_path: str, file_name: str, file_size: int, unmatched_file_id: int = None) -> bool:
    library_folder_path = _get_config_value(db, "LibraryFolderPath")
    if not library_folder_path or not os.path.isdir(library_folder_path):
        logger.error(f"Cannot import file {file_name}: Library folder path not configured or does not exist: {library_folder_path}")
        if unmatched_file_id:
            unmatched_file = db.query(UnmatchedFile).filter(UnmatchedFile.Id == unmatched_file_id).first()
            if unmatched_file:
                unmatched_file.Ignored = True
                db.commit()
                logger.warning(f"Marked unmatched file {file_name} as ignored due to missing library path.")
        return False

    try:
        metadata = _extract_metadata(file_path)
        
        is_album_with_multiple_tracks = False
        import_folder = os.path.dirname(file_path)
        if metadata.get('album'):
            album_name_to_check = metadata['album'].strip().lower()
            if album_name_to_check != 'unknown album':
                for root, _, files in os.walk(import_folder):
                    for f in files:
                        if f.lower().endswith(('.mp3', '.flac', '.wav', '.aac', '.ogg', '.m4a')):
                            other_file_path = os.path.join(root, f)
                            if other_file_path == file_path:
                                continue
                            
                            other_metadata = _extract_metadata(other_file_path)
                            if other_metadata.get('album', '').strip().lower() == album_name_to_check:
                                is_album_with_multiple_tracks = True
                                break
                    if is_album_with_multiple_tracks:
                        break

        release_type = 'Single' if metadata['is_single'] and not is_album_with_multiple_tracks else 'Album'
        
        full_artist_name = metadata['artist']
        album_title = metadata['album']
        track_title = metadata['title']
        track_number = metadata['track_number']
        is_single = (release_type == 'Single')
        release_year = metadata['year']
        disknumber = metadata['disknumber']
        
        if full_artist_name == 'Unknown Artist' and album_title == 'Unknown Album' and track_title == os.path.splitext(file_name)[0]:
            logger.warning(f"Skipping import for {file_name} due to generic metadata after all fallbacks. It will remain in unmatched.")
            return False
            
        folder_artist_name = 'Unknown Artist'
        artist_db_entry = None
        
        if metadata.get('albumartist'):
            album_artist_raw = metadata['albumartist']
            primary_album_artist = album_artist_raw.split(';')[0].strip() if ';' in album_artist_raw else album_artist_raw
            primary_album_artist = primary_album_artist.split('/')[0].strip() if '/' in primary_album_artist else primary_album_artist
            
            artist_db_entry = db.query(Artist).filter(Artist.Name == primary_album_artist).first()
            if artist_db_entry:
                folder_artist_name = artist_db_entry.Name
                logger.debug(f"Found existing artist in DB using album artist: {folder_artist_name}")

        if not artist_db_entry and full_artist_name and full_artist_name != 'Unknown Artist':
            primary_contributing_artist = get_primary_artist_name(full_artist_name)
            artist_db_entry = db.query(Artist).filter(Artist.Name == primary_contributing_artist).first()
            if artist_db_entry:
                folder_artist_name = artist_db_entry.Name
                logger.debug(f"Found existing artist in DB using contributing artist fallback: {folder_artist_name}")

        if not artist_db_entry:
            artist_db_entry = _get_or_create_artist(db, full_artist_name)
            folder_artist_name = full_artist_name

        release = _get_or_create_release(db, artist_db_entry.Id, album_title, release_year, release_type)
        track = _get_or_create_track(db, release.Id, artist_db_entry.Id, track_title, track_number, metadata['duration'])

        new_imported_file = ImportedFile(
            FilePath=file_path,
            FileName=file_name,
            FileSize=file_size,
            ImportTimestamp=datetime.now().isoformat(),
            TrackId=track.Id,
            ReleaseId=release.Id,
            ArtistId=artist_db_entry.Id
        )
        db.add(new_imported_file)

        if unmatched_file_id:
            unmatched_file = db.query(UnmatchedFile).filter(UnmatchedFile.Id == unmatched_file_id).first()
            if unmatched_file:
                db.delete(unmatched_file)
                logger.debug(f"Deleted unmatched file entry with ID {unmatched_file_id}.")

        db.commit()
        logger.info(f"Successfully cataloged in DB: {file_name} (Artist: {artist_db_entry.Name}, Album: {release.Title}, Track: {track.Title})")

        file_ext = os.path.splitext(file_name)[1]
        
        sanitized_folder_artist_name = sanitize_path_component(folder_artist_name)
        sanitized_album_title = sanitize_path_component(release.Title)
        sanitized_track_title = sanitize_path_component(track.Title)
        sanitized_release_year = sanitize_path_component(str(release_year) if release_year else 'Unknown Year')
        sanitized_release_type = sanitize_path_component(release_type)

        folder_pattern = _get_config_value(db, "FolderStructurePattern")
        
        target_album_dir = None
        if not folder_pattern:
            if release_type == 'Single':
                target_album_dir = os.path.join(library_folder_path, sanitized_folder_artist_name, "Singles", sanitized_album_title)
            else:
                target_album_dir = os.path.join(library_folder_path, sanitized_folder_artist_name, sanitized_album_title)
            logger.debug(f"No FolderStructurePattern configured. Using default: {target_album_dir}")
        else:
            try:
                format_args = {
                    'artist': sanitized_folder_artist_name,
                    'year': sanitized_release_year,
                    'type': sanitized_release_type,
                    'album': sanitized_album_title
                }
                relative_album_dir = folder_pattern.format(**format_args)
                path_parts = relative_album_dir.split('/')
                sanitized_parts = [sanitize_path_component(part) for part in path_parts]
                target_album_dir = os.path.join(library_folder_path, *sanitized_parts)

                logger.debug(f"Using FolderStructurePattern: {folder_pattern} -> {target_album_dir}")
            except KeyError as e:
                logger.warning(f"Invalid placeholder '{e}' in FolderStructurePattern '{folder_pattern}'. Falling back to default pattern for this file.")
                if release_type == 'Single':
                    target_album_dir = os.path.join(library_folder_path, sanitized_folder_artist_name, "Singles", sanitized_album_title)
                else:
                    target_album_dir = os.path.join(library_folder_path, sanitized_folder_artist_name, sanitized_album_title)
        
        file_rename_pattern = _get_config_value(db, "FileRenamePattern")

        formatted_disknumber = ""
        formatted_tracknumber = ""

        if disknumber is not None and disknumber > 1:
            formatted_disknumber = f"{disknumber:01d} "

        if track_number is not None:
            formatted_tracknumber = f"{track_number:02d} "
        
        placeholder_values = {
            'artist': sanitized_folder_artist_name,
            'title': sanitized_track_title,
            'album': sanitized_album_title,
            'disknumber': formatted_disknumber,
            'tracknumber': formatted_tracknumber,
        }

        new_file_name_base = None
        if not file_rename_pattern:
            if is_single:
                new_file_name_base = f"{sanitized_folder_artist_name} - {sanitized_track_title}"
                if sanitized_album_title and sanitized_album_title.lower() not in sanitized_track_title.lower() and sanitized_album_title != 'Unknown Album':
                        new_file_name_base = f"{sanitized_folder_artist_name} - {sanitized_track_title} ({sanitized_album_title})"
            else:
                if track_number is not None:
                    new_file_name_base = f"{track_number:02d} - {sanitized_track_title}"
                else:
                    new_file_name_base = f"{sanitized_track_title}"
            logger.debug(f"No FileRenamePattern configured. Using default: {new_file_name_base}")
        else:
            try:
                temp_filename_base = file_rename_pattern
                for key, value in placeholder_values.items():
                    temp_filename_base = temp_filename_base.replace(f"{{{key}}}", value)
                
                new_file_name_base = re.sub(r'\s+', ' ', temp_filename_base).strip()
                new_file_name_base = re.sub(r'\s*-\s*', ' - ', new_file_name_base).strip(' -')

                logger.debug(f"Using FileRenamePattern: '{file_rename_pattern}' -> '{new_file_name_base}'")
            except Exception as e:
                logger.warning(f"Error applying FileRenamePattern '{file_rename_pattern}': {e}. Falling back to default filename pattern.", exc_info=True)
                if is_single:
                    new_file_name_base = f"{sanitized_folder_artist_name} - {sanitized_track_title}"
                    if sanitized_album_title and sanitized_album_title.lower() not in sanitized_track_title.lower() and sanitized_album_title != 'Unknown Album':
                            new_file_name_base = f"{sanitized_folder_artist_name} - {sanitized_track_title} ({sanitized_album_title})"
                else:
                    if track_number is not None:
                        new_file_name_base = f"{track_number:02d} - {sanitized_track_title}"
                    else:
                        new_file_name_base = f"{sanitized_track_title}"

        new_file_name = f"{sanitize_path_component(new_file_name_base)}{file_ext}"
        target_file_path = os.path.join(target_album_dir, new_file_name)

        os.makedirs(target_album_dir, exist_ok=True)
        
        if os.path.exists(target_file_path):
            logger.warning(f"Target file already exists, skipping move to avoid overwrite: {target_file_path}. DB entry exists.")
            return True
        
        shutil.move(file_path, target_file_path)
        logger.info(f"Successfully moved file from '{file_path}' to '{target_file_path}'")

        if metadata.get('cover_path'):
            source_cover_path = metadata['cover_path']
            if os.path.exists(source_cover_path):
                cover_filename = os.path.basename(source_cover_path)
                target_cover_path = os.path.join(target_album_dir, cover_filename)
                if not os.path.exists(target_cover_path):
                    try:
                        shutil.move(source_cover_path, target_cover_path)
                        logger.info(f"Successfully moved cover from '{source_cover_path}' to '{target_cover_path}'")
                    except Exception as e:
                        logger.error(f"Failed to move cover file {source_cover_path}: {e}")
                else:
                    logger.debug(f"Cover art already exists at {target_cover_path}, skipping move.")

        return True

    except IntegrityError as e:
        db.rollback()
        logger.warning(f"IntegrityError during import of {file_name}: {e}. File might already be imported or DB constraint violation.", exc_info=True)
        if unmatched_file_id:
            unmatched_file = db.query(UnmatchedFile).filter(UnmatchedFile.Id == unmatched_file_id).first()
            if unmatched_file:
                db.delete(unmatched_file)
                db.commit()
                logger.info(f"Removed duplicate unmatched file entry with ID {unmatched_file_id} as it was already imported.")
        return False
    except FileNotFoundError:
        db.rollback()
        logger.error(f"File not found during move operation: {file_path}. It might have been moved/deleted externally.", exc_info=True)
        return False
    except Exception as e:
        db.rollback()
        logger.error(f"Error importing or moving file {file_name}: {e}", exc_info=True)
        return False

def scan_import_folder(db: Session) -> tuple[list[UnmatchedFile], int]:
    import_folder_path = _get_config_value(db, "ImportFolderPath")
    if not import_folder_path or not os.path.isdir(import_folder_path):
        logger.error(f"Scan failed: Import folder path not configured or does not exist: {import_folder_path}")
        raise ValueError("Import folder path not configured or does not exist.")

    matched_count = 0
    
    existing_unmatched_paths = {f.FilePath for f in db.query(UnmatchedFile).filter(UnmatchedFile.Ignored == False).all()}
    existing_imported_paths = {f.FilePath for f in db.query(ImportedFile).all()}

    files_to_process = []
    for root, _, files in os.walk(import_folder_path):
        for file_name in files:
            if not file_name.lower().endswith(('.mp3', '.flac', '.wav', '.aac', '.ogg', '.m4a')):
                continue

            file_path = os.path.join(root, file_name)
            
            if file_path in existing_unmatched_paths:
                logger.debug(f"File already in unmatched list: {file_path}")
                continue
            
            if file_path in existing_imported_paths:
                logger.debug(f"File already imported: {file_path}")
                continue
            
            files_to_process.append((file_path, file_name))

    for file_path, file_name in files_to_process:
        try:
            file_size = os.path.getsize(file_path)
            
            success = _import_file_logic(db, file_path, file_name, file_size)

            if success:
                matched_count += 1
                existing_imported_paths.add(file_path)
            else:
                unmatched_entry = UnmatchedFile(
                    FilePath=file_path,
                    FileName=file_name,
                    FileSize=file_size,
                    DetectedArtist='Unknown',
                    DetectedAlbum='Unknown',
                    DetectedTitle='Unknown',
                    ScanTimestamp=datetime.now().isoformat(),
                    IsMatched=False,
                    Ignored=False
                )
                db.add(unmatched_entry)
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()
                    logger.warning(f"File '{file_name}' already exists in unmatched files. Skipping add.")
                logger.info(f"File '{file_name}' added to unmatched files.")
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error processing file {file_path} during scan: {e}", exc_info=True)
    
    _clean_import_directory(import_folder_path)

    return get_unmatched_files(db), matched_count

def match_unmatched_file(db: Session, file_id: int) -> bool:
    unmatched_file = db.query(UnmatchedFile).filter(UnmatchedFile.Id == file_id).first()
    if not unmatched_file:
        logger.warning(f"Unmatched file with ID {file_id} not found for matching.")
        return False

    return _import_file_logic(db, unmatched_file.FilePath, unmatched_file.FileName, unmatched_file.FileSize, unmatched_file.Id)

def ignore_unmatched_file(db: Session, file_id: int) -> bool:
    unmatched_file = db.query(UnmatchedFile).filter(UnmatchedFile.Id == file_id).first()
    if unmatched_file:
        unmatched_file.Ignored = True
        db.commit()
        logger.info(f"Ignored unmatched file: {unmatched_file.FileName}")
        return True
    logger.warning(f"Unmatched file with ID {file_id} not found for ignoring.")
    return False