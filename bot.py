import datetime
import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from drive_service import GoogleDriveService
from config import API_TOKEN, GOOGLE_DRIVE_CREDENTIALS_FILE, FOLDER_IDS, ALLOWED_USERS, MAX_FILE_SIZE_MB
from googleapiclient.discovery import build

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

drive_service = GoogleDriveService(GOOGLE_DRIVE_CREDENTIALS_FILE)
print(FOLDER_IDS)

async def start(update: Update, context) -> None:
    logging.info("Команда /start вызвана.")
    await update.message.reply_text('Привет! Отправь мне фото для загрузки.')

def get_folders(service, parent_id):
    results = service.files().list(
        q=f"'{parent_id}' in parents and mimeType='application/vnd.google-apps.folder'",
        fields="files(id, name)"
    ).execute()
    folders = results.get('files', [])
    folder_dict = {folder['name']: folder['id'] for folder in folders}
    return folder_dict

async def send_folder_buttons(update: Update) -> None:
    keyboard = [[InlineKeyboardButton(name.capitalize(), callback_data=name) for name in FOLDER_IDS.keys()]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Выберите папку для загрузки:', reply_markup=reply_markup)


async def handle_photo(update: Update, context) -> None:
    try:
        logging.info("Получено фото от пользователя.")
        user_id = update.message.from_user.id
        logging.info(f"ID пользователя: {user_id}")

        if user_id not in ALLOWED_USERS:
            logging.warning(f"Пользователь {user_id} не имеет прав для загрузки файлов.")
            await update.message.reply_text('У вас нет прав для загрузки файлов.')
            return

        if update.message.photo:
            logging.info("Фото получено: %s", update.message.photo[-1].file_id)
            file_size_mb = update.message.photo[-1].file_size / (1024 * 1024)

            if file_size_mb > MAX_FILE_SIZE_MB:
                await update.message.reply_text(f'Размер файла превышает {MAX_FILE_SIZE_MB} МБ.')
                return

            context.user_data['photo'] = update.message.photo[-1].file_id
            await send_folder_buttons(update)
        else:
            logging.error("Ошибка: не удалось получить фото.")
            await update.message.reply_text('Ошибка: фото не найдено.')
    except Exception as e:
        logging.error(f"Ошибка в handle_photo: {e}")
        await update.message.reply_text('Произошла ошибка при обработке фото.')


async def handle_folder_selection(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()

    folder_name = query.data
    folder_id = FOLDER_IDS[folder_name]

    photo_file_id = context.user_data.get('photo')

    if photo_file_id:
        # Отправляем сообщение о начале загрузки
        await query.edit_message_text(text='Начинаю загрузку фото...')

        # Получаем информацию о файле
        photo_file = await context.bot.get_file(photo_file_id)

        # Определяем оригинальное имя файла
        original_file_name = f"{photo_file.file_id}.jpg"  # Замените на метод получения оригинального имени, если необходимо

        # Создаем папку с датой
        new_folder_name = datetime.datetime.now().strftime("%Y-%m-%d")
        existing_folder_id = drive_service.find_folder_id_by_name(new_folder_name)

        if existing_folder_id is None:
            # Создаем папку, если она не существует
            new_folder_id = drive_service.create_folder(folder_id, new_folder_name)
        else:
            # Если папка существует, получаем ее ID, но ищем в выбранной папке
            existing_folder_id = drive_service.find_folder_id_by_name(new_folder_name, folder_id)

            if existing_folder_id is None:
                new_folder_id = drive_service.create_folder(folder_id, new_folder_name)
            else:
                new_folder_id = existing_folder_id

        # Путь к сохраненному файлу
        photo_file_path = os.path.join(os.getcwd(), original_file_name)

        # Загружаем фото
        await photo_file.download_to_drive(photo_file_path)

        try:
            logging.info("Загрузка файла в Google Drive...")
            drive_service.upload_file(photo_file_path, new_folder_id)  # Загрузка в папку с именем даты
            os.remove(photo_file_path)  # Удаляем файл после загрузки
            await query.edit_message_text(text='Фото загружено успешно!')
            del context.user_data['photo']  # Очищаем данные пользователя после обработки
        except Exception as e:
            logging.error("Ошибка при загрузке файла: %s", e)
            await query.edit_message_text(text='Ошибка при загрузке фото.')
    else:
        await query.edit_message_text(text='Ошибка: Фото не найдено.')


def main() -> None:
    application = Application.builder().token(API_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(CallbackQueryHandler(handle_folder_selection))

    application.run_polling()


if __name__ == '__main__':
    main()
