import datetime
import os
import logging
from datetime import timedelta  # Импортируем timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, Application, CommandHandler, ContextTypes, MessageHandler, CallbackContext, \
    CallbackQueryHandler, filters
from gdrive_service import GoogleDriveService
from config import API_TOKEN, GOOGLE_DRIVE_CREDENTIALS_FILE, ALLOWED_USERS, MAX_FILE_SIZE_MB, EXCLUDED_FOLDERS, \
    USE_ALLOWED_USERS, STATISTICS_FOLDER, STATISTICS_FILE
import asyncio
from aiohttp import web

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

drive_service = GoogleDriveService(GOOGLE_DRIVE_CREDENTIALS_FILE)

welcome_message = (
    "Привет! Я бот для работы с Google Drive.\n"
    "Пришли фото и я отправлю его в папку выбранного собрания."
)


# Функция для обработки команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(welcome_message, parse_mode='Markdown')


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


async def handle_photo(update: Update, context) -> None:
    try:
        logging.info("Получено фото от пользователя.")
        user_id = update.message.from_user.id
        logging.info(f"ID пользователя: {user_id}")

        if USE_ALLOWED_USERS and user_id not in ALLOWED_USERS:
            logging.warning(f"Пользователь {user_id} не имеет прав для загрузки файлов.")
            await update.message.reply_text('У вас нет прав для загрузки файлов.')
            return

        file = None
        if update.message.photo:
            file = update.message.photo[-1]
        elif update.message.document and update.message.document.mime_type.startswith('image/'):
            file = update.message.document

        if file:
            file_id = file.file_id
            file_size_mb = file.file_size / (1024 * 1024)

            if file_size_mb > MAX_FILE_SIZE_MB:
                await update.message.reply_text(f'Размер файла превышает {MAX_FILE_SIZE_MB} МБ.')
                return

            if 'photos' not in context.user_data:
                context.user_data['photos'] = []

            file_obj = await context.bot.get_file(file_id)
            file_name = update.message.document.file_name if update.message.document else f"photo_{len(context.user_data['photos']) + 1}.jpg"

            context.user_data['photos'].append((file_id, file_name))

            if len(context.user_data['photos']) == 1:
                await send_folder_buttons(update, context)
        else:
            logging.error("Ошибка: не удалось получить фото.")
            await update.message.reply_text('Ошибка: фото не найдено или загруженный файл не является изображением.')

    except Exception as e:
        logging.error(f"Ошибка в handle_photo: {e}")
        await update.message.reply_text('Произошла ошибка при обработке фото.')


async def handle_folder_selection(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()

    # Немедленно скрываем кнопки
    await query.edit_message_reply_markup(reply_markup=None)
    await query.edit_message_text(text='Начинаю загрузку фото...')

    photos = context.user_data.get('photos', [])

    if not photos:
        await query.edit_message_text(text='Ошибка: Фото не найдены. Пожалуйста, загрузите фото перед выбором папки.')
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
        logging.error(f"Ошибка при получении имени папки: {e}")
        await query.edit_message_text(text='Произошла ошибка при выборе папки.')
        return

    date_folder_name = datetime.datetime.now() + timedelta(hours=3)  # Добавляем 3 часа
    date_folder_name_str = date_folder_name.strftime("%d-%m-%Y")

    date_folder_id = drive_service.find_folder_id_by_name(date_folder_name_str, folder_id)
    if date_folder_id is None:
        date_folder_id = drive_service.create_folder(folder_id, date_folder_name_str)

    uploaded_files = []
    for i, (photo_file_id, original_file_name) in enumerate(photos, start=1):
        photo_file = await context.bot.get_file(photo_file_id)
        photo_file_path = os.path.join(os.getcwd(), original_file_name)

        await photo_file.download_to_drive(photo_file_path)

        try:
            logging.info(f"Загрузка файла {original_file_name} в Google Drive...")
            drive_service.upload_file(photo_file_path, date_folder_id, original_file_name)
            uploaded_files.append(original_file_name)
            os.remove(photo_file_path)
        except Exception as e:
            logging.error(f"Ошибка при загрузке файла {original_file_name}: {e}")
            await query.edit_message_text(text=f'Ошибка при загрузке фото {original_file_name}.')
            return

    # Добавляем запись в статистику
    stats_folder_id = drive_service.find_folder_id_by_name(STATISTICS_FOLDER, upload_folder_id)
    if not stats_folder_id:
        stats_folder_id = drive_service.create_folder(upload_folder_id, STATISTICS_FOLDER)

    stats_file_id = drive_service.create_or_get_statistics_sheet(stats_folder_id, STATISTICS_FILE)
    drive_service.add_statistics_entry(
        stats_file_id,
        datetime.datetime.now() + datetime.timedelta(hours=3),
        query.from_user.id,
        f"{folder_name}/{date_folder_name_str}",
        uploaded_files
    )

    uploaded_files_str = "\n".join(uploaded_files)
    success_message = (f'Все фото загружены успешно!\n'
                       f'Папка: {folder_name}/{date_folder_name_str}\n'
                       f'Количество фото: {len(photos)}\n'
                       f'Загруженные файлы:\n{uploaded_files_str}')

    await query.edit_message_text(text=success_message)
    await context.bot.send_message(chat_id=query.message.chat_id, text=f'Всего загружено: {len(photos)}')
    del context.user_data['photos']

async def web_server():
    app = web.Application()
    app.router.add_get("/", lambda request: web.Response(text="Bot is running"))
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Web server started on port {port}")


def main() -> None:
    application = Application.builder().token(API_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_photo))
    application.add_handler(CallbackQueryHandler(handle_folder_selection))

    loop = asyncio.get_event_loop()
    loop.create_task(web_server())
    application.run_polling()

if __name__ == '__main__':
    main()
