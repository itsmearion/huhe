from pyrogram import Client, filters
from asyncio import sleep, create_task
import os
import sys
import time

API_ID = 27917752
API_HASH = "bf6436f671e5363ed68edc1bb293d6d3"
BOT_TOKEN = "7955360080:AAHTYnr-2PZBYGwH5XG0PvdJ5VZdXSIeIDA"

app = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

pending_tasks = {}
last_reload_time = 0
RELOAD_COOLDOWN = 300

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

async def delay_notice(client, chat_id, user_id):
    try:
        await sleep(300)  # 5 menit
        await client.send_message(chat_id, "ᯓ ᡣ𐭩 Halo kak, admin kami sedang offline, tunggu sampai admin membalas pesan kamu, terima kasih  ᡣ𐭩ᡣ𐭩")
    except Exception:
        pass

@app.on_message(filters.text & ~filters.command("format") & ~filters.command("reload"))
async def reset_timer_if_admin_replies(client, message):
    for task in pending_tasks.values():
        task.cancel()
    pending_tasks.clear()

@app.on_message(filters.command("reload"))
async def reload_handler(client, message):
    global last_reload_time
    now = time.time()

    if now - last_reload_time < RELOAD_COOLDOWN:
        sisa = int(RELOAD_COOLDOWN - (now - last_reload_time))
        await message.reply(f"Tunggu {sisa} detik lagi sebelum bisa /reload lagi.")
        return

    last_reload_time = now
    await message.reply("Bot sedang di-reload...")
    await client.stop()
    os.execv(sys.executable, ['python3'] + sys.argv)

app.run()