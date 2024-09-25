from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
import os

class GoogleDriveService:
    def __init__(self, credentials_file):
        self.creds = service_account.Credentials.from_service_account_file(credentials_file)
        self.service = build('drive', 'v3', credentials=self.creds)

    def get_folders(self, parent_id='root'):  # Default to root if no ID is provided
        try:
            print(f"Searching for folders in parent ID: {parent_id}")
            results = self.service.files().list(
                q=f"'{parent_id}' in parents and mimeType='application/vnd.google-apps.folder'",
                fields="files(id, name)"
            ).execute()
            folders = results.get('files', [])
            print(f"Найденные папки: {folders}")
            return {folder['name']: folder['id'] for folder in folders}
        except HttpError as error:
            print(f"Произошла ошибка: {error}")
            return {}

    def create_folder(self, parent_id, folder_name):
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_id]
        }
        folder = self.service.files().create(body=file_metadata, fields='id').execute()
        return folder.get('id')

    def upload_file(self, file_path, parent_id):
        file_metadata = {
            'name': os.path.basename(file_path),  # Используем оригинальное имя файла
            'parents': [parent_id]
        }
        media = MediaFileUpload(file_path, mimetype='image/jpeg')
        file = self.service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        return file.get('id')

    def find_folder_id_by_name(self, folder_name, parent_id=None):
        try:
            # Формируем запрос. Если parent_id не передан, ищем по всему Google Drive.
            query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder'"
            if parent_id:
                query += f" and '{parent_id}' in parents"

            results = self.service.files().list(
                q=query,
                fields="files(id, name)"
            ).execute()
            folders = results.get('files', [])

            if folders:
                return folders[0]['id']  # Возвращаем ID первой найденной папки
            else:
                return None  # Папка не найдена
        except HttpError as error:
            print(f"Произошла ошибка: {error}")
            return None
