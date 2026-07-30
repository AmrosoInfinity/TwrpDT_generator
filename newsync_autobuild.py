import os
import shutil
import subprocess
import requests
import glob
import random
import string
import asyncio
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ==============================================================================
# KONFIGURASI ENVIRONMENT VARIABLES & PRINT DEBUG MENTAH
# ==============================================================================
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BP_TOKEN = os.environ.get("BP_TOKEN", "")       
SESSION_STRING = os.environ.get("SESSION_STRING", "") 
GITHUB_USERNAME = os.environ.get("GH_USERNAME", "")
GITHUB_TOKEN = os.environ.get("GH_TOKEN", "")

# Print full debug mentah untuk memastikan secret terbaca di GitHub Actions
print(f"DEBUG MENTAH BP_TOKEN (Full): '{BP_TOKEN}'", flush=True)
print(f"DEBUG MENTAH API_ID: '{API_ID}'", flush=True)
print(f"DEBUG MENTAH SESSION_STRING (15 char awal): '{SESSION_STRING[:15]}...'", flush=True)

ALLOWED_GROUP_IDS = [
    -1003503670594,
    -1003760536755
]

USER_STATE = {}
PORT_MEMORY = {}

# ==============================================================================
# INISIALISASI DUAL-CLIENT (BOT UI & USERBOT WORKER)
# ==============================================================================
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
# HANDLER: BOT UI (Menampilkan Tombol Pilihan Menu & Porting)
# ==============================================================================
@bot_ui.on_message(filters.command(["dt", "dt_twrp", "start"], prefixes=["/", ".", "#"]))
async def start_menu(client, message):
    chat_id = message.chat.id
    
    if message.chat.type in ["supergroup", "group"] and ALLOWED_GROUP_IDS and chat_id not in ALLOWED_GROUP_IDS:
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🤖 Auto-Pilot (Smart DT Detection)", callback_data="mode_autopilot")],
        [InlineKeyboardButton("🛠️ Force TWRP DT", callback_data="mode_twrp"),
         InlineKeyboardButton("🚀 Force AOSP DT", callback_data="mode_aosp")],
        [InlineKeyboardButton("🔄 Auto TWRP Porter", callback_data="mode_port")]
    ])
    
    teks = (
        "🤖 **TWRP/AOSP Studio (Dual-Engine Mode)**\n\n"
        "Silakan pilih mode operasi yang ingin Anda gunakan:"
    )
    await message.reply_text(teks, reply_markup=keyboard)

@bot_ui.on_callback_query()
async def button_handler(client, callback_query):
    user_id = callback_query.from_user.id
    data = callback_query.data

    if data == "mode_autopilot":
        USER_STATE[user_id] = "autopilot"
        await callback_query.message.edit_text("✅ **Mode:** `Auto-Pilot DT`\n\n🟢 *Gerbang terbuka! Silakan kirim file partisi `.img` Anda.*")
    elif data == "mode_twrp":
        USER_STATE[user_id] = "twrp"
        await callback_query.message.edit_text("✅ **Mode:** `Force TWRP DT`\n\n🟢 *Gerbang terbuka! Silakan kirim file partisi `.img` Anda.*")
    elif data == "mode_aosp":
        USER_STATE[user_id] = "aosp"
        await callback_query.message.edit_text("✅ **Mode:** `Force AOSP DT`\n\n🟢 *Gerbang terbuka! Silakan kirim file partisi `.img` Anda.*")
    elif data == "mode_port":
        USER_STATE[user_id] = "port_step1"
        await callback_query.message.edit_text("🔄 **Mode: Auto TWRP Porter**\n\n🟢 **Langkah 1:** *Silakan kirimkan file STOCK RECOVERY Anda terlebih dahulu.*")

# ==============================================================================
# HANDLER: USERBOT WORKER (Eksekusi Device Tree & Auto Porter)
# ==============================================================================
@userbot_worker.on_message(filters.document & (filters.private | filters.group))
async def handle_document(client, message):
    user_id = message.from_user.id if message.from_user else None

    if not user_id or user_id not in USER_STATE:
        return 

    chat_id = message.chat.id
    if ALLOWED_GROUP_IDS and chat_id not in ALLOWED_GROUP_IDS and message.chat.type != "private":
        return

    file_name = message.document.file_name or ""
    if not file_name.lower().endswith('.img'):
        return

    current_state = USER_STATE.get(user_id)

    # --------------------------------------------------------------------------
    # LOGIKA PORTING (LANGKAH 1: STOCK RECOVERY)
    # --------------------------------------------------------------------------
    if current_state == "port_step1":
        rand_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        work_dir = f"port_workspace_{rand_id}"
        os.makedirs(work_dir, exist_ok=True)
        
        msg = await message.reply_text("⏳ Mendownload Stock Recovery...")
        stock_path = await client.download_media(message, file_name=f"{work_dir}/stock_recovery.img")
        
        PORT_MEMORY[user_id] = stock_path
        USER_STATE[user_id] = "port_step2"
        await msg.edit_text("✅ **Stock Recovery Diterima!**\n\n🟢 **Langkah 2:** *Sekarang kirim file PORT RECOVERY.*")
        return

    # --------------------------------------------------------------------------
    # LOGIKA PORTING (LANGKAH 2: PORT RECOVERY & EKSEKUSI PORTER.SH)
    # --------------------------------------------------------------------------
    elif current_state == "port_step2":
        stock_path = PORT_MEMORY.pop(user_id, None)
        USER_STATE.pop(user_id, None)
        
        if not stock_path or not os.path.exists(stock_path):
            await message.reply_text("❌ Sesi porting kedaluwarsa atau file Stock hilang. Ulangi dari awal lewat /dt.")
            return

        work_dir = os.path.dirname(stock_path)
        msg = await message.reply_text("⏳ Mendownload Port Recovery...")
        port_path = await client.download_media(message, file_name=f"{work_dir}/port_recovery.img")
        
        await msg.edit_text("⚙️ **Menjalankan Auto TWRP Porter (`porter.sh`)...**")

        port_result = subprocess.run(["bash", "porter.sh", stock_path, port_path, work_dir], capture_output=True, text=True)

        if port_result.returncode == 0:
            output_img = f"{work_dir}/twrp_ported.img"
            if os.path.exists(output_img):
                await msg.edit_text("✅ **Porting Berhasil! Mengirim file hasil ke chat...**")
                await client.send_document(chat_id=message.chat.id, document=output_img)
            else:
                await msg.edit_text("❌ Proses selesai tapi file output `twrp_ported.img` tidak ditemukan.")
        else:
            await msg.edit_text(f"❌ **Porting Gagal!**\n`{port_result.stderr[:500]}`")
            
        shutil.rmtree(work_dir, ignore_errors=True)
        return

    # --------------------------------------------------------------------------
    # LOGIKA GENERATOR DEVICE TREE (TWRP / AOSP / AUTOPILOT)
    # --------------------------------------------------------------------------
    selected_mode = USER_STATE.pop(user_id, "autopilot")
    msg = await message.reply_text("⏳ **File diterima oleh Userbot!**\nMemulai unduhan...")

    rand_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    work_dir = f"workspace_{rand_id}"
    
    try:
        os.makedirs(work_dir, exist_ok=True)
        file_path = await client.download_media(message, file_name=f"{work_dir}/source.img")

        with open(file_path, "rb") as f:
            magic_header = f.read(8)
            
        if magic_header.startswith(b"VNDRBOOT"):
            img_type_label = "Vendor Boot (GKI / Android 12+)"
        elif magic_header.startswith(b"ANDROID!"):
            img_type_label = "Boot / Recovery (Standar)"
        else:
            img_type_label = "Format Tidak Dikenal"

        if selected_mode == "twrp":
            engines_to_try = ["twrpdtgen", "aospdtgen"]
        elif selected_mode == "aosp":
            engines_to_try = ["aospdtgen", "twrpdtgen"]
        else:
            if magic_header.startswith(b"VNDRBOOT"):
                engines_to_try = ["aospdtgen", "twrpdtgen"]
            else:
                engines_to_try = ["twrpdtgen", "aospdtgen"]

        await msg.edit_text(f"⚙️ **Menganalisis File...**\n🔍 **Tipe Image:** `{img_type_label}`")

        output_dir = os.path.join(work_dir, "output")
        extraction_success = False
        used_engine = ""
        error_logs = ""

        for engine in engines_to_try:
            await msg.edit_text(f"⚙️ **Mengekstrak File...**\n🔍 **Tipe:** `{img_type_label}`\n⚡ **Engine:** `{engine}`...")
            
            if os.path.exists(output_dir):
                shutil.rmtree(output_dir)
            os.makedirs(output_dir, exist_ok=True)
            
            result = subprocess.run(["python3", "-m", engine, file_path, "-o", output_dir], capture_output=True, text=True)
            
            if result.returncode == 0:
                extraction_success = True
                used_engine = engine
                break
            else:
                error_logs += f"\n**[{engine} Error]:**\n`{result.stderr[:200]}...`\n"

        if not extraction_success:
            await msg.edit_text(f"❌ **Gagal mengekstrak file dengan semua engine!**\n{error_logs}")
            return

        manufacturers = os.listdir(output_dir)
        if not manufacturers:
            raise Exception("Folder output kosong meskipun ekstraksi dilaporkan sukses.")
        manufacturer = manufacturers[0]
        
        codenames = os.listdir(os.path.join(output_dir, manufacturer))
        if not codenames:
            raise Exception("Tidak dapat menemukan codename perangkat.")
        codename = codenames[0]

        device_tree_path = os.path.join(output_dir, manufacturer, codename)

        product_model = "unknown_model"
        build_desc = "unknown_desc"
        build_fingerprint = "unknown_fingerprint"

        mk_files = glob.glob(f"{device_tree_path}/*.mk")
        for mk in mk_files:
            with open(mk, 'r', errors='ignore') as f:
                content = f.read()
                for line in content.split('\n'):
                    if "PRODUCT_MODEL :=" in line or "PRODUCT_MODEL =" in line:
                        product_model = line.split('=', 1)[1].strip().replace('"', '').replace(' ', '_')
                    elif "PRIVATE_BUILD_DESC" in line and "=" in line:
                        build_desc = line.split('=', 1)[1].replace('"', '').replace("'", "").strip().replace(' ', '_')
                    elif "BUILD_FINGERPRINT" in line and "=" in line:
                        build_fingerprint = line.split('=', 1)[1].replace('"', '').replace("'", "").strip().replace('/', '_').replace(' ', '_')

        prefix_name = "aosp" if "aosp" in used_engine else "twrp"
        custom_img_name = f'{prefix_name}-{product_model}-{build_desc}-{build_fingerprint}.img'.replace(':', '_')
        final_workspace_img_path = os.path.join(work_dir, custom_img_name)
        
        os.replace(file_path, final_workspace_img_path)
        repo_name = f"android_device_{manufacturer}_{codename}_{prefix_name}"
        
        await msg.edit_text(f"✅ **Ekstraksi sukses via `{used_engine}`!**\n🚀 Mengunggah ke GitHub `@{GITHUB_USERNAME}`...")

        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        repo_data = {
            "name": repo_name,
            "description": f"{prefix_name.upper()} Device Tree for {codename} (Auto-generated via {used_engine})",
            "private": False
        }
        
        req = requests.post("https://api.github.com/user/repos", json=repo_data, headers=headers)
        if req.status_code not in [201, 422]:
            raise Exception(f"Gagal membuat repositori GitHub:\n{req.text}")

        subprocess.run(["git", "config", "--global", "user.email", "userbot@generator.local"])
        subprocess.run(["git", "config", "--global", "user.name", "Userbot Auto-Generator"])
        
        os.chdir(device_tree_path)
        subprocess.run(["git", "init"])
        subprocess.run(["git", "add", "."])
        subprocess.run(["git", "commit", "-m", f"Initial commit: {prefix_name.upper()} device tree for {codename} ({product_model})"])
        subprocess.run(["git", "branch", "-M", "main"])
        
        remote_url = f"https://{GITHUB_USERNAME}:{GITHUB_TOKEN}@github.com/{GITHUB_USERNAME}/{repo_name}.git"
        subprocess.run(["git", "remote", "add", "origin", remote_url])
        subprocess.run(["git", "push", "-u", "origin", "main", "--force"])
        
        os.chdir("../../..")

        github_link = f"https://github.com/{GITHUB_USERNAME}/{repo_name}/tree/main"
        
        final_text = (
            f"✅ **Device Tree Generated Successfully!**\n\n"
            f"📱 **Model:** `{product_model}`\n"
            f"📟 **Codename:** `{codename}`\n"
            f"🔍 **Tipe File:** `{img_type_label}`\n"
            f"⚙️ **Engine Sukses:** `{used_engine}`\n\n"
            f"🏷️ **Custom Filename:**\n`{custom_img_name}`\n\n"
            f"🔗 **Repository:** {github_link}"
        )
        
        await msg.edit_text(final_text, disable_web_page_preview=True)

    except Exception as e:
        await msg.edit_text(f"❌ **Terjadi kesalahan sistem:**\n`{str(e)}`")
    
    finally:
        if os.path.exists(work_dir):
            shutil.rmtree(work_dir, ignore_errors=True)

# ==============================================================================
# MAIN RUNNER
# ==============================================================================
async def main():
    print("Menghidupkan Dual-Client (Bot UI & Userbot Worker)...", flush=True)
    
    await asyncio.gather(
        bot_ui.start(),
        userbot_worker.start()
    )
    
    print("Dual-Client Berhasil Online dan Standby!", flush=True)

    # Sinkronisasi cache peer grup agar aman dari error "Peer id invalid"
    for gid in ALLOWED_GROUP_IDS:
        try:
            await userbot_worker.get_chat(gid)
        except Exception:
            pass

    await idle()
    
    print("Mematikan klien...", flush=True)
    await bot_ui.stop()
    await userbot_worker.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot dihentikan.")
