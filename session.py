import os
import telebot
import asyncio
from pyrogram import Client
from pyrogram.errors import SessionPasswordNeeded

# Mengambil token bot dari brankas GitHub
BOT_TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)

# Penyimpanan sementara untuk data input user
user_data = {}

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
    user_data[message.chat.id]['phone'] = message.text.replace(" ", "").strip()
    bot.send_message(message.chat.id, "⏳ Mengirim permintaan kode login ke Telegram Anda...")
    asyncio.run(send_login_code(message.chat.id))

async def send_login_code(chat_id):
    data = user_data[chat_id]
    
    # HAPUS in_memory=True agar dibuatkan file session fisik sementara
    client = Client(f"session_{chat_id}", api_id=data['api_id'], api_hash=data['api_hash'])
    
    await client.connect()
    try:
        code_info = await client.send_code(data['phone'])
        data['phone_code_hash'] = code_info.phone_code_hash
        msg = bot.send_message(chat_id, "✅ **Kode telah dikirim!**\nPeriksa aplikasi Telegram Anda.\n\n4️⃣ **Ketik dan kirimkan kode tersebut di sini.**\n\n⚠️ *TIPS: Selipkan spasi (Contoh: 1 2 3 4 5)*", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_code)
    except Exception as e:
        bot.send_message(chat_id, f"❌ **Gagal mengirim kode:**\n`{e}`\n\nTekan /start untuk mengulang.", parse_mode="Markdown")
    finally:
        await client.disconnect() # Putuskan koneksi dengan aman

def process_code(message):
    code = message.text.replace(" ", "").replace("-", "").strip()
    user_data[message.chat.id]['code'] = code
    bot.send_message(message.chat.id, "⏳ Memverifikasi kode Anda...")
    asyncio.run(verify_login_code(message.chat.id))

async def verify_login_code(chat_id):
    data = user_data[chat_id]
    
    # Buka kembali file session yang tadi tersimpan
    client = Client(f"session_{chat_id}", api_id=data['api_id'], api_hash=data['api_hash'])
    await client.connect()
    
    try:
        await client.sign_in(data['phone'], data['phone_code_hash'], data['code'])
        session_string = await client.export_session_string()
        send_success(chat_id, session_string)
        await client.disconnect()
        clean_up(chat_id)
    except SessionPasswordNeeded:
        msg = bot.send_message(chat_id, "🔐 Akun Anda dilindungi **Verifikasi 2 Langkah**.\n\n5️⃣ **Masukkan password Telegram Anda:**", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_password)
        await client.disconnect()
    except Exception as e:
        bot.send_message(chat_id, f"❌ **Kode salah atau kadaluarsa:**\n`{e}`\n\nSilakan tekan /start untuk mengulang.", parse_mode="Markdown")
        await client.disconnect()
        clean_up(chat_id)

def process_password(message):
    user_data[message.chat.id]['password'] = message.text.strip()
    bot.send_message(message.chat.id, "⏳ Memverifikasi password...")
    asyncio.run(verify_password(message.chat.id))

async def verify_password(chat_id):
    data = user_data[chat_id]
    
    client = Client(f"session_{chat_id}", api_id=data['api_id'], api_hash=data['api_hash'])
    await client.connect()
    
    try:
        await client.check_password(data['password'])
        session_string = await client.export_session_string()
        send_success(chat_id, session_string)
    except Exception as e:
        bot.send_message(chat_id, f"❌ **Password salah:**\n`{e}`\n\nSilakan tekan /start untuk mengulang.", parse_mode="Markdown")
    finally:
        await client.disconnect()
        clean_up(chat_id)

def send_success(chat_id, session_string):
    teks = (
        "🎉 **BERHASIL!** 🎉\n\n"
        "Berikut adalah **Session String** Anda. Salin seluruh teks di bawah ini:\n\n"
        f"`{session_string}`\n\n"
        "⚠️ **PERINGATAN KERAS:**\n"
        "Ini adalah kunci utama akun Telegram Anda. JANGAN DIBAGIKAN kepada siapa pun. Segera masukkan ke dalam rahasia (Secrets) GitHub Anda."
    )
    bot.send_message(chat_id, teks, parse_mode="Markdown")

def clean_up(chat_id):
    # Membersihkan file session fisik agar server tetap aman dan rapi
    session_file = f"session_{chat_id}.session"
    journal_file = f"session_{chat_id}.session-journal"
    if os.path.exists(session_file):
        os.remove(session_file)
    if os.path.exists(journal_file):
        os.remove(journal_file)

bot.polling(none_stop=True)
