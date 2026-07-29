import os
import shutil
import subprocess
import requests
import glob
import random
import string
from pyrogram import Client, filters

# ==============================================================================
# KONFIGURASI ENVIRONMENT VARIABLES (Dari GitHub Secrets)
# ==============================================================================
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
SESSION_STRING = os.environ.get("SESSION_STRING")
GITHUB_USERNAME = os.environ.get("GH_USERNAME")
GITHUB_TOKEN = os.environ.get("GH_TOKEN")

# ==============================================================================
# PENGATURAN BATASAN GRUP & SESI USER ID DI BALIK LAYAR
# ==============================================================================
ALLOWED_GROUP_IDS = [
    -1003503670594 # <-- ID Grup utama Anda
]

# Set untuk menyimpan User ID yang sedang memegang izin/sesi aktif
ACTIVE_USERS = set()

# ==============================================================================
# INISIALISASI USERBOT
# ==============================================================================
app = Client(
    "twrp_userbot",
    session_string=SESSION_STRING,
    api_id=API_ID,
    api_hash=API_HASH
)

# ==============================================================================
# HANDLER: PERINTAH /dt_twrp (MENANDAI ID USER)
# ==============================================================================
@app.on_message(filters.command("dt_twrp", prefixes=["/", ".", "#"]))
async def start(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if message.chat.type in ["supergroup", "group"] and ALLOWED_GROUP_IDS and chat_id not in ALLOWED_GROUP_IDS:
        return

    # Menandai ID user di balik layar bahwa dia diizinkan mengirim 1 file .img
    ACTIVE_USERS.add(user_id)

    teks = (
        "🤖 **Generator Device Tree TWRP (Access Mode)**\n\n"
        "Sistem ini mengekstrak *Device Tree* TWRP dengan format penamaan kustom secara otomatis!\n\n"
        f"🟢 **Halo `{message.from_user.first_name}`! Akses Anda diaktifkan.**\n"
        "Silakan kirimkan file partisi `.img` Anda sekarang (tanpa caption).\n"
        "*(Sistem hanya akan memproses file dari Anda dan silahkan duduk ngopi dengan santay).* "
    )
    await message.reply_text(teks)

# ==============================================================================
# HANDLER: DETEKSI FILE .IMG BERDASARKAN ID USER
# ==============================================================================
@app.on_message(filters.document & (filters.private | filters.group))
async def handle_document(client, message):
    chat_id = message.chat.id
    chat_type = message.chat.type
    user_id = message.from_user.id

    if chat_type in ["supergroup", "group"]:
        if ALLOWED_GROUP_IDS and chat_id not in ALLOWED_GROUP_IDS:
            return

    # 1. CEK APAKAH USER INI MEMILIKI IZIN AKTIF (ID TERDAFTAR DI BALIK LAYAR)
    if user_id not in ACTIVE_USERS:
        return # Abaikan total jika user belum mengetik /dt_twrp sebelumnya

    # 2. VALIDASI EKSTENSI .IMG
    file_name = message.document.file_name or ""
    if not file_name.lower().endswith('.img'):
        return

    # 3. CABUT IZIN (Hapus ID dari Set agar gerbang langsung tertutup kembali untuk mencegah spam/looping)
    ACTIVE_USERS.remove(user_id)

    msg = await message.reply_text("⏳ **File `.img` terdeteksi dari pemilik sesi!**\nMemulai unduhan...")

    # 4. Membuat Folder Workspace Unik per Eksekusi
    rand_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    work_dir = f"workspace_{rand_id}"
    
    try:
        os.makedirs(work_dir, exist_ok=True)
        
        # 5. Unduh file
        file_path = await client.download_media(message, file_name=f"{work_dir}/source.img")

        await msg.edit_text("⚙️ **Mengekstrak Device Tree...**")

        output_dir = os.path.join(work_dir, "output")
        os.makedirs(output_dir, exist_ok=True)

        # 6. Proses Ekstraksi twrpdtgen
        result = subprocess.run(["python3", "-m", "twrpdtgen", file_path, "-o", output_dir], capture_output=True, text=True)
        
        if result.returncode != 0:
            await msg.edit_text(f"❌ **Gagal mengekstrak device tree.**\n\n**Log Error:**\n`{result.stderr}`")
            return

        # 7. Baca Struktur Folder Output
        manufacturers = os.listdir(output_dir)
        if not manufacturers:
            raise Exception("Folder output kosong. Pastikan file img mengandung ramdisk.")
        manufacturer = manufacturers[0]
        
        codenames = os.listdir(os.path.join(output_dir, manufacturer))
        if not codenames:
            raise Exception("Tidak dapat menemukan codename perangkat.")
        codename = codenames[0]

        device_tree_path = os.path.join(output_dir, manufacturer, codename)

        # 8. Inspeksi Variabel .mk
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

        # 9. Format Penamaan Baru & Replace File jika sudah ada
        custom_img_name = f'twrp-{product_model}-{build_desc}-{build_fingerprint}.img'.replace(':', '_')
        final_workspace_img_path = os.path.join(work_dir, custom_img_name)
        
        os.replace(file_path, final_workspace_img_path)

        repo_name = f"android_device_{manufacturer}_{codename}"
        
        await msg.edit_text(f"✅ **Ekstraksi berhasil!**\n🚀 Mengunggah ke GitHub `@{GITHUB_USERNAME}`...")

        # 10. Buat Repositori GitHub
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        repo_data = {
            "name": repo_name,
            "description": f"TWRP Device Tree for {codename} | Model: {product_model}",
            "private": False
        }
        
        req = requests.post("https://api.github.com/user/repos", json=repo_data, headers=headers)
        if req.status_code not in [201, 422]:
            raise Exception(f"Gagal membuat repositori GitHub:\n{req.text}")

        # 11. Git Push Source Code
        subprocess.run(["git", "config", "--global", "user.email", "userbot@twrpdtgen.local"])
        subprocess.run(["git", "config", "--global", "user.name", "TWRP Userbot"])
        
        os.chdir(device_tree_path)
        subprocess.run(["git", "init"])
        subprocess.run(["git", "add", "."])
        subprocess.run(["git", "commit", f"-m", f"Add device tree for {codename} ({product_model})"])
        subprocess.run(["git", "branch", "-M", "main"])
        
        remote_url = f"https://{GITHUB_USERNAME}:{GITHUB_TOKEN}@github.com/{GITHUB_USERNAME}/{repo_name}.git"
        subprocess.run(["git", "remote", "add", "origin", remote_url])
        subprocess.run(["git", "push", "-u", "origin", "main", "--force"])
        
        os.chdir("../../..")

        # 12. Kirim Hasil Akhir
        github_link = f"https://github.com/{GITHUB_USERNAME}/{repo_name}/tree/main"
        
        final_text = (
            "✅ **TWRP Device Tree Generated!**\n\n"
            f"📱 **Model:** `{product_model}`\n"
            f"📟 **Codename:** `{codename}`\n"
            f"📋 **Build desc:** `{build_desc}`\n\n"
            f"🏷️ **Custom Filename Format:**\n`{custom_img_name}`\n\n"
            f"🔗 **Device tree:** {github_link}"
        )
        
        await msg.edit_text(final_text, disable_web_page_preview=True)

    except Exception as e:
        await msg.edit_text(f"❌ **Terjadi kesalahan:**\n`{str(e)}`")
    
    finally:
        if os.path.exists(work_dir):
            shutil.rmtree(work_dir, ignore_errors=True)

# ==============================================================================
# EKSEKUSI UTAMA
# ==============================================================================
if __name__ == "__main__":
    print("Userbot TWRP Generator ID Session Mode Menyala!")
    app.run()
