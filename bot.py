from pyrogram import Client, filters
from asyncio import sleep
from threading import Timer

# Ganti dengan informasi bot kamu
API_ID = 123456
API_HASH = "your_api_hash"
BOT_TOKEN = "YOUR_BOT_TOKEN"

app = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Dictionary untuk simpan status waiting reply
pending_replies = {}

@app.on_message(filters.command("format"))
async def format_handler(client, message):
    username = message.from_user.username or "unknown"
    text = (
        f"Salutations I'm @{username}, I’d like to place an order for catalog [t.me/catal] "
        "listed at Blakeshley, Using payment method [dana, gopay, qriss, spay, ovo, bank.] "
        "The total comes to IDR 00.000 Inrush add 5k [yay/nay]. Kindly process this, Thanks a bunch."
    )
    await message.reply(text)

    # Set timer auto-pesan jika admin tidak membalas
    user_id = message.from_user.id
    if user_id in pending_replies:
        pending_replies[user_id].cancel()

    timer = Timer(600, send_admin_offline_notice, args=(client, message.chat.id))
    pending_replies[user_id] = timer
    timer.start()

async def send_admin_offline_notice(client, chat_id):
    text = "ᯓ ᡣ𐭩 Halo kak, admin kami sedang offline, tunggu sampai admin membalas pesan kamu, terima kasih  ᡣ𐭩ᡣ𐭩"
    await client.send_message(chat_id, text)

# Reset timer jika admin (bisa difilter lewat ID atau nama) membalas
@app.on_message(filters.text & ~filters.command("format"))
async def reset_timer_if_admin_replies(client, message):
    admin_user_ids = [123456789]  # Ganti dengan user_id admin
    if message.from_user.id in admin_user_ids:
        for timer in pending_replies.values():
            timer.cancel()
        pending_replies.clear()

app.run()
