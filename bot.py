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
RELOAD_COOLDOWN = 300  # 5 menit
last_reload_time = 0

app = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
pending_tasks = {}

# Handler /start — reload dengan efek dreamy aesthetic
@app.on_message(filters.command("start"))
async def start_handler(client, message):
    global last_reload_time
    now = time.time()

    if now - last_reload_time < RELOAD_COOLDOWN:
        sisa = int(RELOAD_COOLDOWN - (now - last_reload_time))
        await message.reply(f"soft winds whisper — please wait {sisa} more seconds before we bloom anew.")
        return

    last_reload_time = now

    sent = await message.reply(
        "quietly reloading under dusk...\nstitched in silence by @blakeshley — not for the crowd, let it remain ours..."
    )

    async def reload_sequence():
        try:
            await sleep(3)

            # Kirim stiker transisi
            sticker = await client.send_sticker(
                chat_id=message.chat.id,
                sticker="CAACAgUAAxkBAAEBRZhlm-wxEN_fYF--uhHgUCo_Zu0u7AAC9gIAAnlc2VSpczhBBQ4h-DUE"
            )

            # Edit pesan dan hapus stiker
            await sent.edit(
                "reborn softly...\ncrafted under moonlight by @blakeshley — keep the vibe sacred."
            )
            await sticker.delete()

            await sleep(3)
            await sent.delete()

        except Exception:
            pass

        with open(RELOAD_FLAG, "w") as f:
            f.write("reload")

        await client.stop()
        os.execv(sys.executable, ['python3'] + sys.argv)

    create_task(reload_sequence())

# Handler /format — pesan order gaya biasa
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

# Delay auto-reply jika admin belum balas
async def delay_notice(client, chat_id, user_id):
    try:
        await sleep(300)
        await client.send_message(
            chat_id,
            "ᯓ ᡣ𐭩 the stars are still — our admin is away for a moment...\nplease wait in the calm, your message will find its way ᡣ𐭩ᡣ𐭩"
        )
    except Exception:
        pass

# Reset timer jika ada pesan non-command
@app.on_message(filters.text & ~filters.command("format") & ~filters.command("start"))
async def reset_timer_if_admin_replies(client, message):
    for task in pending_tasks.values():
        task.cancel()
    pending_tasks.clear()

# Jalankan bot
app.run()