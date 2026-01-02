"""
File system monitoring for automatic music library updates
"""

import os
import time
import hashlib
import logging
from pathlib import Path
from typing import List, Set
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from mutagen import File as MutagenFile
from sqlalchemy.orm import Session

from .database import get_db, Track
from .config import settings

logger = logging.getLogger(__name__)

class MusicFileHandler(FileSystemEventHandler):
    """Handle file system events for music files"""
    
    def __init__(self, db_session_factory):
        self.db_session_factory = db_session_factory
        self.audio_extensions = set(settings.supported_formats)
        self.processing_queue = set()
        
    def on_created(self, event):
        """Handle new file creation"""
        try:
            if not event.is_directory and self.is_audio_file(event.src_path):
                logger.info(f"New audio file detected: {event.src_path}")
                self.process_audio_file(event.src_path)
        except Exception as e:
            logger.error(f"Error handling file creation event for {event.src_path}: {e}")
    
    def on_modified(self, event):
        """Handle file modification"""
        try:
            if not event.is_directory and self.is_audio_file(event.src_path):
                # Avoid processing the same file multiple times rapidly
                if event.src_path not in self.processing_queue:
                    logger.info(f"Audio file modified: {event.src_path}")
                    self.process_audio_file(event.src_path)
        except Exception as e:
            logger.error(f"Error handling file modification event for {event.src_path}: {e}")
    
    def on_deleted(self, event):
        """Handle file deletion"""
        try:
            if not event.is_directory and self.is_audio_file(event.src_path):
                logger.info(f"Audio file deleted: {event.src_path}")
                self.remove_track_from_db(event.src_path)
        except Exception as e:
            logger.error(f"Error handling file deletion event for {event.src_path}: {e}")
    
    def is_audio_file(self, file_path: str) -> bool:
        """Check if file is a supported audio format"""
        return Path(file_path).suffix.lower() in self.audio_extensions
    
    def process_audio_file(self, file_path: str):
        """Process a single audio file with comprehensive error handling"""
        try:
            self.processing_queue.add(file_path)
            
            # Validate file path
            if not file_path or not isinstance(file_path, str):
                logger.error(f"Invalid file path: {file_path}")
                return
            
            # Wait a moment for file to be fully written
            time.sleep(0.5)
            
            if not os.path.exists(file_path):
                logger.warning(f"File disappeared during processing: {file_path}")
                return
            
            # Check file size (skip empty files)
            try:
                file_size = os.path.getsize(file_path)
                if file_size == 0:
                    logger.warning(f"Skipping empty file: {file_path}")
                    return
                elif file_size < 1024:  # Less than 1KB
                    logger.warning(f"File too small to be valid audio: {file_path}")
                    return
            except OSError as e:
                logger.error(f"Error checking file size for {file_path}: {e}")
                return
            
            # Extract metadata with timeout protection
            try:
                audio_file = MutagenFile(file_path)
                if audio_file is None:
                    logger.warning(f"Could not read audio metadata (possibly corrupted): {file_path}")
                    return
            except Exception as e:
                logger.error(f"Error reading audio metadata from {file_path}: {e}")
                return
            
            # Calculate file hash for duplicate detection
            file_hash = self.calculate_file_hash(file_path)
            if not file_hash:
                logger.warning(f"Could not calculate hash for {file_path}, skipping duplicate detection")
                file_hash = ""
            
            # Store in database with retry logic
            track_id = None
            for attempt in range(3):  # Try up to 3 times
                try:
                    track_id = self.store_track_metadata(file_path, audio_file, file_hash)
                    break
                except Exception as e:
                    logger.warning(f"Database store attempt {attempt + 1} failed for {file_path}: {e}")
                    if attempt == 2:  # Last attempt
                        logger.error(f"Failed to store track after 3 attempts: {file_path}")
                    else:
                        time.sleep(1)  # Wait before retry
            
            if track_id:
                logger.info(f"Successfully processed track {track_id}: {file_path}")
                # Queue for AI analysis (would be handled by background processor)
                # self.queue_for_analysis(track_id)
            else:
                logger.error(f"Failed to process track: {file_path}")
            
        except Exception as e:
            logger.error(f"Unexpected error processing {file_path}: {e}", exc_info=True)
        finally:
            self.processing_queue.discard(file_path)
    
    def calculate_file_hash(self, file_path: str) -> str:
        """Calculate MD5 hash of file for duplicate detection with enhanced error handling"""
        if not file_path or not os.path.exists(file_path):
            return ""
        
        hasher = hashlib.md5()
        try:
            with open(file_path, 'rb') as f:
                while True:
                    chunk = f.read(8192)  # Read in 8KB chunks
                    if not chunk:
                        break
                    hasher.update(chunk)
            return hasher.hexdigest()
        except PermissionError as e:
            logger.error(f"Permission denied calculating hash for {file_path}: {e}")
            return ""
        except OSError as e:
            logger.error(f"OS error calculating hash for {file_path}: {e}")
            return ""
        except MemoryError as e:
            logger.error(f"Memory error calculating hash for {file_path}: {e}")
            return ""
        except Exception as e:
            logger.error(f"Unexpected error calculating hash for {file_path}: {e}")
            return ""
    
    def store_track_metadata(self, file_path: str, audio_file, file_hash: str) -> int:
        """Store track metadata in database"""
        session = self.db_session_factory()
        try:
            # Check if track already exists
            existing_track = session.query(Track).filter_by(file_path=file_path).first()
            
            # Extract metadata with fallbacks
            metadata = self.extract_metadata(audio_file)
            
            if existing_track:
                # Update existing track
                for key, value in metadata.items():
                    setattr(existing_track, key, value)
                existing_track.file_hash = file_hash
                existing_track.file_size = os.path.getsize(file_path)
                track_id = existing_track.id
            else:
                # Create new track
                track = Track(
                    file_path=file_path,
                    file_hash=file_hash,
                    file_size=os.path.getsize(file_path),
                    **metadata
                )
                session.add(track)
                session.flush()  # Get the ID
                track_id = track.id
            
            session.commit()
            return track_id
            
        except Exception as e:
            session.rollback()
            logger.error(f"Database error storing track {file_path}: {e}")
            return None
        finally:
            session.close()
    
    def extract_metadata(self, audio_file) -> dict:
        """Extract metadata from audio file"""
        # Different audio formats store metadata differently
        # This handles the most common formats
        
        def safe_get(key_variants, default="Unknown"):
            for key in key_variants:
                if key in audio_file:
                    value = audio_file[key]
                    if isinstance(value, list) and value:
                        return str(value[0])
                    elif value:
                        return str(value)
            return default
        
        # Extract basic metadata
        title = safe_get(['TIT2', 'TITLE', '\xa9nam'])
        artist = safe_get(['TPE1', 'ARTIST', '\xa9ART'])
        album = safe_get(['TALB', 'ALBUM', '\xa9alb'])
        genre = safe_get(['TCON', 'GENRE', '\xa9gen'])
        
        # Extract year
        year = safe_get(['TDRC', 'DATE', '\xa9day'])
        try:
            if year and year != "Unknown":
                year = int(str(year)[:4])  # Extract just the year part
        except (ValueError, TypeError):
            year = None
        
        # Extract audio properties
        duration = 0
        bitrate = 0
        sample_rate = 0
        
        if hasattr(audio_file, 'info') and audio_file.info:
            duration = int(getattr(audio_file.info, 'length', 0))
            bitrate = int(getattr(audio_file.info, 'bitrate', 0))
            sample_rate = int(getattr(audio_file.info, 'sample_rate', 0))
        
        return {
            'title': title,
            'artist': artist,
            'album': album,
            'year': year,
            'genre': genre,
            'duration': duration,
            'bitrate': bitrate,
            'sample_rate': sample_rate
        }
    
    def remove_track_from_db(self, file_path: str):
        """Remove track from database when file is deleted"""
        session = self.db_session_factory()
        try:
            track = session.query(Track).filter_by(file_path=file_path).first()
            if track:
                session.delete(track)
                session.commit()
                logger.info(f"Removed track from database: {file_path}")
        except Exception as e:
            session.rollback()
            logger.error(f"Error removing track from database: {e}")
        finally:
            session.close()

class FileMonitor:
    """Main file monitoring system"""
    
    def __init__(self, directories: List[str], database_url: str):
        self.directories = directories
        self.database_url = database_url
        self.observer = Observer()
        self.handler = MusicFileHandler(get_db)
        self.is_running = False
        
    def start(self):
        """Start monitoring specified directories"""
        if self.is_running:
            logger.warning("File monitor is already running")
            return
        
        # Add watches for each directory
        for directory in self.directories:
            if os.path.exists(directory):
                self.observer.schedule(
                    self.handler, 
                    directory, 
                    recursive=True
                )
                logger.info(f"Started monitoring: {directory}")
            else:
                logger.warning(f"Directory does not exist: {directory}")
        
        self.observer.start()
        self.is_running = True
        logger.info("File monitor started successfully")
    
    def stop(self):
        """Stop file monitoring"""
        if not self.is_running:
            return
        
        self.observer.stop()
        self.observer.join()
        self.is_running = False
        logger.info("File monitor stopped")
    
    def initial_scan(self):
        """Perform initial scan of all directories"""
        logger.info("Starting initial library scan...")
        
        total_files = 0
        processed_files = 0
        
        for directory in self.directories:
            if not os.path.exists(directory):
                logger.warning(f"Skipping non-existent directory: {directory}")
                continue
            
            logger.info(f"Scanning directory: {directory}")
            
            for root, dirs, files in os.walk(directory):
                for file in files:
                    file_path = os.path.join(root, file)
                    total_files += 1
                    
                    if self.handler.is_audio_file(file_path):
                        try:
                            self.handler.process_audio_file(file_path)
                            processed_files += 1
                            
                            if processed_files % 100 == 0:
                                logger.info(f"Processed {processed_files} audio files...")
                                
                        except Exception as e:
                            logger.error(f"Error processing {file_path}: {e}")
        
        logger.info(f"Initial scan complete: {processed_files} audio files processed out of {total_files} total files")