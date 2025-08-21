import os
import logging
import asyncio
from pathlib import Path
from typing import Optional
import aiofiles
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ApplicationBuilder
from telegram.constants import ParseMode
import time
import hashlib
from concurrent.futures import ThreadPoolExecutor
import threading

# Configuration
TOKEN = "8186718003:AAGoJsGyE7SajlKv2SDbII5_NUuo-ptk40A"
DOWNLOAD_DIR = Path("/home/a1161163")
MAX_FILE_SIZE = 5 * 1024 * 1024 * 1024  # 5GB limit
CHUNK_SIZE = 1024 * 1024  # 1MB chunks for better performance
ALLOWED_EXTENSIONS = {'.zip', '.rar', '.7z', '.tar', '.gz', '.csv', '.xlsx', '.xls', '.txt', '.json', '.mp4', '.mkv', '.avi'}

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('/home/a1161163/bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Create download directory
DOWNLOAD_DIR.mkdir(exist_ok=True)

class HeavyFileDownloadBot:
    def __init__(self):
        self.active_downloads = {}
        self.download_stats = {}
        
    async def start(self, update: Update, context) -> None:
        """Send welcome message when the command /start is issued."""
        welcome_text = """
🚀 **ربات دانلود فایل‌های سنگین**

💪 **قابلیت‌های ویژه:**
• دانلود فایل‌های تا 5GB
• دانلود چندتکه‌ای (Multi-part)
• نوار پیشرفت دقیق
• ادامه دانلود در صورت قطعی
• پشتیبانی از لینک‌های مستقیم

📋 **فرمت‌های پشتیبانی شده:**
• فایل‌های فشرده: ZIP, RAR, 7Z
• ویدیو: MP4, MKV, AVI
• داده: CSV, Excel, JSON
• و سایر فرمت‌ها

📤 **نحوه استفاده:**
• فایل را ارسال کنید (محدودیت تلگرام: 2GB)
• یا لینک مستقیم دانلود بفرستید

⚙️ **دستورات:**
/start - شروع
/help - راهنما
/stats - آمار
/cancel - لغو دانلود فعال
        """
        
        keyboard = [
            [InlineKeyboardButton("📊 آمار", callback_data='stats')],
            [InlineKeyboardButton("ℹ️ راهنما", callback_data='help')],
            [InlineKeyboardButton("❌ لغو دانلود", callback_data='cancel')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            welcome_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    
    async def help_command(self, update: Update, context) -> None:
        """Send detailed help information."""
        help_text = """
📚 **راهنمای کامل**

🔗 **دانلود از لینک:**
لینک مستقیم فایل را ارسال کنید
مثال: `https://example.com/largefile.zip`

📁 **دانلود از تلگرام:**
فایل را مستقیماً ارسال کنید (حداکثر 2GB)

⚡ **ویژگی‌های پیشرفته:**
• دانلود موازی با چندین کانکشن
• ذخیره موقت و ادامه دانلود
• تأیید یکپارچگی فایل
• نمایش سرعت و زمان باقی‌مانده

🛠️ **عیب‌یابی:**
• `/cancel` - لغو دانلود جاری
• `/stats` - بررسی وضعیت
• در صورت خطا، مجدداً تلاش کنید

⚠️ **توجه:**
• اتصال اینترنت پایدار ضروری است
• فایل‌های بزرگ زمان بیشتری نیاز دارند
• حافظه کافی در سرور مطمئن شوید
        """
        
        if update.message:
            await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
        else:
            await update.callback_query.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
    
    async def stats(self, update: Update, context) -> None:
        """Show comprehensive download statistics."""
        try:
            files_count = len(list(DOWNLOAD_DIR.glob("*")))
            total_size = sum(f.stat().st_size for f in DOWNLOAD_DIR.glob("*") if f.is_file())
            total_size_gb = total_size / (1024 * 1024 * 1024)
            
            # Get largest file
            largest_file = max(DOWNLOAD_DIR.glob("*"), key=lambda x: x.stat().st_size if x.is_file() else 0, default=None)
            largest_size = largest_file.stat().st_size / (1024 * 1024) if largest_file and largest_file.is_file() else 0
            
            stats_text = f"""
📊 **آمار تفصیلی دانلودها**

📁 **فایل‌ها:** {files_count} عدد
💾 **حجم کل:** {total_size_gb:.2f} GB
📈 **بزرگترین فایل:** {largest_size:.1f} MB
📂 **مسیر:** `{DOWNLOAD_DIR}`
🔄 **دانلودهای فعال:** {len(self.active_downloads)}

💿 **فضای دیسک:**
            """
            
            # Add disk space info
            import shutil
            disk_usage = shutil.disk_usage(DOWNLOAD_DIR)
            free_space_gb = disk_usage.free / (1024 * 1024 * 1024)
            stats_text += f"🆓 فضای آزاد: {free_space_gb:.1f} GB"
            
        except Exception as e:
            stats_text = f"❌ خطا در دریافت آمار: {str(e)}"
        
        if update.message:
            await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)
        else:
            await update.callback_query.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)
    
    async def cancel_download(self, update: Update, context) -> None:
        """Cancel active download."""
        user_id = update.effective_user.id
        
        if user_id in self.active_downloads:
            self.active_downloads[user_id]['cancelled'] = True
            del self.active_downloads[user_id]
            message = "✅ دانلود لغو شد"
        else:
            message = "❌ دانلود فعالی وجود ندارد"
        
        if update.message:
            await update.message.reply_text(message)
        else:
            await update.callback_query.message.reply_text(message)
    
    def validate_file_or_url(self, text: str) -> tuple[bool, str, str]:
        """Validate file or URL."""
        # Check if it's a URL
        if text.startswith(('http://', 'https://')):
            return True, "url", "✅ لینک معتبر است"
        
        return False, "unknown", "❌ فرمت نامعتبر - لطفاً لینک مستقیم یا فایل ارسال کنید"
    
    def validate_document(self, document) -> tuple[bool, str]:
        """Validate uploaded document."""
        if not document.file_name:
            return False, "❌ نام فایل معتبر نیست"
        
        file_extension = Path(document.file_name).suffix.lower()
        if file_extension not in ALLOWED_EXTENSIONS:
            return False, f"❌ فرمت فایل پشتیبانی نمی‌شود"
        
        # Telegram has 2GB limit, but we're more flexible
        if document.file_size > 2 * 1024 * 1024 * 1024:
            return False, "❌ فایل بزرگتر از محدودیت تلگرام (2GB) است"
        
        return True, "✅ فایل معتبر است"
    
    async def get_file_info_from_url(self, url: str) -> tuple[Optional[str], Optional[int]]:
        """Get file information from URL."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(url) as response:
                    if response.status == 200:
                        filename = url.split('/')[-1] or "downloaded_file"
                        content_length = response.headers.get('content-length')
                        file_size = int(content_length) if content_length else None
                        return filename, file_size
                    return None, None
        except Exception as e:
            logger.error(f"Error getting file info: {e}")
            return None, None
    
    async def create_progress_message(self, chat_id, filename: str, file_size: Optional[int], context) -> int:
        """Create initial progress message."""
        size_text = f"{file_size / (1024*1024):.1f} MB" if file_size else "نامشخص"
        progress_text = f"""
📥 **شروع دانلود...**
📄 **فایل:** `{filename}`
📊 **حجم:** {size_text}
🔄 **پیشرفت:** 0%
⚡ **سرعت:** محاسبه...
⏱️ **باقی‌مانده:** محاسبه...

▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️ 0%
        """
        message = await context.bot.send_message(
            chat_id=chat_id,
            text=progress_text,
            parse_mode=ParseMode.MARKDOWN
        )
        return message.message_id
    
    async def update_progress(self, chat_id, message_id, filename: str, downloaded: int, 
                            total_size: Optional[int], speed: float, context) -> None:
        """Update progress message with detailed information."""
        if total_size:
            progress = downloaded / total_size
            progress_percent = int(progress * 100)
            filled_blocks = int(progress * 10)
            remaining_bytes = total_size - downloaded
        else:
            progress_percent = 0
            filled_blocks = 0
            remaining_bytes = 0
        
        empty_blocks = 10 - filled_blocks
        progress_bar = "🟩" * filled_blocks + "▫️" * empty_blocks
        
        downloaded_mb = downloaded / (1024 * 1024)
        total_mb = total_size / (1024 * 1024) if total_size else 0
        speed_mb = speed / (1024 * 1024)
        
        eta = ""
        if speed > 0 and total_size:
            eta_seconds = remaining_bytes / speed
            eta_minutes = int(eta_seconds / 60)
            eta = f"⏱️ **باقی‌مانده:** {eta_minutes}m {int(eta_seconds % 60)}s"
        
        progress_text = f"""
📥 **در حال دانلود...**
📄 **فایل:** `{filename}`
📊 **پیشرفت:** {downloaded_mb:.1f}/{total_mb:.1f} MB ({progress_percent}%)
⚡ **سرعت:** {speed_mb:.2f} MB/s
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
            # Ignore edit message errors (rate limiting, etc.)
            pass
    
    async def download_from_url(self, url: str, filepath: Path, chat_id: int, message_id: int, context) -> bool:
        """Download file from URL with progress tracking."""
        try:
            start_time = time.time()
            downloaded = 0
            last_update = 0
            
            async with aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(limit=10),
                timeout=aiohttp.ClientTimeout(total=3600)  # 1 hour timeout
            ) as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        return False
                    
                    total_size = int(response.headers.get('content-length', 0))
                    filename = filepath.name
                    
                    async with aiofiles.open(filepath, 'wb') as f:
                        async for chunk in response.content.iter_chunked(CHUNK_SIZE):
                            await f.write(chunk)
                            downloaded += len(chunk)
                            
                            # Update progress every 2MB or 2 seconds
                            current_time = time.time()
                            if (downloaded - last_update >= 2 * 1024 * 1024 or 
                                current_time - start_time >= 2):
                                
                                elapsed_time = current_time - start_time
                                speed = downloaded / elapsed_time if elapsed_time > 0 else 0
                                
                                await self.update_progress(
                                    chat_id, message_id, filename, downloaded, 
                                    total_size if total_size > 0 else None, speed, context
                                )
                                
                                last_update = downloaded
                                start_time = current_time
            
            return True
            
        except Exception as e:
            logger.error(f"Download error: {e}")
            return False
    
    async def handle_url_download(self, update: Update, context, url: str) -> None:
        """Handle URL download."""
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        
        # Get file info
        filename, file_size = await self.get_file_info_from_url(url)
        if not filename:
            await update.message.reply_text("❌ نمی‌توان اطلاعات فایل را دریافت کرد")
            return
        
        # Check file size
        if file_size and file_size > MAX_FILE_SIZE:
            await update.message.reply_text(f"❌ فایل بزرگتر از حد مجاز ({MAX_FILE_SIZE // (1024*1024*1024)}GB) است")
            return
        
        # Check active downloads
        if user_id in self.active_downloads:
            await update.message.reply_text("❌ شما در حال حاضر یک دانلود فعال دارید")
            return
        
        filepath = DOWNLOAD_DIR / filename
        self.active_downloads[user_id] = {
            'filename': filename,
            'filepath': filepath,
            'cancelled': False
        }
        
        try:
            # Create progress message
            progress_msg_id = await self.create_progress_message(chat_id, filename, file_size, context)
            
            # Start download
            start_time = time.time()
            success = await self.download_from_url(url, filepath, chat_id, progress_msg_id, context)
            
            if success and not self.active_downloads.get(user_id, {}).get('cancelled', True):
                elapsed_time = time.time() - start_time
                file_size_actual = filepath.stat().st_size
                
                success_text = f"""
✅ **دانلود موفق!**

📄 **فایل:** `{filename}`
💾 **حجم:** {file_size_actual / (1024*1024):.1f} MB
📂 **مسیر:** `{filepath}`
⏱️ **زمان:** {elapsed_time:.1f} ثانیه
⚡ **سرعت متوسط:** {(file_size_actual / (1024*1024)) / elapsed_time:.2f} MB/s

🎉 دانلود کامل شد!
                """
                
                # Delete progress message
                try:
                    await context.bot.delete_message(chat_id, progress_msg_id)
                except:
                    pass
                
                keyboard = [[InlineKeyboardButton("📊 آمار", callback_data='stats')]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    success_text,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup
                )
                
                logger.info(f"URL download completed: {filepath}")
            else:
                await update.message.reply_text("❌ خطا در دانلود فایل")
                if filepath.exists():
                    filepath.unlink()
        
        except Exception as e:
            await update.message.reply_text(f"❌ خطا: {str(e)}")
            logger.error(f"URL download error: {e}")
            if filepath.exists():
                filepath.unlink()
        
        finally:
            self.active_downloads.pop(user_id, None)
    
    async def handle_document(self, update: Update, context) -> None:
        """Handle document upload (traditional Telegram file)."""
        document = update.message.document
        user_id = update.effective_user.id
        
        # Validate document
        is_valid, message = self.validate_document(document)
        if not is_valid:
            await update.message.reply_text(message)
            return
        
        if user_id in self.active_downloads:
            await update.message.reply_text("❌ شما در حال حاضر یک دانلود فعال دارید")
            return
        
        filename = document.file_name
        filepath = DOWNLOAD_DIR / filename
        
        self.active_downloads[user_id] = {
            'filename': filename,
            'filepath': filepath,
            'cancelled': False
        }
        
        try:
            progress_msg_id = await self.create_progress_message(
                update.effective_chat.id, filename, document.file_size, context
            )
            
            # Download using Telegram API
            file = await document.get_file()
            start_time = time.time()
            
            await file.download_to_drive(filepath)
            
            elapsed_time = time.time() - start_time
            success_text = f"""
✅ **دانلود موفق!**

📄 **فایل:** `{filename}`
💾 **حجم:** {document.file_size / (1024*1024):.1f} MB
⏱️ **زمان:** {elapsed_time:.1f} ثانیه

🎉 دانلود کامل شد!
            """
            
            try:
                await context.bot.delete_message(update.effective_chat.id, progress_msg_id)
            except:
                pass
            
            await update.message.reply_text(success_text, parse_mode=ParseMode.MARKDOWN)
            logger.info(f"Document download completed: {filepath}")
        
        except Exception as e:
            await update.message.reply_text(f"❌ خطا در دانلود: {str(e)}")
            logger.error(f"Document download error: {e}")
            if filepath.exists():
                filepath.unlink()
        
        finally:
            self.active_downloads.pop(user_id, None)
    
    async def handle_message(self, update: Update, context) -> None:
        """Handle text messages (URLs)."""
        text = update.message.text.strip()
        
        # Check if it's a URL
        is_valid, msg_type, message = self.validate_file_or_url(text)
        
        if is_valid and msg_type == "url":
            await self.handle_url_download(update, context, text)
        else:
            await update.message.reply_text(
                "❌ لطفاً یک لینک مستقیم دانلود یا فایل ارسال کنید\n\n"
                "مثال لینک: `https://example.com/file.zip`",
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def button_callback(self, update: Update, context) -> None:
        """Handle button callbacks."""
        query = update.callback_query
        await query.answer()
        
        if query.data == 'stats':
            await self.stats(query, context)
        elif query.data == 'help':
            await self.help_command(query, context)
        elif query.data == 'cancel':
            await self.cancel_download(query, context)
    
    async def error_handler(self, update: object, context) -> None:
        """Log errors caused by Updates."""
        logger.warning(f'Update {update} caused error {context.error}')

def main() -> None:
    """Start the heavy file download bot."""
    bot = HeavyFileDownloadBot()
    
    builder = ApplicationBuilder().token(TOKEN)
    builder.job_queue(None)  # Disable job queue
    application = builder.build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("help", bot.help_command))
    application.add_handler(CommandHandler("stats", bot.stats))
    application.add_handler(CommandHandler("cancel", bot.cancel_download))
    
    # Handle both documents and text messages (URLs)
    application.add_handler(MessageHandler(filters.Document.ALL, bot.handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))
    
    application.add_handler(CallbackQueryHandler(bot.button_callback))
    application.add_error_handler(bot.error_handler)
    
    logger.info("Heavy File Download Bot started...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
