import datetime
import os
import logging
import mimetypes
from datetime import timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackContext, CallbackQueryHandler, filters
from telegram.error import BadRequest
from gdrive_service import GoogleDriveService
from config import API_TOKEN, GOOGLE_DRIVE_CREDENTIALS_FILE, ALLOWED_USERS, MAX_FILE_SIZE_MB, EXCLUDED_FOLDERS, \
    USE_ALLOWED_USERS, STATISTICS_FOLDER, STATISTICS_FILE, ALLOWED_FILE_TYPES, ADMIN_USERS

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

mimetypes.add_type('application/jwpub', '.jwpub')

drive_service = GoogleDriveService(GOOGLE_DRIVE_CREDENTIALS_FILE)


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


async def start(update: Update, context) -> None:
    await update.message.reply_text(welcome_message)


async def send_folder_buttons(update: Update, context) -> None:
    upload_folder_id = drive_service.find_folder_id_by_name('Upload')
    if not upload_folder_id:
        await update.message.reply_text('Ошибка: папка "Upload" не найдена в Google Drive.')
        return

    folders = drive_service.get_folders(upload_folder_id)
    folders = {name: folder_id for name, folder_id in folders.items() if name not in EXCLUDED_FOLDERS}

    keyboard = []
    row = []

    for name, folder_id in folders.items():
        row.append(InlineKeyboardButton(name, callback_data=folder_id))
        if len(row) == 2:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Выберите папку для загрузки:', reply_markup=reply_markup)


async def handle_file(update: Update, context) -> None:
    try:
        logger.info(f"Получен файл от пользователя {update.message.from_user.id}.")

        if USE_ALLOWED_USERS and update.message.from_user.id not in ALLOWED_USERS:
            logger.warning(f"Пользователь {update.message.from_user.id} не имеет прав для загрузки файлов.")
            await update.message.reply_text('У вас нет прав для загрузки файлов.')
            return

        file = None
        file_type_category = None
        file_extension = ''
        original_file_name = None

        caption = update.message.caption
        if caption and 'comments' not in context.user_data:
            context.user_data['comments'] = []
        if caption:
            comment_count = len(context.user_data['comments']) + 1
            comment = {
                'filename': f'comment_{comment_count}.txt',
                'content': caption,
                'telegram_timestamp': update.message.date.strftime('%Y-%m-%d %H:%M:%S')
            }
            context.user_data['comments'].append(comment)

        if 'files' not in context.user_data:
            context.user_data['files'] = []
        if 'unsupported_files' not in context.user_data:
            context.user_data['unsupported_files'] = []

        if update.message.photo:
            file = update.message.photo[-1]
            file_type_category = 'image'
            file_extension = '.jpg'
            file_name = f"image_{len(context.user_data.get('files', [])) + 1}{file_extension}"
        elif update.message.video:
            file = update.message.video
            file_type_category = 'video'
            original_file_name = file.file_name
            file_extension = os.path.splitext(original_file_name)[1] if original_file_name else '.mp4'
            file_name = original_file_name or f"video_{len(context.user_data.get('files', [])) + 1}{file_extension}"
            file_size_mb = file.file_size / (1024 * 1024)
            logger.info(f"Видео: {file_name}, размер: {file_size_mb:.2f} МБ")
            if file_size_mb > 50:  # Лимит Telegram API
                await update.message.reply_text(
                    "Видео превышает 50 МБ и не может быть загружено через Telegram. "
                    "Пожалуйста, отправьте прямую ссылку на видео (например, из Google Drive или другого сервиса)."
                )
                return
        elif update.message.audio:
            file = update.message.audio
            file_type_category = 'audio'
            original_file_name = file.file_name
            file_extension = os.path.splitext(original_file_name)[1] if original_file_name else '.mp3'
            file_name = original_file_name or f"audio_{len(context.user_data.get('files', [])) + 1}{file_extension}"
        elif update.message.document:
            file = update.message.document
            original_file_name = file.file_name
            file_extension = os.path.splitext(original_file_name)[1].lower() if original_file_name else ''
            mime_type = file.mime_type or 'application/octet-stream'
            logger.info(f"Документ: {original_file_name}, размер: {file.file_size / (1024 * 1024):.2f} МБ, MIME: {mime_type}")
            if file_extension in ['.mp4', '.mov', '.avi', '.mkv'] or mime_type in ALLOWED_FILE_TYPES['video']['mime_types']:
                file_type_category = 'video'
                file_name = original_file_name or f"video_{len(context.user_data.get('files', [])) + 1}{file_extension}"
                file_size_mb = file.file_size / (1024 * 1024)
                if file_size_mb > 50:  # Лимит Telegram API
                    await update.message.reply_text(
                        "Видео превышает 50 МБ и не может быть загружено через Telegram. "
                        "Пожалуйста, отправьте прямую ссылку на видео (например, из Google Drive или другого сервиса)."
                    )
                    return
            else:
                file_type_category = get_file_type_category(mime_type, file_extension)
                file_name = original_file_name

        if not file:
            await update.message.reply_text('Ошибка: файл не найден.')
            return

        if not file_type_category:
            current_file = {
                'name': original_file_name or 'Неизвестный файл',
                'reason': 'Неподдерживаемый формат'
            }
            if current_file not in context.user_data['unsupported_files']:
                context.user_data['unsupported_files'].append(current_file)
        else:
            max_size = ALLOWED_FILE_TYPES[file_type_category]['max_size_mb']
            file_size_mb = file.file_size / (1024 * 1024)

            if file_size_mb > max_size:
                current_file = {
                    'name': file_name,
                    'reason': f'превышен размер {format_size(max_size)}'
                }
                if current_file not in context.user_data['unsupported_files']:
                    context.user_data['unsupported_files'].append(current_file)
            else:
                current_file = {
                    'file_id': file.file_id,
                    'file_name': file_name,
                    'type': file_type_category,
                    'size_mb': file_size_mb
                }
                if not any(f['file_name'] == file_name for f in context.user_data['files']):
                    context.user_data['files'].append(current_file)

        if not context.user_data['files'] and context.user_data['unsupported_files']:
            unsupported_message = "Следующие файлы не поддерживаются:\n"
            for file in context.user_data['unsupported_files']:
                unsupported_message += f"• {file['name']} - {file['reason']}\n"
            context.user_data['files'] = []
            context.user_data['unsupported_files'] = []
            context.user_data['comments'] = []
            await update.message.reply_text(unsupported_message)
            return

        if context.user_data['files']:
            current_time = datetime.datetime.now()
            if 'last_message_time' not in context.user_data or \
                    (current_time - context.user_data['last_message_time']).total_seconds() > 5:
                context.user_data['last_message_time'] = current_time
                await send_folder_buttons(update, context)

    except Exception as e:
        logger.error(f"Ошибка в handle_file: {e}")
        await update.message.reply_text('Произошла ошибка при обработке файла. Пожалуйста, попробуйте еще раз.')

async def handle_folder_selection(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()

    await query.edit_message_reply_markup(reply_markup=None)
    await query.edit_message_text(text='Загружаю файлы...')

    files = context.user_data.get('files', [])
    unsupported_files = context.user_data.get('unsupported_files', [])
    comments = context.user_data.get('comments', [])

    def create_progress_bar(current, total, width=20):
        progress = int(width * current / total)
        return f"[{'■' * progress}{'□' * (width - progress)}]"

    if not files and not unsupported_files:
        await query.edit_message_text(text='Ошибка: Файлы не найдены. Пожалуйста, загрузите файлы перед выбором папки.')
        return

    folder_id = query.data

    try:
        upload_folder_id = drive_service.find_folder_id_by_name('Upload')
        folders = drive_service.get_folders(upload_folder_id)
        folder_name = next(name for name, id in folders.items() if id == folder_id)
    except StopIteration:
        await query.edit_message_text(text='Ошибка: Выбранная папка не найдена.')
        return
    except Exception as e:
        logger.error(f"Ошибка при получении имени папки: {e}")
        await query.edit_message_text(text='Произошла ошибка при выборе папки.')
        return

    date_folder_name = datetime.datetime.now() + timedelta(hours=3)
    date_folder_name_str = date_folder_name.strftime("%d-%m-%Y")
    date_folder_id = drive_service.find_folder_id_by_name(date_folder_name_str, folder_id)
    if date_folder_id is None:
        date_folder_id = drive_service.create_folder(folder_id, date_folder_name_str)

    uploaded_files = []
    total_files = len(files) + len(comments)
    current_file = 0

    for file_info in files:
        current_file += 1
        progress_bar = create_progress_bar(current_file - 0.5, total_files)
        percentage = ((current_file - 0.5) / total_files) * 100

        progress_message = (
            f'Загружаю файлы...\n'
            f'Загрузка файла {file_info["file_name"]}\n'
            f'{progress_bar} {percentage:.1f}%\n'
            f'Прогресс: {current_file}/{total_files}'
        )
        await query.edit_message_text(text=progress_message)

        if 'file_id' in file_info:
            try:
                photo_file = await context.bot.get_file(file_info['file_id'])
                photo_file_path = os.path.join(os.getcwd(), file_info['file_name'])
                await photo_file.download_to_drive(photo_file_path)
            except telegram.error.BadRequest as e:
                logger.error(f"Ошибка при скачивании файла {file_info['file_name']}: {e}")
                await query.edit_message_text(
                    text=f"Файл {file_info['file_name']} слишком большой (>50 МБ). "
                         f"Пожалуйста, отправьте прямую ссылку на файл."
                )
                return
        else:  # Файлы из URL
            photo_file_path = file_info['file_path']

        try:
            drive_service.upload_file(photo_file_path, date_folder_id, file_info['file_name'])
            uploaded_files.append(file_info['file_name'])
            os.remove(photo_file_path)
        except Exception as e:
            logger.error(f"Ошибка при загрузке файла {file_info['file_name']}: {e}")
            await query.edit_message_text(text=f'Ошибка при загрузке файла {file_info["file_name"]}.')
            return

    # Загрузка комментариев (без изменений)
    for comment in comments:
        current_file += 1
        progress_bar = create_progress_bar(current_file - 0.5, total_files)
        percentage = ((current_file - 0.5) / total_files) * 100

        progress_message = (
            f'Загружаю файлы...\n'
            f'Загрузка комментария {comment["filename"]}\n'
            f'{progress_bar} {percentage:.1f}%\n'
            f'Прогресс: {current_file}/{total_files}'
        )
        await query.edit_message_text(text=progress_message)

        comment_path = os.path.join(os.getcwd(), comment['filename'])
        with open(comment_path, 'w', encoding='utf-8') as f:
            f.write(comment['content'])

        try:
            drive_service.upload_file(comment_path, date_folder_id, comment['filename'])
            uploaded_files.append(comment['filename'])
            os.remove(comment_path)
        except Exception as e:
            logger.error(f"Ошибка при загрузке комментария {comment['filename']}: {e}")

    # Формирование итогового сообщения (без изменений)
    total_uploaded = len(uploaded_files)
    total_files = len(files) + len(context.user_data.get('unsupported_files', []))
    total_comments = len(context.user_data.get('comments', []))

    success_message = f'Успешно загружено {total_uploaded} {get_files_word(total_uploaded)}!\n'
    success_message += f'Папка: {folder_name}/{date_folder_name_str}\n'
    success_message += f'Всего {total_files} {get_files_word(total_files)}'
    if total_comments > 0:
        success_message += f' и {total_comments} {get_comments_word(total_comments)}'
    success_message += '\n'

    if uploaded_files:
        success_message += f'\nЗагруженные файлы:\n'
        for file in uploaded_files:
            if file.startswith('comment_'):
                continue
            success_message += f"• {file}\n"

    if context.user_data.get('comments'):
        success_message += f'\nКомментарии:\n'
        for comment in context.user_data['comments']:
            success_message += f"• {comment['filename']}\n"

    if context.user_data.get('unsupported_files'):
        success_message += f'\nНеподдерживаемые файлы:\n'
        for unsupported in context.user_data['unsupported_files']:
            success_message += f"• {unsupported['name']}\n"

    await query.edit_message_text(text=success_message)

    # Отправка статистики админам и запись в Google Sheets (без изменений)
    if ADMIN_USERS:
        for admin_id in ADMIN_USERS:
            try:
                await context.bot.send_message(chat_id=admin_id, text=success_message)
            except Exception as e:
                logger.error(f"Ошибка при отправке статистики админу {admin_id}: {e}")

    stats_folder_id = drive_service.find_folder_id_by_name(STATISTICS_FOLDER, upload_folder_id)
    if not stats_folder_id:
        stats_folder_id = drive_service.create_folder(upload_folder_id, STATISTICS_FOLDER)

    stats_file_id = drive_service.create_or_get_statistics_sheet(stats_folder_id, STATISTICS_FILE)
    drive_service.add_statistics_entry(
        stats_file_id,
        datetime.datetime.now() + datetime.timedelta(hours=0),
        query.from_user.id,
        f"{folder_name}/{date_folder_name_str}",
        uploaded_files
    )

    # Очистка данных
    context.user_data['files'] = []
    context.user_data['unsupported_files'] = []
    context.user_data['comments'] = []



def main() -> None:
    application = Application.builder().token(API_TOKEN).build()
    application.add_handler(CommandHandler("start", start))

    application.add_handler(MessageHandler(
        filters.PHOTO | filters.VIDEO | filters.AUDIO | filters.Document.ALL, handle_file
    ))
    application.add_handler(CallbackQueryHandler(handle_folder_selection))

    application.run_polling()


if __name__ == '__main__':
    main()