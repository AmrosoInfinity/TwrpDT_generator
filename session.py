import os
import telebot
import asyncio
import threading
from pyrogram import Client
from pyrogram.errors import SessionPasswordNeeded

# Mengambil token bot dari brankas GitHub
BOT_TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)

# ====================================================================
# INTI PERBAIKAN: Membuat Background Thread untuk Event Loop Asyncio
# Ini menjaga koneksi Pyrogram tetap HIDUP 24/7 tanpa terputus
# ====================================================================
loop = asyncio.new_event_loop()

def start_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

# Menjalankan loop di latar belakang
threading.Thread(target=start_loop, args=(loop,), daemon=True).start()
# ====================================================================

# Penyimpanan sementara untuk data input user & client yang sedang aktif
user_data = {}
active_clients = {}

@bot.message_handler(commands=['start'])
def start(message):
    teks = (
        "🤖 **Selamat Datang di Bot Pembuat Pyrogram Session!**\n\n"
        "Bot ini dibuat khusus untuk membantu Anda menghasilkan **Session String** secara aman.\n\n"
        "Ketuk tombol di bawah untuk memulai prosesnya!"
    )
    markup = telebot.types.InlineKeyboardMarkup()
    btn = telebot.types.InlineKeyboardButton("🔑 Mulai Buat Session String", callback_data="start_session")
    markup.add(btn)
    bot.send_message(message.chat.id, teks, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "start_session")
def ask_api_id(call):
    bot.answer_callback_query(call.id)
    user_data[call.message.chat.id] = {}
    msg = bot.send_message(call.message.chat.id, "1️⃣ **Masukkan API ID Anda:**\n*(Hanya berupa deretan angka, contoh: 32158540)*", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_api_id)

def process_api_id(message):
    api_id = message.text.strip()
    if not api_id.isdigit():
        msg = bot.send_message(message.chat.id, "❌ API ID harus berupa angka. Silakan kirim ulang:")
        bot.register_next_step_handler(msg, process_api_id)
        return
    user_data[message.chat.id]['api_id'] = int(api_id)
    
    msg = bot.send_message(message.chat.id, "2️⃣ **Masukkan API HASH Anda:**\n*(Berupa kombinasi huruf dan angka)*", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_api_hash)

def process_api_hash(message):
    user_data[message.chat.id]['api_hash'] = message.text.strip()
    msg = bot.send_message(message.chat.id, "3️⃣ **Masukkan Nomor Telegram Anda:**\n*(Gunakan format internasional, contoh: +6281234567890)*", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_phone)

def process_phone(message):
    chat_id = message.chat.id
    user_data[chat_id]['phone'] = message.text.replace(" ", "").strip()
    bot.send_message(chat_id, "⏳ Mengirim permintaan kode login ke Telegram Anda...")
    
    # Melempar tugas ke background thread agar tidak memblokir bot
    future = asyncio.run_coroutine_threadsafe(send_login_code(chat_id), loop)
    future.result()

async def send_login_code(chat_id):
    data = user_data[chat_id]
    
    # Kita menggunakan memori RAM lagi karena sekarang koneksi sudah aman
    client = Client(f"session_{chat_id}", api_id=data['api_id'], api_hash=data['api_hash'], in_memory=True)
    active_clients[chat_id] = client
    
    await client.connect() # KONEKSI DITAHAN
    try:
        code_info = await client.send_code(data['phone'])
        data['phone_code_hash'] = code_info.phone_code_hash
        msg = bot.send_message(chat_id, "✅ **Kode telah dikirim!**\nPeriksa aplikasi Telegram Anda.\n\n4️⃣ **Ketik dan kirimkan kode tersebut di sini.**\n\n⚠️ *TIPS: Selipkan spasi (Contoh: 1 2 3 4 5)*", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_code)
    except Exception as e:
        bot.send_message(chat_id, f"❌ **Gagal mengirim kode:**\n`{e}`\n\nTekan /start untuk mengulang.", parse_mode="Markdown")
        await client.disconnect()
        del active_clients[chat_id]

def process_code(message):
    chat_id = message.chat.id
    code = message.text.replace(" ", "").replace("-", "").strip()
    user_data[chat_id]['code'] = code
    bot.send_message(chat_id, "⏳ Memverifikasi kode Anda...")
    
    future = asyncio.run_coroutine_threadsafe(verify_login_code(chat_id), loop)
    future.result()

async def verify_login_code(chat_id):
    data = user_data[chat_id]
    client = active_clients.get(chat_id)
    
    if not client:
        bot.send_message(chat_id, "❌ Koneksi terputus secara tidak terduga. Silakan tekan /start untuk mengulang.")
        return

    try:
        await client.sign_in(data['phone'], data['phone_code_hash'], data['code'])
        session_string = await client.export_session_string()
        send_success(chat_id, session_string)
        await client.disconnect()
        del active_clients[chat_id]
    except SessionPasswordNeeded:
        msg = bot.send_message(chat_id, "🔐 Akun Anda dilindungi **Verifikasi 2 Langkah**.\n\n5️⃣ **Masukkan password Telegram Anda:**", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_password)
    except Exception as e:
        bot.send_message(chat_id, f"❌ **Kode salah atau kadaluarsa:**\n`{e}`\n\nSilakan tekan /start untuk mengulang.", parse_mode="Markdown")
        await client.disconnect()
        del active_clients[chat_id]

def process_password(message):
    chat_id = message.chat.id
    user_data[chat_id]['password'] = message.text.strip()
    bot.send_message(chat_id, "⏳ Memverifikasi password...")
    
    future = asyncio.run_coroutine_threadsafe(verify_password(chat_id), loop)
    future.result()

async def verify_password(chat_id):
    data = user_data[chat_id]
    client = active_clients.get(chat_id)
    
    if not client:
        bot.send_message(chat_id, "❌ Koneksi terputus secara tidak terduga. Silakan tekan /start untuk mengulang.")
        return

    try:
        await client.check_password(data['password'])
        session_string = await client.export_session_string()
        send_success(chat_id, session_string)
    except Exception as e:
        bot.send_message(chat_id, f"❌ **Password salah:**\n`{e}`\n\nSilakan tekan /start untuk mengulang.", parse_mode="Markdown")
    finally:
        await client.disconnect()
        del active_clients[chat_id]

def send_success(chat_id, session_string):
    teks = (
        "🎉 **BERHASIL!** 🎉\n\n"
        "Berikut adalah **Session String** Anda. Salin seluruh teks di bawah ini:\n\n"
        f"`{session_string}`\n\n"
        "⚠️ **PERINGATAN KERAS:**\n"
        "Ini adalah kunci utama akun Telegram Anda. JANGAN DIBAGIKAN kepada siapa pun. Segera masukkan ke dalam rahasia (Secrets) GitHub Anda."
    )
    bot.send_message(chat_id, teks, parse_mode="Markdown")

bot.polling(none_stop=True)
