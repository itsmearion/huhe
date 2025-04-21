from pyrogram import Client, filters
from asyncio import sleep, create_task
import os
import sys
import time

# Konfigurasi bot
API_ID = 27917752
API_HASH = "bf6436f671e5363ed68edc1bb293d6d3"
BOT_TOKEN = "7955360080:AAHTYnr-2PZBYGwH5XG0PvdJ5VZdXSIeIDA"

app = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

pending_tasks = {}
RELOAD_COOLDOWN = 300  # 5 menit
last_reload_time = 0

# Handler untuk /start yang juga me-reload bot
@app.on_message(filters.command("start"))
async def start_handler(client, message):
    global last_reload_time
    now = time.time()

    if now - last_reload_time < RELOAD_COOLDOWN:
        sisa = int(RELOAD_COOLDOWN - (now - last_reload_time))
        await message.reply(f"Tunggu {sisa} detik lagi sebelum bisa /start ulang.")
        return

    last_reload_time = now
    await message.reply("Bot ini dibuat oleh @blakeshley secara eksklusif.\nBot sedang di-reload...")
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

app.run()