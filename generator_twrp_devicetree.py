import os
import shutil
import subprocess
import requests
import random
import string
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ==============================================================================
# KONFIGURASI ENVIRONMENT VARIABLES
# ==============================================================================
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BP_TOKEN= os.environ.get("BP_TOKEN", "")       
SESSION_STRING = os.environ.get("SESSION_STRING", "") 
GITHUB_USERNAME = os.environ.get("GH_USERNAME", "")
GITHUB_TOKEN = os.environ.get("GH_TOKEN", "")

# HANYA SATU GRUP INI YANG DIIZINKAN (Grup Tester Anda)
ALLOWED_GROUP_IDS = [-1003760536755]

USER_STATE = {}
PORT_MEMORY = {}

# ==============================================================================
# INISIALISASI KLIEN
# ==============================================================================
bot_ui = Client(
    "bot_ui_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bp_token=BP_TOKEN,
    in_memory=True
)

userbot_worker = Client(
    "userbot_session",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING,
    in_memory=True
)

# ==============================================================================
# HANDLER: BOT UI (Tombol Interaktif)
# ==============================================================================
@bot_ui.on_message(filters.command(["dt", "start"], prefixes=["/", ".", "!"]))
async def start_menu(client, message):
    chat_id = message.chat.id
    
    # Validasi ketat: Abaikan jika dari grup lain
    if message.chat.type in ["supergroup", "group"] and chat_id not in ALLOWED_GROUP_IDS:
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛠️ TWRP DT (Android 8 - 11)", callback_data="menu_twrp")],
        [InlineKeyboardButton("🚀 AOSP DT (Android 12+ GKI)", callback_data="menu_aosp")],
        [InlineKeyboardButton("🔄 Auto TWRP Porter", callback_data="menu_port")]
    ])
    
    teks = (
        "🤖 **TWRP/AOSP Studio (Dual-Engine)**\n\n"
        "Silakan pilih mode operasi yang ingin Anda gunakan:"
    )
    await message.reply_text(teks, reply_markup=keyboard)

@bot_ui.on_callback_query()
async def button_handler(client, callback_query):
    user_id = callback_query.from_user.id
    data = callback_query.data

    if data == "menu_twrp":
        USER_STATE[user_id] = "twrp"
        await callback_query.message.edit_text(
            "🛠️ **Mode: TWRP Device Tree**\n\n"
            "🟢 *Akses dibuka. Silakan kirim file `boot.img` atau `recovery.img` Anda sekarang.*"
        )
    elif data == "menu_aosp":
        USER_STATE[user_id] = "aosp"
        await callback_query.message.edit_text(
            "🚀 **Mode: AOSP Device Tree**\n\n"
            "🟢 *Akses dibuka. Silakan kirim file `vendor_boot.img` atau `init_boot.img` Anda sekarang.*"
        )
    elif data == "menu_port":
        USER_STATE[user_id] = "port_step1"
        await callback_query.message.edit_text(
            "🔄 **Mode: Auto TWRP Porter**\n\n"
            "🟢 **Langkah 1:** *Silakan kirimkan file STOCK RECOVERY Anda terlebih dahulu.*"
        )

# ==============================================================================
# HANDLER: USERBOT WORKER (Menyambar File Dokumen)
# ==============================================================================
@userbot_worker.on_message(filters.document)
async def handle_document(client, message):
    chat_id = message.chat.id
    
    # Mutlak abaikan pesan dokumen dari luar grup yang diizinkan untuk mencegah error peer
    if chat_id not in ALLOWED_GROUP_IDS:
        return

    user_id = message.from_user.id if message.from_user else None
    if not user_id or user_id not in USER_STATE:
        return 

    state = USER_STATE[user_id]
    file_name = message.document.file_name or ""
    
    if not file_name.lower().endswith('.img'):
        return

    msg = await message.reply_text("⏳ **Userbot menyambar file Anda...**")

    # MODE GENERATOR (TWRP / AOSP)
    if state in ["twrp", "aosp"]:
        USER_STATE.pop(user_id, None) 
        engine = "twrpdtgen" if state == "twrp" else "aospdtgen"
        
        rand_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        work_dir = f"workspace_{rand_id}"
        os.makedirs(work_dir, exist_ok=True)
        
        file_path = await client.download_media(message, file_name=f"{work_dir}/source.img")
        await msg.edit_text(f"⚙️ **Userbot mengekstrak via `{engine}`...**")
        
        output_dir = os.path.join(work_dir, "output")
        result = subprocess.run(["python3", "-m", engine, file_path, "-o", output_dir], capture_output=True, text=True)
        
        if result.returncode != 0:
            await msg.edit_text(f"❌ **Userbot Gagal Ekstraksi!**\n`{result.stderr[:500]}`")
            shutil.rmtree(work_dir, ignore_errors=True)
            return
            
        await msg.edit_text("✅ **Userbot Berhasil mengekstrak Device Tree!**")
        shutil.rmtree(work_dir, ignore_errors=True)

    # MODE PORTING (LANGKAH 1)
    elif state == "port_step1":
        rand_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        work_dir = f"port_workspace_{rand_id}"
        os.makedirs(work_dir, exist_ok=True)
        
        stock_path = await client.download_media(message, file_name=f"{work_dir}/stock_recovery.img")
        PORT_MEMORY[user_id] = stock_path
        USER_STATE[user_id] = "port_step2"
        
        await msg.edit_text("✅ **Stock Recovery Diterima!**\n\n🟢 **Langkah 2:** *Sekarang kirim file PORT RECOVERY.*")

    # MODE PORTING (LANGKAH 2)
    elif state == "port_step2":
        stock_path = PORT_MEMORY.pop(user_id, None)
        USER_STATE.pop(user_id, None)
        
        work_dir = os.path.dirname(stock_path)
        port_path = await client.download_media(message, file_name=f"{work_dir}/port_recovery.img")
        
        await msg.edit_text("⚙️ **Menjalankan Auto Porter...**")

        port_result = subprocess.run(["bash", "porter.sh", stock_path, port_path, work_dir], capture_output=True, text=True)

        if port_result.returncode == 0:
            output_img = f"{work_dir}/twrp_ported.img"
            if os.path.exists(output_img):
                await msg.edit_text("✅ **Porting Berhasil! Mengirim file hasil...**")
                await client.send_document(chat_id=message.chat.id, document=output_img)
            else:
                await msg.edit_text("❌ Proses selesai tapi file output `twrp_ported.img` tidak ditemukan.")
        else:
            await msg.edit_text(f"❌ **Porting Gagal!**\n`{port_result.stderr[:500]}`")
            
        shutil.rmtree(work_dir, ignore_errors=True)

# ==============================================================================
# MAIN RUNNER
# ==============================================================================
async def main():
    print("Menghidupkan Bot UI & Userbot Worker...")
    await bot_ui.start()
    await userbot_worker.start()
    print("Kedua Client Berhasil Online dan Standby!")
    
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot dihentikan.")
