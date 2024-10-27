import datetime
import os
import logging
import mimetypes
from datetime import timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackContext, CallbackQueryHandler, filters
from gdrive_service import GoogleDriveService
from config import API_TOKEN, GOOGLE_DRIVE_CREDENTIALS_FILE, ALLOWED_USERS, MAX_FILE_SIZE_MB, EXCLUDED_FOLDERS, \
    USE_ALLOWED_USERS, STATISTICS_FOLDER, STATISTICS_FILE, ALLOWED_FILE_TYPES

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Добавляем регистрацию MIME-типа для jwpub
mimetypes.add_type('application/jwpub', '.jwpub')

drive_service = GoogleDriveService(GOOGLE_DRIVE_CREDENTIALS_FILE)


def get_file_type_category(mime_type, file_extension):
    """
    Определяет категорию файла на основе MIME-типа и расширения
    с дополнительной обработкой для jwpub файлов
    """
    # Специальная обработка для jwpub файлов
    if file_extension.lower() == '.jwpub':
        return 'jwpub'

    for category, settings in ALLOWED_FILE_TYPES.items():
        if mime_type in settings['mime_types'] or file_extension.lower() in settings['extensions']:
            return category
    return None


def format_size(size_mb):
    """Форматирует размер файла для удобного отображения"""
    if size_mb >= 1024:
        return f"{size_mb / 1024:.1f} ГБ"
    return f"{size_mb:.1f} МБ"


def get_allowed_files_description():
    """Возвращает отформатированное описание разрешенных типов файлов"""
    descriptions = []
    for category, settings in ALLOWED_FILE_TYPES.items():
        max_size = format_size(settings['max_size_mb'])
        extensions = ', '.join(settings['extensions'])
        descriptions.append(f"• {settings['description']} ({extensions}) - до {max_size}")
    return '\n'.join(descriptions)


welcome_message = (
    "Привет!\nЯ бот для работы с Google Drive.\n"
    "Умею загружать следующие типы файлов:\n\n"
    f"{get_allowed_files_description()}\n\n"
    "Пришлите мне файл, и я помогу загрузить его в нужную папку."
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

    if row:  # Если осталась одна кнопка после последней итерации
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

        if update.message.photo:
            file = update.message.photo[-1]
            file_type_category = 'image'
        elif update.message.video:
            file = update.message.video
            file_type_category = 'video'
        elif update.message.document:
            file = update.message.document
            mime_type = file.mime_type or 'application/octet-stream'
            file_extension = os.path.splitext(file.file_name)[1] if file.file_name else ''
            file_type_category = get_file_type_category(mime_type, file_extension)

        if not file:
            await update.message.reply_text('Ошибка: файл не найден.')
            return

        if not file_type_category:
            await update.message.reply_text(
                'Неподдерживаемый тип файла. Разрешены следующие типы:\n\n' +
                get_allowed_files_description()
            )
            return

        max_size = ALLOWED_FILE_TYPES[file_type_category]['max_size_mb']
        file_size_mb = file.file_size / (1024 * 1024)

        if file_size_mb > max_size:
            await update.message.reply_text(
                f'Размер файла ({format_size(file_size_mb)}) превышает допустимый ' +
                f'предел {format_size(max_size)} для типа {ALLOWED_FILE_TYPES[file_type_category]["description"]}.'
            )
            return

        if 'files' not in context.user_data:
            context.user_data['files'] = []

        # Определение имени файла
        if update.message.document:
            file_name = update.message.document.file_name
        elif update.message.video:
            file_name = f"video_{len(context.user_data['files']) + 1}.mp4"
        else:
            file_number = len(context.user_data['files']) + 1
            file_name = f"photo_{file_number}.jpg"

        context.user_data['files'].append({
            'file_id': file.file_id,
            'file_name': file_name,
            'type': file_type_category,
            'size_mb': file_size_mb
        })

        logger.info(f"Добавлен файл: {file_name} (тип: {file_type_category}, размер: {format_size(file_size_mb)})")

        # Удаляем предыдущее сообщение о принятых файлах, если оно есть
        if 'acceptance_message_id' in context.user_data:
            try:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id,
                    message_id=context.user_data['acceptance_message_id']
                )
            except Exception as e:
                logger.error(f"Ошибка при удалении предыдущего сообщения: {e}")

        # Формируем сообщение о всех принятых файлах
        # files_info = []
        # for file_info in context.user_data['files']:
        #     files_info.append(
        #         f"Файл принят: {file_info['file_name']}\n"
        #         f"Тип: {ALLOWED_FILE_TYPES[file_info['type']]['description']}\n"
        #         f"Размер: {format_size(file_info['size_mb'])}"
        #     )
        #
        # acceptance_message = "\n\n".join(files_info)
        # msg = await update.message.reply_text(acceptance_message)
        # context.user_data['acceptance_message_id'] = msg.message_id

        # Показываем кнопки выбора папки только если прошло достаточно времени
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

    # Скрываем кнопки
    await query.edit_message_reply_markup(reply_markup=None)
    await query.edit_message_text(text='Загружаю файлы...')

    files = context.user_data.get('files', [])

    if not files:
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

    def create_progress_bar(current, total, width=20):
        progress = int(width * current / total)
        return f"[{'■' * progress}{'□' * (width - progress)}]"

    uploaded_files = []
    for i, file_info in enumerate(files, 1):
        file_id = file_info['file_id']
        file_name = file_info['file_name']

        # Создаем прогресс-бар
        progress_bar = create_progress_bar(i - 0.5, len(files))  # -0.5 чтобы показать, что файл в процессе загрузки
        percentage = ((i - 0.5) / len(files)) * 100

        # Обновляем сообщение о текущем прогрессе
        progress_message = (
            f'Загружаю файлы...\n'
            f'Загрузка файла {file_name}\n'
            f'{progress_bar} {percentage:.1f}%\n'
            f'Прогресс: {i}/{len(files)}'
        )
        await query.edit_message_text(text=progress_message)

        photo_file = await context.bot.get_file(file_id)
        photo_file_path = os.path.join(os.getcwd(), file_name)

        await photo_file.download_to_drive(photo_file_path)

        try:
            logger.info(f"Загрузка файла {file_name} в Google Drive...")
            drive_service.upload_file(photo_file_path, date_folder_id, file_name)
            uploaded_files.append(file_name)

            # Обновляем прогресс-бар после завершения загрузки файла
            progress_bar = create_progress_bar(i, len(files))
            percentage = (i / len(files)) * 100
            progress_message = (
                f'Загружаю файлы...\n'
                f'Файл {file_name} загружен\n'
                f'{progress_bar} {percentage:.1f}%\n'
                f'Прогресс: {i}/{len(files)}'
            )
            await query.edit_message_text(text=progress_message)

            os.remove(photo_file_path)
        except Exception as e:
            logger.error(f"Ошибка при загрузке файла {file_name}: {e}")
            await query.edit_message_text(text=f'Ошибка при загрузке файла {file_name}.')
            return

    # Добавляем запись в статистику
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

    uploaded_files_str = "\n".join(uploaded_files)
    success_message = (f'Все файлы загружены успешно!\n'
                       f'Папка: {folder_name}/{date_folder_name_str}\n'
                       f'Количество файлов: {len(files)}\n'
                       f'Загруженные файлы:\n{uploaded_files_str}')

    await query.edit_message_text(text=success_message)

    # Очищаем список файлов после успешной загрузки
    context.user_data['files'] = []


def main() -> None:
    application = Application.builder().token(API_TOKEN).build()
    application.add_handler(CommandHandler("start", start))

    # Updated filter syntax for newer python-telegram-bot versions
    application.add_handler(MessageHandler(
        filters.PHOTO | filters.VIDEO | filters.Document.ALL, handle_file
    ))
    application.add_handler(CallbackQueryHandler(handle_folder_selection))

    application.run_polling()


if __name__ == '__main__':
    main()