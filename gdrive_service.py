from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GoogleDriveService:
    def __init__(self, credentials_file):
        self.creds = service_account.Credentials.from_service_account_file(credentials_file)
        self.drive_service = build('drive', 'v3', credentials=self.creds)
        self.sheets_service = build('sheets', 'v4', credentials=self.creds)

    def get_folders(self, parent_id='root'):
        try:
            results = self.drive_service.files().list(
                q=f"'{parent_id}' in parents and mimeType='application/vnd.google-apps.folder'",
                fields="files(id, name)"
            ).execute()
            folders = results.get('files', [])
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
        folder = self.drive_service.files().create(body=file_metadata, fields='id').execute()
        return folder.get('id')

    def upload_file(self, file_path, parent_id, file_name=None):
        file_name = file_name or os.path.basename(file_path)
        file_metadata = {
            'name': file_name,
            'parents': [parent_id]
        }

        # Проверяем, существует ли файл с таким именем
        existing_file = self.drive_service.files().list(
            q=f"name='{file_name}' and '{parent_id}' in parents",
            fields="files(id)"
        ).execute().get('files', [])

        media = MediaFileUpload(file_path, resumable=True)

        if existing_file:
            # Если файл существует, обновляем его
            file = self.drive_service.files().update(
                fileId=existing_file[0]['id'],
                media_body=media
            ).execute()
        else:
            # Если файла нет, создаем новый
            file = self.drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()

        return file.get('id')

    def find_folder_id_by_name(self, folder_name, parent_id=None):
        try:
            query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder'"
            if parent_id:
                query += f" and '{parent_id}' in parents"

            results = self.drive_service.files().list(
                q=query,
                fields="files(id, name)"
            ).execute()
            folders = results.get('files', [])

            if folders:
                return folders[0]['id']
            else:
                return None
        except HttpError as error:
            print(f"Произошла ошибка: {error}")
            return None

    def create_or_get_statistics_sheet(self, folder_id, file_name):
        # Проверяем, существует ли файл
        file_id = self.find_file_id_by_name(file_name, folder_id)

        if not file_id:
            # Если файл не существует, создаем новый
            file_metadata = {
                'name': file_name,
                'parents': [folder_id],
                'mimeType': 'application/vnd.google-apps.spreadsheet'
            }
            file = self.drive_service.files().create(body=file_metadata, fields='id').execute()
            file_id = file.get('id')

            # Инициализируем заголовки
            self.sheets_service.spreadsheets().values().update(
                spreadsheetId=file_id,
                range='A1:E1',
                valueInputOption='RAW',
                body={
                    'values': [['Дата', 'ID пользователя', 'Папка загрузки', 'Имена файлов', 'Количество файлов']]
                }
            ).execute()

        return file_id

    def add_statistics_entry(self, sheet_id, date, user_id, folder, file_names):
        values = [
            [
                date.strftime('%Y-%m-%d %H:%M:%S'),
                str(user_id),
                folder,
                ', '.join(file_names),
                str(len(file_names))
            ]
        ]

        body = {
            'values': values
        }

        logger.info(f"Полученные данные: {body}")
        self.sheets_service.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range='A1',
            valueInputOption='RAW',
            insertDataOption='INSERT_ROWS',
            body=body
        ).execute()

    def find_file_id_by_name(self, file_name, parent_id=None):
        query = f"name='{file_name}'"
        if parent_id:
            query += f" and '{parent_id}' in parents"

        results = self.drive_service.files().list(
            q=query,
            fields="files(id)"
        ).execute()
        files = results.get('files', [])

        if files:
            return files[0]['id']
        else:
            return None
