"""
Google Drive manager module for uploading and organizing files.
"""
import os
import pickle
from typing import Optional, Tuple
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from config.logger import get_logger
from config.settings import *
from utils.helpers import retry_on_failure
from src.models import MediaFile, DriveFile

logger = get_logger(__name__)


class DriveManager:
    """Handles Google Drive operations."""

    def __init__(self, credentials_path: str = None, token_path: str = None):
        """
        Initialize Drive Manager.

        Args:
            credentials_path: Path to credentials.json file
            token_path: Path to token.pickle file
        """
        self.credentials_path = credentials_path or CREDENTIALS_FILE
        self.token_path = token_path or TOKEN_PICKLE
        self.service = self._authenticate()

    def _authenticate(self):
        """
        Authenticate and return a Google Drive service object.

        Returns:
            Google Drive service object or None if fails
        """
        creds = None
        if os.path.exists(self.token_path):
            with open(self.token_path, 'rb') as token:
                creds = pickle.load(token)

        # If there are no (valid) credentials available, let the user log in
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("Refreshing Google Drive credentials...")
                creds.refresh(Request())
            else:
                logger.info("Starting Google Drive authentication flow...")
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, SCOPES
                )
                creds = flow.run_local_server(port=0)

            # Save the credentials for the next run
            with open(self.token_path, 'wb') as token:
                pickle.dump(creds, token)
                logger.info("✅ Credentials saved to token.pickle")

        try:
            service = build('drive', 'v3', credentials=creds)
            logger.info("✅ Google Drive API service created successfully.")
            return service
        except Exception as e:
            logger.error(f"❌ Error creating Google Drive service: {e}", exc_info=True)
            return None

    def create_folder(self, folder_name: str, parent_folder_id: str) -> Optional[str]:
        """
        Create a folder in Google Drive and return its ID.

        Args:
            folder_name: Name of the folder to create
            parent_folder_id: ID of the parent folder

        Returns:
            Folder ID or None if fails
        """
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_folder_id]
        }

        try:
            folder = self.service.files().create(
                body=file_metadata,
                fields='id',
                supportsAllDrives=True
            ).execute()

            folder_id = folder.get('id')
            logger.info(f"📁 Folder '{folder_name}' created with ID: {folder_id}")
            return folder_id
        except Exception as e:
            logger.error(f"❌ Error creating folder '{folder_name}': {e}", exc_info=True)
            return None

    @retry_on_failure(max_retries=DRIVE_UPLOAD_MAX_RETRIES, delay=DRIVE_UPLOAD_RETRY_DELAY)
    def upload_file(self, media_file: MediaFile, folder_id: str) -> Optional[DriveFile]:
        """
        Upload a file to a specific Google Drive folder with automatic retries.

        Args:
            media_file: MediaFile object with file info
            folder_id: ID of the destination folder in Drive

        Returns:
            DriveFile object or None if fails

        Note:
            This function has automatic retries configured via decorator.
        """
        file_metadata = {
            'name': media_file.filename,
            'parents': [folder_id]
        }
        media = MediaFileUpload(media_file.path, resumable=True)

        file = self.service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id',
            supportsAllDrives=True
        ).execute()

        file_id = file.get('id')
        logger.info(f"⬆️ File '{media_file.filename}' uploaded with ID: {file_id}")

        return DriveFile(
            id=file_id,
            name=media_file.filename,
            parent_folder_id=folder_id
        )

    def file_exists(self, filename: str, folder_id: str) -> Tuple[bool, Optional[str]]:
        """
        Check if a file with the given name already exists in the specified folder.

        Args:
            filename: Name of the file to search for
            folder_id: ID of the folder to search in

        Returns:
            Tuple: (exists: bool, file_id: str or None)
        """
        try:
            query = f"name = '{filename}' and '{folder_id}' in parents and trashed = false"
            response = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name)',
                supportsAllDrives=True,
                includeItemsFromAllDrives=True
            ).execute()

            files = response.get('files', [])
            if files:
                file_id = files[0].get('id')
                logger.info(f"ℹ️ File '{filename}' already exists in Drive with ID: {file_id}")
                return True, file_id
            return False, None
        except Exception as e:
            logger.warning(f"⚠️ Error checking if '{filename}' exists: {e}")
            # If there's an error checking, assume file doesn't exist
            return False, None

    def upload_if_not_exists(
        self,
        media_file: MediaFile,
        folder_id: str
    ) -> Tuple[bool, Optional[DriveFile]]:
        """
        Upload a file only if it doesn't already exist in Drive.

        Args:
            media_file: MediaFile object with file info
            folder_id: ID of the destination folder

        Returns:
            Tuple: (uploaded: bool, drive_file: DriveFile or None)
        """
        exists, file_id = self.file_exists(media_file.filename, folder_id)

        if exists:
            logger.info(f"⏭️ File already exists in Drive, skipping: {media_file.filename}")
            return False, DriveFile(
                id=file_id,
                name=media_file.filename,
                parent_folder_id=folder_id
            )

        try:
            drive_file = self.upload_file(media_file, folder_id)
            return True, drive_file
        except Exception as e:
            logger.error(f"❌ Error uploading file: {e}", exc_info=True)
            return False, None
