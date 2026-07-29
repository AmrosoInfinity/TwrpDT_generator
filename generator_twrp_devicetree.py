import os
import shutil
import telebot
import subprocess
import requests
import glob
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ================= KONFIGURASI MENGGUNAKAN ENVIRONMENT VARIABLES =================
# Variabel ini akan diambil secara otomatis dari GitHub Secrets oleh file YAML
BOT_TOKEN = os.environ.get("BOT_TOKEN")
GITHUB_USERNAME = os.environ.get("GH_USERNAME")
GITHUB_TOKEN = os.environ.get("GH_TOKEN")
# ===============================================================================

bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    teks = (
        "🤖 **Selamat datang di Generator Device Tree TWRP!**\n\n"
        "**Pengenalan:**\n"
        "Bot ini adalah asisten otomatis untuk mengekstrak dan membuat *Device Tree* TWRP dari file partisi *boot* perangkat Android Anda.\n\n"
        "**Fungsi & Harapan:**\n"
        "Bot ini berfungsi untuk menghemat waktu *developer* dengan mengeksekusi `twrpdtgen` di belakang layar dan langsung mengunggah hasilnya ke GitHub. Diharapkan bot ini mempermudah komunitas dalam merakit *Custom Recovery*.\n\n"
        "**Penggunaan:**\n"
        "Kirimkan file berekstensi `.img` sebagai dokumen ke obrolan ini."
    )

    markup = InlineKeyboardMarkup()
    btn_info = InlineKeyboardButton("💡 Info Input partisi (.img)", callback_data="info_input")
    btn_share = InlineKeyboardButton("🔗 Share Bot", url="https://t.me/share/url?url=https://t.me/genDT_TWRPbot&text=Coba%20Bot%20Generator%20Device%20Tree%20TWRP%20ini!")
    markup.add(btn_info)
    markup.add(btn_share)

    bot.send_message(message.chat.id, teks, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "info_input")
def callback_info(call):
    pesan_info = (
        "Silakan kirim file berekstensi .img ke bot ini.\n\n"
        "⚠️ Pastikan Anda menginput partisi yang sesuai (ramdisk)! Karena kemungkinan bukan hanya di boot.img saja. "
        "Misalnya, untuk perangkat baru bisa jadi di vendor_boot.img atau recovery.img."
    )
    bot.answer_callback_query(call.id, "Membaca info input...", show_alert=False)
    bot.send_message(call.message.chat.id, pesan_info)

@bot.message_handler(content_types=['document'])
def handle_document(message):
    if not message.document.file_name.endswith('.img'):
        bot.reply_to(message, "❌ Harap kirimkan file dengan ekstensi `.img`!")
        return

    # Pengecekan limit 20MB Telegram API
    if message.document.file_size > 20 * 1024 * 1024:
        bot.reply_to(message, "❌ Ukuran file melebihi 20MB. Bot Telegram API standar tidak dapat mengunduh file ini.")
        return

    msg = bot.reply_to(message, "⏳ Mengunduh file `.img` Anda...")

    try:
        # Unduh file
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        work_dir = "workspace"
        os.makedirs(work_dir, exist_ok=True)
        file_path = os.path.join(work_dir, "boot.img")
        
        with open(file_path, 'wb') as new_file:
            new_file.write(downloaded_file)

        bot.edit_message_text("⚙️ Mengekstrak Device Tree...", chat_id=msg.chat.id, message_id=msg.message_id)

        # Hapus folder output lama jika ada
        output_dir = os.path.join(work_dir, "output")
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)

        # Jalankan twrpdtgen
        result = subprocess.run(["python3", "-m", "twrpdtgen", file_path, "-o", output_dir], capture_output=True, text=True)
        
        if result.returncode != 0:
            bot.edit_message_text(f"❌ Gagal mengekstrak device tree.\n\nLog:\n{result.stderr}", chat_id=msg.chat.id, message_id=msg.message_id)
            return

        # Mendapatkan nama Manufacturer dan Codename dari struktur folder
        manufacturers = os.listdir(output_dir)
        if not manufacturers:
            raise Exception("Folder output kosong.")
        manufacturer = manufacturers[0]
        
        codenames = os.listdir(os.path.join(output_dir, manufacturer))
        if not codenames:
            raise Exception("Tidak dapat menemukan codename perangkat.")
        codename = codenames[0]

        device_tree_path = os.path.join(output_dir, manufacturer, codename)
        repo_name = f"android_device_{manufacturer}_{codename}"
        
        bot.edit_message_text(f"✅ Ekstraksi berhasil!\n🚀 Mengunggah ke GitHub @{GITHUB_USERNAME}...", chat_id=msg.chat.id, message_id=msg.message_id)

        # Membuat Repositori di GitHub via API
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        repo_data = {
            "name": repo_name,
            "description": f"TWRP Device Tree for {codename}",
            "private": False
        }
        
        req = requests.post("https://api.github.com/user/repos", json=repo_data, headers=headers)
        if req.status_code not in [201, 422]: # 201 Created, 422 Already exists
            raise Exception(f"Gagal membuat repositori GitHub: {req.text}")

        # Git push proses
        subprocess.run(["git", "config", "--global", "user.email", "bot@twrpdtgen.local"])
        subprocess.run(["git", "config", "--global", "user.name", "TWRP Bot"])
        
        os.chdir(device_tree_path)
        subprocess.run(["git", "init"])
        subprocess.run(["git", "add", "."])
        subprocess.run(["git", "commit", "-m", "Initial commit: auto generated via Telegram Bot"])
        subprocess.run(["git", "branch", "-M", "main"])
        
        remote_url = f"https://{GITHUB_USERNAME}:{GITHUB_TOKEN}@github.com/{GITHUB_USERNAME}/{repo_name}.git"
        subprocess.run(["git", "remote", "add", "origin", remote_url])
        subprocess.run(["git", "push", "-u", "origin", "main", "--force"])
        
        # Kembali ke direktori awal
        os.chdir("../../..")

        # Mencari Build Description dari file .mk
        build_desc = "Unknown"
        mk_files = glob.glob(f"{device_tree_path}/*.mk")
        for mk in mk_files:
            with open(mk, 'r') as f:
                content = f.read()
                if "PRIVATE_BUILD_DESC=" in content:
                    for line in content.split('\n'):
                        if "PRIVATE_BUILD_DESC=" in line:
                            build_desc = line.split('=')[1].replace('"', '').strip()
                            break

        # Format pesan balasan akhir
        github_link = f"https://github.com/{GITHUB_USERNAME}/{repo_name}/tree/main"
        
        final_text = (
            "✅ **TWRP device tree generated**\n"
            f"Codename: `{codename}`\n"
            f"Manufacturer: `{manufacturer}`\n"
            f"Build description: `{build_desc}`\n"
            f"Device tree: {github_link}"
        )
        
        bot.edit_message_text(final_text, chat_id=msg.chat.id, message_id=msg.message_id, parse_mode="Markdown")
        
        # Bersihkan workspace
        shutil.rmtree(work_dir)

    except Exception as e:
        bot.edit_message_text(f"❌ Terjadi kesalahan:\n`{str(e)}`", chat_id=msg.chat.id, message_id=msg.message_id, parse_mode="Markdown")

bot.polling(none_stop=True)
