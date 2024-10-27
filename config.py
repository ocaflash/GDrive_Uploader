import os
from dotenv import load_dotenv, dotenv_values

load_dotenv()

API_TOKEN = os.getenv('API_TOKEN')
GOOGLE_DRIVE_CREDENTIALS_FILE = os.getenv('GOOGLE_DRIVE_CREDENTIALS_FILE')
EXCLUDED_FOLDERS = os.getenv('EXCLUDED_FOLDERS').split(',')
ALLOWED_USERS = list(map(int, os.getenv('ALLOWED_USERS').split(',')))
ADMIN_USERS = list(map(int, os.getenv('ADMIN_USERS', '').split(',')))
MAX_FILE_SIZE_MB = int(os.getenv('MAX_FILE_SIZE_MB'))
USE_ALLOWED_USERS = os.getenv('USE_ALLOWED_USERS', 'False').lower() == 'true'
STATISTICS_FOLDER = os.getenv('STATISTICS_FOLDER')
STATISTICS_FILE = os.getenv('STATISTICS_FILE')

# Обновленные настройки типов файлов
ALLOWED_FILE_TYPES = {
    'image': {
        'mime_types': ['image/jpeg', 'image/png', 'image/gif'],
        'extensions': ['.jpg', '.jpeg', '.png', '.gif'],
        'max_size_mb': 5,
        'description': 'Изображения'
    },
    'document': {
        'mime_types': ['application/pdf', 'application/msword',
                      'application/vnd.openxmlformats-officedocument.wordprocessingml.document'],
        'extensions': ['.pdf', '.doc', '.docx'],
        'max_size_mb': 10,
        'description': 'Документы'
    },
    'spreadsheet': {
        'mime_types': ['application/vnd.ms-excel',
                      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'],
        'extensions': ['.xls', '.xlsx'],
        'max_size_mb': 5,
        'description': 'Таблицы'
    },
    'video': {
        'mime_types': ['video/mp4', 'video/quicktime', 'video/x-msvideo', 'video/x-matroska'],
        'extensions': ['.mp4', '.mov', '.avi', '.mkv'],
        'max_size_mb': 100,
        'description': 'Видео'
    },
    'jwpub': {
        'mime_types': ['application/jwpub', 'application/octet-stream'],  # octet-stream для общего случая
        'extensions': ['.jwpub'],
        'max_size_mb': 5,
        'description': 'JWPUB публикации'
    }
}