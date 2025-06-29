import os
import datetime
import mimetypes
import logging
from telethon import TelegramClient, events
from telethon.tl.custom import Button
from gdrive_service import GoogleDriveService
from config import API_ID, API_HASH, SESSION_NAME, GOOGLE_DRIVE_CREDENTIALS_FILE
from config import ALLOWED_USERS, EXCLUDED_FOLDERS, USE_ALLOWED_USERS, ALLOWED_FILE_TYPES

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Регистрация MIME-типа для jwpub
mimetypes.add_type('application/jwpub', '.jwpub')

# Инициализация Telethon userbot
client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
gdrive = GoogleDriveService(GOOGLE_DRIVE_CREDENTIALS_FILE)

# user_data: хранит временные данные для каждого пользователя
user_data = {}

def get_files_word(count):
    if count % 100 in [11, 12, 13, 14]:
        return "файлов"
    remainder = count % 10
    if remainder == 1:
        return "файл"
    elif remainder in [2, 3, 4]:
        return "файла"
    else:
        return "файлов"

def get_file_type_category(mime_type, file_extension):
    if file_extension.lower() == '.jwpub':
        return 'jwpub'
    for category, settings in ALLOWED_FILE_TYPES.items():
        if mime_type in settings['mime_types'] or file_extension.lower() in settings['extensions']:
            return category
    return None

def format_size(size_mb):
    if size_mb >= 1024:
        return f"{size_mb / 1024:.1f} ГБ"
    return f"{size_mb:.1f} МБ"

def get_allowed_files_description():
    descriptions = []
    for category, settings in ALLOWED_FILE_TYPES.items():
        max_size = format_size(settings['max_size_mb'])
        extensions = ', '.join(settings['extensions'])
        descriptions.append(f"• {settings['description']} ({extensions}) - до {max_size}")
    return '\n'.join(descriptions)

def get_comments_word(count):
    if count % 100 in [11, 12, 13, 14]:
        return "комментариев"
    remainder = count % 10
    if remainder == 1:
        return "комментарий"
    elif remainder in [2, 3, 4]:
        return "комментария"
    else:
        return "комментариев"

welcome_message = (
    "Привет!\nЯ бот для работы с Google Drive.\n"
    "Умею загружать следующие типы файлов:\n\n"
    f"{get_allowed_files_description()}\n\n"
    "Пришлите мне файлы, и я помогу загрузить их в нужную папку."
)

async def send_welcome(event):
    await event.respond(welcome_message)

async def send_folder_buttons(event):
    upload_folder_id = gdrive.find_folder_id_by_name('Upload')
    if not upload_folder_id:
        await event.respond('Ошибка: папка "Upload" не найдена в Google Drive.')
        return
    folders = gdrive.get_folders(upload_folder_id)
    folders = {name: folder_id for name, folder_id in folders.items() if name not in EXCLUDED_FOLDERS}
    buttons = []
    row = []
    for name, folder_id in folders.items():
        row.append(Button.inline(name, data=folder_id.encode()))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    await event.respond('Выберите папку для загрузки:', buttons=buttons)

@client.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    await send_welcome(event)

@client.on(events.NewMessage(incoming=True))
async def file_handler(event):
    user_id = event.sender_id
    if user_id not in user_data:
        user_data[user_id] = {'files': [], 'unsupported_files': [], 'comments': []}
    data = user_data[user_id]
    if USE_ALLOWED_USERS and user_id not in ALLOWED_USERS:
        await event.respond('У вас нет прав для загрузки файлов.')
        return
    # Обработка комментария (caption)
    if event.text and not event.file:
        comment_count = len(data['comments']) + 1
        comment = {
            'filename': f'comment_{comment_count}.txt',
            'content': event.text,
            'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        data['comments'].append(comment)
        await event.respond('Комментарий сохранён. Теперь отправьте файл или выберите папку.')
        return
    if event.file:
        file_name = event.file.name or 'file'
        file_extension = os.path.splitext(file_name)[1]
        mime_type = event.file.mime_type or 'application/octet-stream'
        file_type_category = get_file_type_category(mime_type, file_extension)
        file_size_mb = event.file.size / (1024 * 1024)
        if not file_type_category:
            data['unsupported_files'].append({'name': file_name, 'reason': 'Неподдерживаемый формат'})
            await event.respond(f'Файл {file_name} не поддерживается.')
            return
        max_size = ALLOWED_FILE_TYPES[file_type_category]['max_size_mb']
        if file_size_mb > max_size:
            data['unsupported_files'].append({'name': file_name, 'reason': f'превышен размер {format_size(max_size)}'})
            await event.respond(f'Файл {file_name} превышает допустимый размер.')
            return
        # Сохраняем файл во временную папку
        os.makedirs('downloads', exist_ok=True)
        file_path = os.path.join('downloads', file_name)
        await event.download_media(file=file_path)
        data['files'].append({'file_path': file_path, 'file_name': file_name, 'type': file_type_category, 'size_mb': file_size_mb})
        await event.respond(f'Файл {file_name} сохранён. Теперь выберите папку для загрузки.')
        await send_folder_buttons(event)

@client.on(events.CallbackQuery())
async def folder_selection_handler(event):
    user_id = event.sender_id
    data = user_data.get(user_id, {'files': [], 'unsupported_files': [], 'comments': []})
    folder_id = event.data.decode()
    if not data['files'] and not data['comments']:
        await event.answer('Нет файлов или комментариев для загрузки.', alert=True)
        return
    date_folder_name = (datetime.datetime.now() + datetime.timedelta(hours=3)).strftime('%d-%m-%Y')
    date_folder_id = gdrive.find_folder_id_by_name(date_folder_name, folder_id)
    if date_folder_id is None:
        date_folder_id = gdrive.create_folder(folder_id, date_folder_name)
    uploaded_files = []
    total_files = len(data['files']) + len(data['comments'])
    current_file = 0
    for file_info in data['files']:
        current_file += 1
        await event.edit(f'Загружаю файл {file_info["file_name"]} ({current_file}/{total_files})...')
        try:
            gdrive.upload_file(file_info['file_path'], date_folder_id, file_info['file_name'])
            uploaded_files.append(file_info['file_name'])
            os.remove(file_info['file_path'])
        except Exception as e:
            await event.edit(f'Ошибка при загрузке файла {file_info["file_name"]}: {e}')
            return
    for comment in data['comments']:
        current_file += 1
        comment_path = os.path.join('downloads', comment['filename'])
        with open(comment_path, 'w', encoding='utf-8') as f:
            f.write(comment['content'])
        try:
            gdrive.upload_file(comment_path, date_folder_id, comment['filename'])
            uploaded_files.append(comment['filename'])
            os.remove(comment_path)
        except Exception as e:
            await event.edit(f'Ошибка при загрузке комментария {comment["filename"]}: {e}')
    success_message = f'Успешно загружено {len(uploaded_files)} {get_files_word(len(uploaded_files))}!\nПапка: {date_folder_name}\n'
    if uploaded_files:
        success_message += '\nЗагруженные файлы:\n' + '\n'.join(f'• {f}' for f in uploaded_files)
    if data['unsupported_files']:
        success_message += '\n\nНеподдерживаемые файлы:\n' + '\n'.join(f'• {f["name"]} ({f["reason"]})' for f in data['unsupported_files'])
    await event.edit(success_message)
    # Очистка данных пользователя
    user_data[user_id] = {'files': [], 'unsupported_files': [], 'comments': []}

if __name__ == '__main__':
    print('Userbot запущен...')
    client.start()
    client.run_until_disconnected()
