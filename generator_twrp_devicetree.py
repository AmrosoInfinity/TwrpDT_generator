import os
import shutil
import subprocess
import requests
import random
import string
import asyncio
from pyrogram import Client, filters, compose
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ==============================================================================
# KONFIGURASI ENVIRONMENT VARIABLES
# ==============================================================================
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")       # Untuk UI Tombol
SESSION_STRING = os.environ.get("SESSION_STRING", "") # Untuk bypass limit 20MB
GITHUB_USERNAME = os.environ.get("GH_USERNAME", "")
GITHUB_TOKEN = os.environ.get("GH_TOKEN", "")

ALLOWED_GROUP_IDS = [-1003503670594,-1003760536755] # ID Grup tempat Bot & Userbot berkumpul

# ==============================================================================
# STATE MACHINE (Memori Bersama antara Bot dan Userbot)
# ==============================================================================
USER_STATE = {}
PORT_MEMORY = {}

# ==============================================================================
# INISIALISASI DUAL-CLIENT
# ==============================================================================
# 1. Klien Bot (Tukang Pamer UI)
bot_ui = Client("bot_ui", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# 2. Klien Userbot (Tukang Kerja Kasar)
userbot_worker = Client("userbot_worker", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)

# ==============================================================================
# HANDLER: BOT UI (Menampilkan Tombol)
# ==============================================================================
@bot_ui.on_message(filters.command(["dt"]) & filters.group)
async def start_menu(client, message):
    if ALLOWED_GROUP_IDS and message.chat.id not in ALLOWED_GROUP_IDS:
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
            "🟢 *Akses Userbot dibuka. Silakan kirim `boot.img` atau `recovery.img` Anda sekarang.*"
        )
    elif data == "menu_aosp":
        USER_STATE[user_id] = "aosp"
        await callback_query.message.edit_text(
            "🚀 **Mode: AOSP Device Tree**\n\n"
            "🟢 *Akses Userbot dibuka. Silakan kirim `vendor_boot.img` atau `init_boot.img` Anda sekarang.*"
        )
    elif data == "menu_port":
        USER_STATE[user_id] = "port_step1"
        await callback_query.message.edit_text(
            "🔄 **Mode: Auto TWRP Porter**\n\n"
            "🟢 **Langkah 1:** *Silakan kirimkan file STOCK RECOVERY Anda terlebih dahulu.*"
        )

# ==============================================================================
# HANDLER: USERBOT WORKER (Menyambar File & Mengeksekusi)
# ==============================================================================
@userbot_worker.on_message(filters.document & filters.group)
async def handle_document(client, message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if ALLOWED_GROUP_IDS and chat_id not in ALLOWED_GROUP_IDS:
        return

    # Cek memori bersama, apakah user ini sudah menekan tombol di Bot UI?
    if user_id not in USER_STATE:
        return 

    state = USER_STATE[user_id]
    file_name = message.document.file_name or ""
    
    if not file_name.lower().endswith('.img'):
        return

    msg = await message.reply_text("⏳ **Userbot menyambar file Anda...**")

    # ---------------------------------------------------------
    # MODE GENERATOR (TWRP / AOSP)
    # ---------------------------------------------------------
    if state in ["twrp", "aosp"]:
        USER_STATE.pop(user_id) # Kunci gerbang
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
            
        await msg.edit_text("✅ **Userbot Berhasil!**\nSilakan integrasikan logika GitHub Anda di sini.")
        shutil.rmtree(work_dir, ignore_errors=True)

    # ---------------------------------------------------------
    # MODE PORTING
    # ---------------------------------------------------------
    elif state == "port_step1":
        rand_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        work_dir = f"port_workspace_{rand_id}"
        os.makedirs(work_dir, exist_ok=True)
        
        stock_path = await client.download_media(message, file_name=f"{work_dir}/stock_recovery.img")
        PORT_MEMORY[user_id] = stock_path
        USER_STATE[user_id] = "port_step2"
        
        await msg.edit_text("✅ **Userbot menerima Stock Recovery!**\n\n🟢 **Langkah 2:** *Silakan kirim PORT RECOVERY.*")

    elif state == "port_step2":
        stock_path = PORT_MEMORY.pop(user_id)
        USER_STATE.pop(user_id)
        
        work_dir = os.path.dirname(stock_path)
        port_path = await client.download_media(message, file_name=f"{work_dir}/port_recovery.img")
        
        await msg.edit_text("⚙️ **Userbot menjalankan Auto Porter...**")

        # Panggil script porting Anda
        port_result = subprocess.run(["bash", "porter.sh", stock_path, port_path, work_dir], capture_output=True, text=True)

        if port_result.returncode == 0:
            output_img = f"{work_dir}/twrp_ported.img"
            if os.path.exists(output_img):
                await msg.edit_text("✅ **Porting Berhasil! Userbot mengunggah hasil...**")
                await client.send_document(chat_id=message.chat.id, document=output_img)
            else:
                await msg.edit_text("❌ Proses selesai tapi file output tidak ditemukan.")
        else:
            await msg.edit_text(f"❌ **Porting Gagal!**\n`{port_result.stderr[:500]}`")
            
        shutil.rmtree(work_dir, ignore_errors=True)

# ==============================================================================
# EKSEKUSI BERSAMAAN (DUAL RUNNER)
# ==============================================================================
async def main():
    print("Dual-Client (Bot UI & Userbot Worker) Menyala Bersamaan!")
    await compose([bot_ui, userbot_worker])

if __name__ == "__main__":
    asyncio.run(main())
