from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
import os

DOWNLOAD_DIR = "/home/a1161163"  # مسیر ذخیره روی VPS
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

TOKEN = "8186718003:AAGoJsGyE7SajlKv2SDbII5_NUuo-ptk40A"

def start(update: Update, context: CallbackContext):
    update.message.reply_text("سلام! فایل CSV رو اینجا بفرست.")

def handle_file(update: Update, context: CallbackContext):
    file = update.message.document.get_file()
    filename = os.path.join(DOWNLOAD_DIR, update.message.document.file_name)
    file.download(filename)
    update.message.reply_text(f"فایل دریافت شد و ذخیره شد: {filename}")

updater = Updater(TOKEN)
dp = updater.dispatcher

dp.add_handler(CommandHandler("start", start))
dp.add_handler(MessageHandler(Filters.document, handle_file))

updater.start_polling()
updater.idle()
