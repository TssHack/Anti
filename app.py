from pyrogram import Client, filters
import json
import re
import os

# تنظیمات
api_id = 25584288     # 👈 API ID شما
api_hash = "ba2aeba66be85240a381afce80d0834b"  # 👈 API HASH شما
admin_id = 1848591768  # 👈 آیدی عددی شما

# نام فایل ذخیره وضعیت
state_file = "state.json"

# تابع بارگذاری وضعیت
def load_state():
    if os.path.exists(state_file):
        with open(state_file, "r") as f:
            data = json.load(f)
            return data.get("enabled", True)
    return True

# تابع ذخیره وضعیت
def save_state(enabled):
    with open(state_file, "w") as f:
        json.dump({"enabled": enabled}, f)

# تشخیص کد لاگین
def is_login_code(text):
    if not text:
        return False
    patterns = [
        r"\b\d{5,6}\b",  # کد عددی ۵ یا ۶ رقمی
        r"(کد ورود|کد تایید|Login code|Verification code)"
    ]
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)

# ساخت کلاینت
app = Client("anti_login", api_id=api_id, api_hash=api_hash)

# روشن کردن آنتی‌لاگین
@app.on_message(filters.command("on") & filters.user(admin_id))
async def turn_on(client, message):
    save_state(True)
    await message.reply("✅ آنتی‌لاگین فعال شد.")

# خاموش کردن آنتی‌لاگین
@app.on_message(filters.command("off") & filters.user(admin_id))
async def turn_off(client, message):
    save_state(False)
    await message.reply("❌ آنتی‌لاگین غیرفعال شد.")

# بررسی پیام‌های متنی (در همه چت‌ها)
@app.on_message(filters.text)
async def scan_message(client, message):
    if not load_state():
        return
    if is_login_code(message.text):
        try:
            await message.forward(admin_id)
        except Exception as e:
            print("❗ خطا در ارسال پیام:", e)

# اجرای برنامه
app.run()
