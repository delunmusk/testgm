# Telegram YouTube Shorts Downloader

Bot Telegram untuk menerima hingga 10 link YouTube dalam satu pesan, lalu mengunduh dan mengirim video satu per satu.

Gunakan hanya video yang Anda miliki atau berhak untuk diunduh. Bot ini tidak menangani konten ber-DRM.

## Deploy ke Render

1. Simpan folder ini dalam repository GitHub baru.
2. Di Render, pilih **New → Background Worker** lalu pilih repository tersebut.
3. Gunakan **Docker** sebagai environment dan pilih branch utama.
4. Tambahkan Environment Variable `BOT_TOKEN` dengan token dari @BotFather.
5. Klik **Create Background Worker**.

Background Worker dipakai agar bot bisa menjalankan long polling 24 jam. Jangan memakai Static Site atau Web Service untuk konfigurasi ini.
