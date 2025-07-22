# /app/routers/deemix.py 
import logging
import os
import tempfile
import shutil
from pathlib import Path
import re

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from ..db import SessionLocal
from ..models import Config

from deezer import Deezer

from deemix.settings import load as load_deemix_settings
from deemix import generateDownloadObject
from deemix.downloader import Downloader
from deemix.utils import formatListener

import anyio

router = APIRouter()

logger = logging.getLogger(__name__)

QUALITY_MAPPING = {
    "FLAC": 9,
    "MP3_320": 3,
    "MP3_128": 1,
    "DEFAULT": 3,
    "MP4_RA3": 8,
    "MP4_RA2": 7,
    "MP4_RA1": 6,
}


class LogListener:
    @classmethod
    def send(cls, key, value=None):
        logString = formatListener(key, value)
        if logString:
            logger.info(f"Deemix Listener: {logString}")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def _get_config_value(db: Session, key: str) -> str | None:
    config_entry = db.query(Config).filter(Config.Key == key).first()
    return config_entry.Value if config_entry else None

def sanitize_filename_component(name: str) -> str:
    if not isinstance(name, str):
        name = str(name)
    invalid_chars = r'[<>:"/\\|?*\x00-\x1f]'
    sanitized_name = re.sub(invalid_chars, '', name).strip()
    sanitized_name = sanitized_name.replace(':', ' - ')
    sanitized_name = sanitized_name.replace('/', '_')
    sanitized_name = sanitized_name.replace('\\', '_')
    return sanitized_name

async def _perform_deemix_download(
    deezerid: int,
    download_path: str,
    arl_key: str,
    download_quality: str
):
    temp_config_dir_path_str = None

    try:
        logger.info(f"[_perform_deemix_download] Attempting Deemix download for Deezer ID: {deezerid} to path: {download_path} with quality: {download_quality}")

        numeric_bitrate = QUALITY_MAPPING.get(download_quality, QUALITY_MAPPING["MP3_320"])
        logger.debug(f"[_perform_deemix_download] Mapped download quality '{download_quality}' to numeric bitrate: {numeric_bitrate}")

        temp_config_dir_path_str = tempfile.mkdtemp()
        temp_config_dir_path_obj = Path(temp_config_dir_path_str)
        logger.debug(f"[_perform_deemix_download] Using temporary deemix config directory: {temp_config_dir_path_obj}")

        deemix_settings = load_deemix_settings(temp_config_dir_path_obj)
        deemix_settings['arl'] = arl_key
        deemix_settings['downloadLocation'] = download_path
        
        deemix_settings['albumFolderTemplate'] = ''
        deemix_settings['quality'] = numeric_bitrate
        logger.debug(f"[_perform_deemix_download] Deemix settings configured: {deemix_settings}")

        if not os.path.exists(download_path):
            logger.error(f"[_perform_deemix_download] Download path does not exist: {download_path}")
            return f"Error: Download path '{download_path}' does not exist."
        else:
            logger.debug(f"[_perform_deemix_download] Download path '{download_path}' verified.")

        dz = Deezer() 
        if not dz.login_via_arl(arl_key):
            logger.error("[_perform_deemix_download] Failed to log into Deezer with provided ARL key. Please check your ARL key.")
            return "Error: Failed to log into Deezer with provided ARL key."
        logger.debug("[_perform_deemix_download] Successfully logged into Deezer.")

        listener = LogListener()
        
        deezer_link = None
        item_to_download_list = []

        try_album_link = f"https://www.deezer.com/album/{deezerid}"
        logger.debug(f"[_perform_deemix_download] Attempting to identify Deezer ID {deezerid} as an album using link: {try_album_link}")
        item_to_download_album = generateDownloadObject(
            dz, 
            try_album_link, 
            plugins=None,
            listener=listener,
            bitrate=numeric_bitrate
        )
        
        if item_to_download_album:
            deezer_link = try_album_link
            if not isinstance(item_to_download_album, list):
                item_to_download_list = [item_to_download_album]
            else:
                item_to_download_list = item_to_download_album
            logger.debug(f"[_perform_deemix_download] Deezer ID {deezerid} identified as an album. {len(item_to_download_list)} items generated.")
        else:
            try_track_link = f"https://www.deezer.com/track/{deezerid}"
            logger.debug(f"[_perform_deemix_download] Attempting to identify Deezer ID {deezerid} as a track using link: {try_track_link}")
            item_to_download_track = generateDownloadObject(
                dz, 
                try_track_link, 
                plugins=None,
                listener=listener,
                bitrate=numeric_bitrate
            )
            
            if item_to_download_track:
                deezer_link = try_track_link
                if not isinstance(item_to_download_track, list):
                    item_to_download_list = [item_to_download_track]
                else:
                    item_to_download_list = item_to_download_track
                logger.debug(f"[_perform_deemix_download] Deezer ID {deezerid} identified as a track. {len(item_to_download_list)} items generated.")
            else:
                logger.error(f"[_perform_deemix_download] Deezer ID {deezerid} not found as album or track via deemix processing.")
                return f"Error: Deezer ID {deezerid} could not be identified as a valid album or track."
        
        if not deezer_link or not item_to_download_list:
            logger.error(f"[_perform_deemix_download] Failed to construct a Deezer link or generate download items for ID {deezerid}. No object type identified or items generated.")
            return f"Error: Failed to identify Deezer object type or generate items for ID {deezerid}."

        successful_downloads = 0
        total_downloads = 0
        errors = []
        
        for obj in item_to_download_list:
            if obj.isCanceled:
                logger.info(f"[_perform_deemix_download] Skipping download for cancelled item: {getattr(obj, 'name', 'Unknown')}")
                continue

            total_downloads += 1
            track_name = getattr(obj, 'title', 'Unknown Track') if hasattr(obj, 'title') else 'Unknown Track' 

            try:
                artist_name_result = 'Unknown Artist'
                if hasattr(obj, 'artist') and obj.artist is not None:
                    artist_name_candidate = getattr(obj.artist, 'name', None)
                    if artist_name_candidate is not None and not callable(artist_name_candidate) and artist_name_candidate.strip() != '':
                        artist_name_result = artist_name_candidate.strip()
                
                if artist_name_result == 'Unknown Artist' and hasattr(obj, 'contributors') and obj.contributors:
                    for contributor in obj.contributors:
                        if hasattr(contributor, 'name') and contributor.name is not None and not callable(contributor.name) and contributor.name.strip() != '':
                            artist_name_result = contributor.name.strip()
                            break
                
                artist_name = sanitize_filename_component(artist_name_result)

                album_title_result = 'Unknown Album'
                if hasattr(obj, 'album') and obj.album is not None:
                    album_title_candidate = getattr(obj.album, 'title', None)
                    if album_title_candidate is not None and not callable(album_title_candidate):
                        album_title_result = album_title_candidate
                album_title = sanitize_filename_component(album_title_result)

                track_title_result = 'Unknown Title'
                if hasattr(obj, 'title') and obj.title is not None:
                    track_title_candidate = getattr(obj, 'title', None)
                    if track_title_candidate is not None and not callable(track_title_candidate):
                        track_title_result = track_title_candidate
                track_title = sanitize_filename_component(track_title_result)

                file_extension = ".mp3"
                if numeric_bitrate == 9:
                    file_extension = ".flac"
                elif numeric_bitrate in [8, 7, 6]:
                    file_extension = ".m4a"

                logger.info(f"[_perform_deemix_download] Starting download for item: {track_title} by {artist_name}")
                
                await anyio.to_thread.run_sync(Downloader(dz, obj, deemix_settings, listener).start)

                if obj.downloaded > 0 and len(obj.errors) == 0:
                    successful_downloads += obj.downloaded
                    logger.info(f"Deemix successfully downloaded one item.")
                    
                    found_actual_file = None
                    sanitized_track_title_lower = track_title.lower()
                    sanitized_artist_name_lower = artist_name.lower()
                    
                    max_verification_attempts = 15
                    attempt = 0
                    while not found_actual_file and attempt < max_verification_attempts:
                        attempt += 1
                        logger.debug(f"Verification attempt {attempt}/{max_verification_attempts} for '{track_title}' by '{artist_name}'...")
                        for existing_file in os.listdir(download_path):
                            full_path = os.path.join(download_path, existing_file)
                            if os.path.isfile(full_path) and existing_file.lower().endswith(file_extension):
                                file_name_lower = existing_file.lower()
                                if sanitized_track_title_lower in file_name_lower and sanitized_artist_name_lower in file_name_lower:
                                    if os.path.getsize(full_path) > 0:
                                        found_actual_file = full_path
                                        break
                                    else:
                                        logger.debug(f"Found file '{existing_file}' but it's zero size, waiting...")
                        if not found_actual_file:
                            await anyio.sleep(0.1) 
                    
                    if found_actual_file:
                        logger.info(f"Downloaded file found at: {found_actual_file}.")
                    else:
                        logger.warning(f"Could not locate the downloaded file in '{download_path}' after {max_verification_attempts} attempts. Expected parts: '{track_title}', '{artist_name}'.")
                        errors.append(f"Downloaded item '{track_name}' not found for verification after deemix completion.")

                elif len(obj.errors) > 0:
                    for error in obj.errors:
                        errors.append(f"Error for {track_name} (Track ID: {error.get('data', {}).get('id', 'N/A')}): {error.get('message', 'Unknown error')}")
                        logger.error(f"[_perform_deemix_download] Download error for {track_name}: {error.get('message', 'Unknown error')}")
                else:
                    errors.append(f"Download for {track_name} completed with unexpected state (no files downloaded, no explicit errors).")
                    logger.warning(f"[_perform_deemix_download] Download for {track_name} completed with unexpected state.")

            except Exception as e:
                errors.append(f"Exception during download for {track_name}: {e}")
                logger.exception(f"[_perform_deemix_download] Exception when running Downloader.start() for {track_name}")
                continue

        final_message = ""
        if successful_downloads > 0:
            final_message = f"Deemix download completed for Deezer ID: {deezerid}. {successful_downloads}/{total_downloads} items successful."
            if errors:
                final_message += f" Some errors occurred: {'; '.join(errors)}"
            logger.info(f"[_perform_deemix_download] {final_message}")
        else:
            final_message = f"Deemix download failed for Deezer ID: {deezerid}. All items failed. Details: {'; '.join(errors)}"
            logger.error(f"[_perform_deemix_download] {final_message}")

        return final_message

    except Exception as e:
        logger.critical(f"[_perform_deemix_download] CRITICAL UNCAUGHT ERROR IN BACKGROUND TASK for Deezer ID {deezerid}: {e}", exc_info=True)
        raise
    finally:
        if temp_config_dir_path_str and os.path.exists(temp_config_dir_path_str):
            try:
                shutil.rmtree(temp_config_dir_path_str)
                logger.debug(f"[_perform_deemix_download] Cleaned up temporary deemix config directory: {temp_config_dir_path_str}")
            except OSError as e:
                logger.warning(f"[_perform_deemix_download] Failed to remove temporary directory {temp_config_dir_path_str}: {e}")


@router.get("/deemix/download/{deezerid}")
async def deemix_download_route(
    deezerid: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    artist_id: int = Query(None, description="Optional Artist ID for context/logging")
):
    logger.info(f"Received request to download Deezer ID: {deezerid}")

    download_path = _get_config_value(db, "ImportFolderPath")
    arl_key = _get_config_value(db, "DeezerARLKey")
    download_quality = _get_config_value(db, "DeezerDownloadQuality")

    if not download_path:
        error_msg = "Import folder path not configured. Please set it in settings."
        logger.error(error_msg)
        return JSONResponse(status_code=400, content={"status": "error", "message": error_msg})

    if not arl_key:
        error_msg = "Deezer ARL Key not configured. Please set it in settings."
        logger.error(error_msg)
        return JSONResponse(status_code=400, content={"status": "error", "message": error_msg})

    if not download_quality:
        download_quality = "MP3_320"
        logger.warning(f"Deezer download quality not set in config, defaulting to {download_quality}.")
    elif download_quality not in QUALITY_MAPPING:
        logger.warning(f"Configured download quality '{download_quality}' is not a valid Deezer format. Defaulting to MP3_320.")
        download_quality = "MP3_320"


    if not os.path.isdir(download_path):
        error_msg = f"Configured import path '{download_path}' does not exist or is not a directory."
        logger.error(error_msg)
        return JSONResponse(status_code=400, content={"status": "error", "message": error_msg})

    background_tasks.add_task(_perform_deemix_download, deezerid, download_path, arl_key, download_quality)
    logger.info(f"Deemix download for Deezer ID: {deezerid} added to background tasks.")

    success_message = "Deemix download initiated in the background."
    if artist_id:
        logger.info(f"Download initiated for Deezer ID {deezerid} from artist ID {artist_id} context.")

    return JSONResponse(status_code=200, content={"status": "success", "message": success_message})