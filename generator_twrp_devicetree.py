import os
import shutil
import subprocess
import random
import string
import asyncio
import sys
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ==============================================================================
# KONFIGURASI & LOGGING REALTIME
# ==============================================================================
def log(message):
    """Fungsi cetak log real-time dengan flush agar langsung muncul di console GitHub"""
    print(f"[LOG] {message}", flush=True)

log("Memulai skrip dan membaca Environment Variables...")

API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BP_TOKEN = os.environ.get("BP_TOKEN", "")       
SESSION_STRING = os.environ.get("SESSION_STRING", "") 
GH_USERNAME = os.environ.get("GH_USERNAME", "")
GH_TOKEN = os.environ.get("GH_TOKEN", "")

log(f"Config terdeteksi -> API_ID: {API_ID} | BP_TOKEN length: {len(BP_TOKEN)} | SESSION length: {len(SESSION_STRING)}")

USER_STATE = {}
PORT_MEMORY = {}

# ==============================================================================
# INISIALISASI DUAL-CLIENT
# ==============================================================================
log("Menginisialisasi klien Pyrogram...")

bot_ui = Client(
    "bot_ui_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BP_TOKEN,
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
# HANDLER: BOT UI
# ==============================================================================
@bot_ui.on_message(filters.command(["dt", "start"], prefixes=["/", ".", "!"]))
async def start_menu(client, message):
    log(f"EVENT: Menerima perintah /start atau /dt dari user ID: {message.from_user.id if message.from_user else 'Unknown'}")
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
    log("RESPONS: Menu utama berhasil dikirim ke Telegram.")

@bot_ui.on_callback_query()
async def button_handler(client, callback_query):
    user_id = callback_query.from_user.id
    data = callback_query.data
    log(f"EVENT CALLBACK: User {user_id} memilih tombol -> {data}")

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
# HANDLER: USERBOT WORKER
# ==============================================================================
@userbot_worker.on_message(filters.document)
async def handle_document(client, message):
    try:
        user_id = message.from_user.id if message.from_user else None
        log(f"USERBOT MENANGKAP DOKUMEN dari user ID: {user_id}")
        
        if not user_id or user_id not in USER_STATE:
            log("DIABAIKAN: User tidak memiliki state aktif (belum klik menu).")
            return 

        state = USER_STATE[user_id]
        file_name = message.document.file_name or ""
        log(f"STATE USER: {state} | Nama File: {file_name}")
        
        if not file_name.lower().endswith('.img'):
            log("DIABAIKAN: File yang dikirim bukan format .img")
            return

        msg = await message.reply_text("⏳ **Userbot menyambar file Anda...**")

        if state in ["twrp", "aosp"]:
            USER_STATE.pop(user_id, None) 
            engine = "twrpdtgen" if state == "twrp" else "aospdtgen"
            
            rand_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
            work_dir = f"workspace_{rand_id}"
            os.makedirs(work_dir, exist_ok=True)
            
            log(f"Mendownload file ke {work_dir}/source.img ...")
            file_path = await client.download_media(message, file_name=f"{work_dir}/source.img")
            await msg.edit_text(f"⚙️ **Userbot mengekstrak via `{engine}`...**")
            
            output_dir = os.path.join(work_dir, "output")
            log(f"Menjalankan subprocess: python3 -m {engine}")
            result = subprocess.run(["python3", "-m", engine, file_path, "-o", output_dir], capture_output=True, text=True)
            
            if result.returncode != 0:
                log(f"GAGAL EKSTRAKSI: {result.stderr[:300]}")
                await msg.edit_text(f"❌ **Userbot Gagal Ekstraksi!**\n`{result.stderr[:500]}`")
                shutil.rmtree(work_dir, ignore_errors=True)
                return
                
            log("SUKSES EKSTRAKSI! Membersihkan workspace...")
            await msg.edit_text("✅ **Userbot Berhasil mengekstrak Device Tree!**")
            shutil.rmtree(work_dir, ignore_errors=True)

        elif state == "port_step1":
            rand_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
            work_dir = f"port_workspace_{rand_id}"
            os.makedirs(work_dir, exist_ok=True)
            
            log(f"Mendownload Stock Recovery ke {work_dir}/stock_recovery.img ...")
            stock_path = await client.download_media(message, file_name=f"{work_dir}/stock_recovery.img")
            PORT_MEMORY[user_id] = stock_path
            USER_STATE[user_id] = "port_step2"
            
            await msg.edit_text("✅ **Stock Recovery Diterima!**\n\n🟢 **Langkah 2:** *Sekarang kirim file PORT RECOVERY.*")

        elif state == "port_step2":
            stock_path = PORT_MEMORY.pop(user_id, None)
            USER_STATE.pop(user_id, None)
            
            work_dir = os.path.dirname(stock_path)
            log(f"Mendownload Port Recovery ke {work_dir}/port_recovery.img ...")
            port_path = await client.download_media(message, file_name=f"{work_dir}/port_recovery.img")
            
            await msg.edit_text("⚙️ **Menjalankan Auto Porter...**")
            log("Menjalankan script porter.sh ...")

            port_result = subprocess.run(["bash", "porter.sh", stock_path, port_path, work_dir], capture_output=True, text=True)

            if port_result.returncode == 0:
                output_img = f"{work_dir}/twrp_ported.img"
                if os.path.exists(output_img):
                    log("PORTING BERHASIL! Mengirim file hasil ke chat...")
                    await msg.edit_text("✅ **Porting Berhasil! Mengirim file hasil...**")
                    await client.send_document(chat_id=message.chat.id, document=output_img)
                else:
                    log("GAGAL: Output file twrp_ported.img tidak ditemukan.")
                    await msg.edit_text("❌ Proses selesai tapi file output `twrp_ported.img` tidak ditemukan.")
            else:
                log(f"GAGAL PORTER: {port_result.stderr[:300]}")
                await msg.edit_text(f"❌ **Porting Gagal!**\n`{port_result.stderr[:500]}`")
                
            shutil.rmtree(work_dir, ignore_errors=True)
            
    except Exception as e:
        log(f"ERROR KRITIS PADA HANDLER DOKUMEN: {e}")

# ==============================================================================
# MAIN RUNNER
# ==============================================================================
async def main():
    log("Menghidupkan Bot UI...")
    await bot_ui.start()
    log("Bot UI Berhasil Online!")

    log("Menghidupkan Userbot Worker...")
    await userbot_worker.start()
    log("Userbot Worker Berhasil Online!")
    
    log("Semua klien aktif. Memasuki status idle (mendengarkan event realtime)...")
    await idle()
    
    log("Mematikan klien secara aman...")
    await bot_ui.stop()
    await userbot_worker.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log("Program dihentikan secara manual oleh pengguna.")
