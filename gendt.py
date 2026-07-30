import os
import shutil
import subprocess
import requests
import glob
import random
import string
from pyrogram import Client, filters

# ==============================================================================
# KONFIGURASI ENVIRONMENT VARIABLES
# ==============================================================================
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
SESSION_STRING = os.environ.get("SESSION_STRING")
GITHUB_USERNAME = os.environ.get("GH_USERNAME")
GITHUB_TOKEN = os.environ.get("GH_TOKEN")

# ==============================================================================
# PENGATURAN GRUP & SESI USER
# ==============================================================================
ALLOWED_GROUP_IDS = [
    -1003503670594 # <-- ID Grup utama Anda
]

ACTIVE_USERS = set()

app = Client(
    "twrp_userbot",
    session_string=SESSION_STRING,
    api_id=API_ID,
    api_hash=API_HASH
)

# ==============================================================================
# HANDLER: PERINTAH BUKA GERBANG (/dt)
# ==============================================================================
@app.on_message(filters.command(["dt", "dt_twrp"], prefixes=["/", ".", "#"]))
async def start(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if message.chat.type in ["supergroup", "group"] and ALLOWED_GROUP_IDS and chat_id not in ALLOWED_GROUP_IDS:
        return

    ACTIVE_USERS.add(user_id)

    teks = (
        "🤖 **Generator Device Tree (Auto-Pilot Mode)**\n\n"
        "Kirimkan file partisi `.img` Anda sekarang tanpa *caption*.\n"
        "Sistem akan otomatis mendeteksi jenis file (Boot/Vendor Boot) dan memilih *engine* ekstraktor terbaik (`twrpdtgen` atau `aospdtgen`) secara dinamis.\n\n"
        f"🟢 **Akses untuk {message.from_user.mention} telah dibuka!**"
    )
    await message.reply_text(teks)

# ==============================================================================
# HANDLER: DETEKSI & PROSES FILE OTOMATIS
# ==============================================================================
@app.on_message(filters.document & (filters.private | filters.group))
async def handle_document(client, message):
    chat_id = message.chat.id
    chat_type = message.chat.type
    user_id = message.from_user.id

    if chat_type in ["supergroup", "group"]:
        if ALLOWED_GROUP_IDS and chat_id not in ALLOWED_GROUP_IDS:
            return

    if user_id not in ACTIVE_USERS:
        return 

    file_name = message.document.file_name or ""
    if not file_name.lower().endswith('.img'):
        return

    # Kunci gerbang
    ACTIVE_USERS.remove(user_id)

    msg = await message.reply_text("⏳ **File diterima!**\nMemulai unduhan...")

    rand_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    work_dir = f"workspace_{rand_id}"
    
    try:
        os.makedirs(work_dir, exist_ok=True)
        file_path = await client.download_media(message, file_name=f"{work_dir}/source.img")

        # ----------------------------------------------------------------------
        # 1. BACA MAGIC HEADER UNTUK MENENTUKAN PRIORITAS ENGINE
        # ----------------------------------------------------------------------
        with open(file_path, "rb") as f:
            magic_header = f.read(8)
            
        if magic_header.startswith(b"VNDRBOOT"):
            img_type_label = "Vendor Boot (GKI / Android 12+)"
            engines_to_try = ["aospdtgen", "twrpdtgen"] # Prioritaskan AOSP
        elif magic_header.startswith(b"ANDROID!"):
            img_type_label = "Boot / Recovery (Standar)"
            engines_to_try = ["twrpdtgen", "aospdtgen"] # Prioritaskan TWRP
        else:
            img_type_label = "Format Tidak Dikenal"
            engines_to_try = ["twrpdtgen", "aospdtgen"]

        await msg.edit_text(f"⚙️ **Menganalisis File...**\n🔍 **Tipe Image:** `{img_type_label}`")

        output_dir = os.path.join(work_dir, "output")
        
        # ----------------------------------------------------------------------
        # 2. AUTO-PILOT EXECUTION (SMART FALLBACK)
        # ----------------------------------------------------------------------
        extraction_success = False
        used_engine = ""
        error_logs = ""

        for engine in engines_to_try:
            await msg.edit_text(f"⚙️ **Mengekstrak File...**\n🔍 **Tipe Image:** `{img_type_label}`\n⚡ **Mencoba Engine:** `{engine}`...")
            
            # Pastikan folder output bersih untuk setiap percobaan
            if os.path.exists(output_dir):
                shutil.rmtree(output_dir)
            os.makedirs(output_dir, exist_ok=True)
            
            result = subprocess.run(["python3", "-m", engine, file_path, "-o", output_dir], capture_output=True, text=True)
            
            if result.returncode == 0:
                extraction_success = True
                used_engine = engine
                break # Sukses! Hentikan loop percobaan
            else:
                error_logs += f"\n**[{engine} Error]:**\n`{result.stderr[:200]}...`\n"

        # Jika semua engine gagal
        if not extraction_success:
            await msg.edit_text(f"❌ **Gagal mengekstrak file dengan semua *engine* yang tersedia!**\n{error_logs}")
            return

        # ----------------------------------------------------------------------
        # 3. BACA OUTPUT DAN PARSING DATA
        # ----------------------------------------------------------------------
        manufacturers = os.listdir(output_dir)
        if not manufacturers:
            raise Exception("Folder output kosong meskipun ekstraksi dilaporkan sukses.")
        manufacturer = manufacturers[0]
        
        codenames = os.listdir(os.path.join(output_dir, manufacturer))
        if not codenames:
            raise Exception("Tidak dapat menemukan codename perangkat di struktur output.")
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

        # Prefix penamaan berdasarkan engine yang berhasil
        prefix_name = "aosp" if "aosp" in used_engine else "twrp"
        custom_img_name = f'{prefix_name}-{product_model}-{build_desc}-{build_fingerprint}.img'.replace(':', '_')
        final_workspace_img_path = os.path.join(work_dir, custom_img_name)
        
        os.replace(file_path, final_workspace_img_path)

        repo_name = f"android_device_{manufacturer}_{codename}_{prefix_name}"
        
        await msg.edit_text(f"✅ **Ekstraksi berhasil via `{used_engine}`!**\n🚀 Mengunggah ke GitHub `@{GITHUB_USERNAME}`...")

        # ----------------------------------------------------------------------
        # 4. UNGGAH KE GITHUB
        # ----------------------------------------------------------------------
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

if __name__ == "__main__":
    print("Userbot Generator Auto-Pilot Mode Menyala!")
    app.run()
