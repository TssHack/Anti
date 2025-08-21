import os
import logging
import asyncio
from pathlib import Path
from typing import Optional
import aiofiles
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from telegram.constants import ParseMode
from tqdm.asyncio import tqdm
import time

# Configuration
TOKEN = "8186718003:AAGoJsGyE7SajlKv2SDbII5_NUuo-ptk40A"  # استفاده از متغیر محیطی بهتر است
DOWNLOAD_DIR = Path("/home/a1161163")
MAX_FILE_SIZE = 40000 * 1024 * 1024  # 50MB limit
ALLOWED_EXTENSIONS = {'.csv', '.xlsx', '.xls', '.txt', '.json'}

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Create download directory
DOWNLOAD_DIR.mkdir(exist_ok=True)

class FileDownloadBot:
    def __init__(self):
        self.active_downloads = {}
    
    async def start(self, update: Update, context) -> None:
        """Send welcome message when the command /start is issued."""
        welcome_text = """
🤖 **سلام! به ربات دانلود فایل خوش آمدید**

📋 **قابلیت‌های ربات:**
• دانلود فایل‌های CSV، Excel، TXT و JSON
• نمایش نوار پیشرفت دانلود
• بررسی اعتبار فایل‌ها
• محدودیت حجم: 50MB

📤 **نحوه استفاده:**
فقط فایل مورد نظرتان را ارسال کنید!

⚙️ **دستورات:**
/start - شروع
/help - راهنما
/stats - آمار دانلودها
        """
        
        keyboard = [
            [InlineKeyboardButton("📊 آمار", callback_data='stats')],
            [InlineKeyboardButton("ℹ️ راهنما", callback_data='help')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            welcome_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    
    async def help_command(self, update: Update, context) -> None:
        """Send help information."""
        help_text = """
📚 **راهنمای استفاده**

**فرمت‌های پشتیبانی شده:**
• CSV (.csv)
• Excel (.xlsx, .xls)
• متن (.txt)
• JSON (.json)

**محدودیت‌ها:**
• حداکثر حجم: 50MB
• تنها فایل‌های معتبر پذیرفته می‌شوند

**نکات:**
• در صورت خطا، مجدداً تلاش کنید
• از اتصال پایدار اینترنت استفاده کنید
        """
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
    
    async def stats(self, update: Update, context) -> None:
        """Show download statistics."""
        try:
            files_count = len(list(DOWNLOAD_DIR.glob("*")))
            total_size = sum(f.stat().st_size for f in DOWNLOAD_DIR.glob("*") if f.is_file())
            total_size_mb = total_size / (1024 * 1024)
            
            stats_text = f"""
📊 **آمار دانلودها**

📁 تعداد فایل‌ها: {files_count}
💾 حجم کل: {total_size_mb:.2f} MB
📂 مسیر ذخیره: {DOWNLOAD_DIR}
🔄 دانلودهای فعال: {len(self.active_downloads)}
            """
        except Exception as e:
            stats_text = f"❌ خطا در دریافت آمار: {str(e)}"
        
        await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)
    
    def validate_file(self, document) -> tuple[bool, str]:
        """Validate uploaded file."""
        if not document.file_name:
            return False, "❌ نام فایل معتبر نیست"
        
        file_extension = Path(document.file_name).suffix.lower()
        if file_extension not in ALLOWED_EXTENSIONS:
            return False, f"❌ فرمت فایل پشتیبانی نمی‌شود. فرمت‌های مجاز: {', '.join(ALLOWED_EXTENSIONS)}"
        
        if document.file_size > MAX_FILE_SIZE:
            return False, f"❌ حجم فایل بیش از حد مجاز ({MAX_FILE_SIZE // (1024*1024)}MB) است"
        
        return True, "✅ فایل معتبر است"
    
    async def create_progress_message(self, chat_id, filename: str, context) -> int:
        """Create initial progress message."""
        progress_text = f"""
📥 **در حال دانلود...**
📄 فایل: `{filename}`
📊 پیشرفت: 0%
⏱️ زمان باقی‌مانده: محاسبه...

▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️ 0%
        """
        message = await context.bot.send_message(
            chat_id=chat_id,
            text=progress_text,
            parse_mode=ParseMode.MARKDOWN
        )
        return message.message_id
    
    async def update_progress(self, chat_id, message_id, filename: str, progress: float, speed: float, context) -> None:
        """Update progress message."""
        progress_percent = int(progress * 100)
        filled_blocks = int(progress * 10)
        empty_blocks = 10 - filled_blocks
        
        progress_bar = "🟩" * filled_blocks + "▫️" * empty_blocks
        
        eta = ""
        if speed > 0:
            remaining = (1 - progress) * 100  # approximate remaining time
            eta = f"⏱️ سرعت: {speed:.1f} KB/s"
        
        progress_text = f"""
📥 **در حال دانلود...**
📄 فایل: `{filename}`
📊 پیشرفت: {progress_percent}%
{eta}

{progress_bar} {progress_percent}%
        """
        
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=progress_text,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.warning(f"Could not update progress: {e}")
    
    async def handle_file(self, update: Update, context) -> None:
        """Handle file upload with progress bar."""
        document = update.message.document
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        
        # Validate file
        is_valid, message = self.validate_file(document)
        if not is_valid:
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
            return
        
        # Check if user has active download
        if user_id in self.active_downloads:
            await update.message.reply_text("❌ شما در حال حاضر یک دانلود فعال دارید. لطفاً صبر کنید.")
            return
        
        filename = document.file_name
        filepath = DOWNLOAD_DIR / filename
        
        # Add to active downloads
        self.active_downloads[user_id] = filename
        
        try:
            # Create progress message
            progress_msg_id = await self.create_progress_message(chat_id, filename, context)
            
            # Get file object
            file = await document.get_file()
            file_size = document.file_size
            
            # Download with progress tracking
            start_time = time.time()
            chunk_size = 8192
            downloaded = 0
            
            async with aiofiles.open(filepath, 'wb') as f:
                async for chunk in file.iter_chunks(chunk_size=chunk_size):
                    await f.write(chunk)
                    downloaded += len(chunk)
                    
                    # Update progress every 10% or 1MB
                    if downloaded % (file_size // 10 + 1) < chunk_size or downloaded % (1024*1024) < chunk_size:
                        progress = downloaded / file_size
                        elapsed_time = time.time() - start_time
                        speed = (downloaded / 1024) / elapsed_time if elapsed_time > 0 else 0
                        
                        await self.update_progress(
                            chat_id, progress_msg_id, filename, progress, speed, context
                        )
            
            # Final success message
            success_text = f"""
✅ **دانلود با موفقیت انجام شد!**

📄 فایل: `{filename}`
💾 حجم: {file_size / 1024:.1f} KB
📂 مسیر: `{filepath}`
⏱️ زمان دانلود: {time.time() - start_time:.1f} ثانیه

🎉 فایل آماده استفاده است!
            """
            
            # Delete progress message and send success message
            try:
                await context.bot.delete_message(chat_id, progress_msg_id)
            except:
                pass
            
            keyboard = [[InlineKeyboardButton("📊 مشاهده آمار", callback_data='stats')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                success_text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
            
            logger.info(f"File downloaded successfully: {filepath}")
            
        except Exception as e:
            error_text = f"❌ خطا در دانلود فایل: {str(e)}"
            await update.message.reply_text(error_text)
            logger.error(f"Download error: {e}")
            
            # Clean up failed download
            if filepath.exists():
                filepath.unlink()
        
        finally:
            # Remove from active downloads
            self.active_downloads.pop(user_id, None)
    
    async def button_callback(self, update: Update, context) -> None:
        """Handle button callbacks."""
        query = update.callback_query
        await query.answer()
        
        if query.data == 'stats':
            await self.stats(query, context)
        elif query.data == 'help':
            await self.help_command(query, context)
    
    async def error_handler(self, update: Update, context) -> None:
        """Log errors caused by Updates."""
        logger.warning(f'Update {update} caused error {context.error}')

def main() -> None:
    """Start the bot."""
    # Create bot instance
    bot = FileDownloadBot()
    
    # Create application
    application = Application.builder().token(TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("help", bot.help_command))
    application.add_handler(CommandHandler("stats", bot.stats))
    application.add_handler(MessageHandler(filters.Document.ALL, bot.handle_file))
    application.add_handler(CallbackQueryHandler(bot.button_callback))
    
    # Add error handler
    application.add_error_handler(bot.error_handler)
    
    # Start the bot
    logger.info("Starting bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
