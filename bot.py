from pyrogram import Client, filters
from asyncio import sleep, create_task
import os
import sys
import time

# Konfigurasi bot
API_ID = 27917752
API_HASH = "bf6436f671e5363ed68edc1bb293d6d3"
BOT_TOKEN = "7955360080:AAHTYnr-2PZBYGwH5XG0PvdJ5VZdXSIeIDA"

RELOAD_FLAG = "reload.flag"

app = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

pending_tasks = {}
RELOAD_COOLDOWN = 300  # 5 menit
last_reload_time = 0

# Kirim pesan jika bot berhasil di-reload
@app.on_message(filters.command("start"))
async def start_handler(client, message):
    global last_reload_time
    now = time.time()

    if now - last_reload_time < RELOAD_COOLDOWN:
        sisa = int(RELOAD_COOLDOWN - (now - last_reload_time))
        await message.reply(f"Tunggu {sisa} detik lagi sebelum bisa /start ulang.")
        return

    last_reload_time = now
    await message.reply("Bot sedang di-reload.\ncrafted exclusively by @blakeshley. Not for public use, don’t steal the vibe...")
    # Buat file penanda reload
    with open(RELOAD_FLAG, "w") as f:
        f.write("reload")

    await client.stop()
    os.execv(sys.executable, ['python3'] + sys.argv)

# Handler untuk /format
@app.on_message(filters.command("format"))
async def format_handler(client, message):
    username = message.from_user.username or "unknown"
    text = (
        f"Salutations I'm @{username}, I’d like to place an order for catalog [t.me/blakeshley] "
        "listed at Blakeshley, Using payment method [dana, gopay, qriss, spay, ovo, bank.] "
        "The total comes to IDR [00.000] Inrush add 5k [yay/nay]. Kindly process this, Thanks a bunch."
    )
    await message.reply(text)

    user_id = message.from_user.id
    if user_id in pending_tasks:
        pending_tasks[user_id].cancel()

    task = create_task(delay_notice(client, message.chat.id, user_id))
    pending_tasks[user_id] = task

# Fungsi auto-kirim pesan jika admin tidak membalas
async def delay_notice(client, chat_id, user_id):
    try:
        await sleep(300)  # 5 menit
        await client.send_message(chat_id, "ᯓ ᡣ𐭩 Halo kak, admin kami sedang offline, tunggu sampai admin membalas pesan kamu, terima kasih ᡣ𐭩ᡣ𐭩")
    except Exception:
        pass

# Reset jika ada pesan masuk selain command
@app.on_message(filters.text & ~filters.command("format") & ~filters.command("start"))
async def reset_timer_if_admin_replies(client, message):
    for task in pending_tasks.values():
        task.cancel()
    pending_tasks.clear()

# Cek apakah habis reload
async def on_startup():
    if os.path.exists(RELOAD_FLAG):
        os.remove(RELOAD_FLAG)
        async with app:
            await app.send_message("me", "Bot berhasil di-reload.\ncrafted exclusively by @blakeshley. Not for public use, don’t steal the vibe")

app.run()