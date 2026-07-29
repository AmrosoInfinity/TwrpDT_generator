import os
import shutil
import subprocess
import requests
import glob
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
# PENGATURAN BATASAN GRUP (IZINKAN HIDUP DI GRUP TERTENTU SAJA)
# ==============================================================================
# Masukkan ID grup yang diizinkan di sini (bisa berupa integer negatif untuk supergrup).
# Contoh: ALLOWED_GROUP_IDS = [-1001234567890, -1009876543210]
# Jika dikosongkan ([ ]), maka bot tidak akan merespons di grup manapun (hanya chat pribadi).
ALLOWED_GROUP_IDS = [
    -1003503670594, # <-- Ganti dengan ID Grup utama Anda
]

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
# HANDLER: PERINTAH /START
# ==============================================================================
@app.on_message(filters.command("dt_twrp", prefixes=["/", ".", "#"]))
async def start(client, message):
    # Jika di grup, pastikan grup tersebut terdaftar sebelum merespons perintah start
    if message.chat.type in ["supergroup", "group"] and message.chat.id not in ALLOWED_GROUP_IDS:
        return

    teks = (
        "🤖 **Generator Device Tree TWRP (Pro Mode)**\n\n"
        "Sistem ini mendeteksi dan mengekstrak *Device Tree* TWRP dengan kecepatan turbo, mendukung file hingga 2 GB!\n\n"
        "**Cara Penggunaan:**\n"
        "Kirimkan file partisi berekstensi `.img` (misalnya `boot.img`) dengan menyertakan teks **`/dt`** pada *caption*."
    )
    await message.reply_text(teks)

# ==============================================================================
# HANDLER: DETEKSI FILE .IMG OTOMATIS (Dibatasi Grup Tertentu)
# ==============================================================================
@app.on_message(filters.document & (filters.private | filters.group))
async def handle_document(client, message):
    chat_id = message.chat.id
    chat_type = message.chat.type

    # ATURAN KETAT:
    # 1. Jika di dalam Grup/Supergrup, cek apakah ID grup ada di dalam ALLOWED_GROUP_IDS.
    if chat_type in ["supergroup", "group"]:
        if chat_id not in ALLOWED_GROUP_IDS:
            return # Abaikan total jika dari grup yang tidak terdaftar
        
        # Di grup yang diizinkan, user wajib menyertakan caption '/dt'
        caption = message.caption or ""
        if "/dt" not in caption.lower():
            return

    file_name = message.document.file_name or ""
    if not file_name.lower().endswith('.img'):
        return

    msg = await message.reply_text("⏳ **File `.img` terdeteksi!**\nMemulai unduhan... \n*(Kecepatan turbo aktif berkat Userbot + tgcrypto)*")

    work_dir = "workspace"
    try:
        if os.path.exists(work_dir):
            shutil.rmtree(work_dir)
        os.makedirs(work_dir, exist_ok=True)
        
        # 1. PROSES UNDUH FILE
        file_path = await client.download_media(message, file_name=f"{work_dir}/boot.img")

        await msg.edit_text("⚙️ **Mengekstrak Device Tree...**\n*(Memproses file via twrpdtgen)*")

        output_dir = os.path.join(work_dir, "output")
        os.makedirs(output_dir, exist_ok=True)

        # 2. PROSES EKSTRAK (twrpdtgen)
        result = subprocess.run(["python3", "-m", "twrpdtgen", file_path, "-o", output_dir], capture_output=True, text=True)
        
        if result.returncode != 0:
            await msg.edit_text(f"❌ **Gagal mengekstrak device tree.**\n\n**Log Error:**\n`{result.stderr}`")
            return

        # 3. MEMBACA STRUKTUR FOLDER OUTPUT
        manufacturers = os.listdir(output_dir)
        if not manufacturers:
            raise Exception("Folder output kosong. Pastikan ini adalah partisi boot/recovery yang valid.")
        manufacturer = manufacturers[0]
        
        codenames = os.listdir(os.path.join(output_dir, manufacturer))
        if not codenames:
            raise Exception("Tidak dapat menemukan codename perangkat di dalam boot image.")
        codename = codenames[0]

        device_tree_path = os.path.join(output_dir, manufacturer, codename)
        repo_name = f"android_device_{manufacturer}_{codename}"
        
        await msg.edit_text(f"✅ **Ekstraksi berhasil!**\n🚀 Membuat repositori dan mengunggah ke GitHub `@{GITHUB_USERNAME}`...")

        # 4. MEMBUAT REPOSITORI GITHUB BARU
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        repo_data = {
            "name": repo_name,
            "description": f"TWRP Device Tree for {codename} (Auto-generated by Telegram Userbot)",
            "private": False
        }
        
        req = requests.post("https://api.github.com/user/repos", json=repo_data, headers=headers)
        if req.status_code not in [201, 422]:
            raise Exception(f"Gagal membuat repositori GitHub:\n{req.text}")

        # 5. PUSH SOURCE CODE KE GITHUB (GIT)
        subprocess.run(["git", "config", "--global", "user.email", "userbot@twrpdtgen.local"])
        subprocess.run(["git", "config", "--global", "user.name", "TWRP Userbot"])
        
        os.chdir(device_tree_path)
        subprocess.run(["git", "init"])
        subprocess.run(["git", "add", "."])
        subprocess.run(["git", "commit", "-m", "Initial commit: auto generated via Telegram Userbot"])
        subprocess.run(["git", "branch", "-M", "main"])
        
        remote_url = f"https://{GITHUB_USERNAME}:{GITHUB_TOKEN}@github.com/{GITHUB_USERNAME}/{repo_name}.git"
        subprocess.run(["git", "remote", "add", "origin", remote_url])
        subprocess.run(["git", "push", -u, "origin", "main", "--force"])
        
        os.chdir("../../..")

        # 6. INSPEKSI VARIABEL BUILD DESCRIPTION
        build_desc = "Unknown"
        mk_files = glob.glob(f"{device_tree_path}/*.mk")
        for mk in mk_files:
            with open(mk, 'r') as f:
                content = f.read()
                if "PRIVATE_BUILD_DESC" in content:
                    for line in content.split('\n'):
                        if "PRIVATE_BUILD_DESC" in line and "=" in line:
                            build_desc = line.split('=', 1)[1].replace('"', '').replace("'", "").strip()
                            break

        # 7. FORMAT PESAN HASIL AKHIR
        github_link = f"https://github.com/{GITHUB_USERNAME}/{repo_name}/tree/main"
        
        final_text = (
            "✅ **TWRP Device Tree Generated!**\n\n"
            f"📱 **Codename:** `{codename}`\n"
            f"🏭 **Manufacturer:** `{manufacturer}`\n"
            f"📋 **Build desc:** `{build_desc}`\n\n"
            f"🔗 **Device tree:** {github_link}"
        )
        
        await msg.edit_text(final_text, disable_web_page_preview=True)

    except Exception as e:
        await msg.edit_text(f"❌ **Terjadi kesalahan:**\n`{str(e)}`")
    
    finally:
        if os.path.exists(work_dir):
            shutil.rmtree(work_dir)

# ==============================================================================
# EKSEKUSI UTAMA
# ==============================================================================
if __name__ == "__main__":
    print("Userbot TWRP Generator Whitelist Group Mode Menyala!")
    app.run()
