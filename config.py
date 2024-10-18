import os
from dotenv import load_dotenv, dotenv_values

load_dotenv()

API_TOKEN = os.getenv('API_TOKEN')
GOOGLE_DRIVE_CREDENTIALS_FILE = os.getenv('GOOGLE_DRIVE_CREDENTIALS_FILE')
EXCLUDED_FOLDERS = os.getenv('EXCLUDED_FOLDERS').split(',')
ALLOWED_USERS = list(map(int, os.getenv('ALLOWED_USERS').split(',')))
MAX_FILE_SIZE_MB = int(os.getenv('MAX_FILE_SIZE_MB'))
USE_ALLOWED_USERS = os.getenv('USE_ALLOWED_USERS', 'False').lower() == 'true'
STATISTICS_FOLDER = os.getenv('STATISTICS_FOLDER')
STATISTICS_FILE = os.getenv('STATISTICS_FILE')
