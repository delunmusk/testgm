import asyncio
import logging
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yt_dlp
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters


BOT_TOKEN = os.environ.get("BOT_TOKEN")
MAX_LINKS_PER_MESSAGE = int(os.environ.get("MAX_LINKS_PER_MESSAGE", "10"))
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_MB", "49")) * 1024 * 1024

YOUTUBE_URL = re.compile(
    r"https?://(?:www\.)?(?:youtube\.com/(?:shorts|watch)\?[^\s]+|youtu\.be/)[^\s<>()]+",
    re.IGNORECASE,
)


@dataclass
class DownloadJob:
    chat_id: int
    source_url: str
    position: int
    total: int


queue: asyncio.Queue[DownloadJob] = asyncio.Queue()


def find_youtube_urls(text: str) -> list[str]:
    urls: list[str] = []
    for match in YOUTUBE_URL.findall(text):
        url = match.rstrip(".,!?:;)]}")
        if url not in urls:
            urls.append(url)
    return urls


def download_video(source_url: str) -> tuple[Path, str]:
    """Download one video into an isolated folder and return its final file."""
    output_dir = Path(tempfile.mkdtemp(prefix="yt-short-"))
    options = {
        "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]/b",
        "outtmpl": str(output_dir / "%(title).80B-%(id)s.%(ext)s"),
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 30,
    }
    with yt_dlp.YoutubeDL(options) as downloader:
        info = downloader.extract_info(source_url, download=True)
        title = info.get("title") or "YouTube Short"

    candidates = [
        path for path in output_dir.iterdir()
        if path.is_file() and path.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"}
    ]
    if not candidates:
        shutil.rmtree(output_dir, ignore_errors=True)
        raise RuntimeError("File video tidak ditemukan setelah download.")
    return max(candidates, key=lambda path: path.stat().st_size), title


async def worker(application: Application) -> None:
    while True:
        job = await queue.get()
        downloaded_path: Optional[Path] = None
        try:
            await application.bot.send_chat_action(job.chat_id, ChatAction.UPLOAD_VIDEO)
            downloaded_path, title = await asyncio.to_thread(download_video, job.source_url)
            size = downloaded_path.stat().st_size
            if size > MAX_UPLOAD_BYTES:
                await application.bot.send_message(
                    job.chat_id,
                    f"Video {job.position}/{job.total} terlalu besar untuk dikirim bot "
                    f"({size / 1024 / 1024:.1f} MB).",
                )
                continue
            with downloaded_path.open("rb") as video:
                await application.bot.send_video(
                    chat_id=job.chat_id,
                    video=video,
                    caption=f"{job.position}/{job.total} — {title[:900]}",
                    supports_streaming=True,
                )
        except Exception as error:  # Keep the queue alive after one bad link.
            logging.exception("Download failed: %s", error)
            await application.bot.send_message(
                job.chat_id,
                f"Gagal memproses video {job.position}/{job.total}. Link mungkin privat, dibatasi, atau tidak didukung.",
            )
        finally:
            if downloaded_path:
                shutil.rmtree(downloaded_path.parent, ignore_errors=True)
            queue.task_done()


async def post_init(application: Application) -> None:
    application.create_task(worker(application), name="download-worker")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message:
        return
    await update.effective_message.reply_text(
        "Kirim link YouTube Shorts. Kamu boleh paste sampai "
        f"{MAX_LINKS_PER_MESSAGE} link sekaligus; bot memprosesnya satu per satu."
    )


async def receive_links(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message or not message.text or not update.effective_chat:
        return
    urls = find_youtube_urls(message.text)
    if not urls:
        await message.reply_text("Kirim link YouTube Shorts yang valid.")
        return
    if len(urls) > MAX_LINKS_PER_MESSAGE:
        await message.reply_text(f"Maksimal {MAX_LINKS_PER_MESSAGE} link dalam satu pesan.")
        return
    for position, source_url in enumerate(urls, start=1):
        await queue.put(DownloadJob(update.effective_chat.id, source_url, position, len(urls)))
    await message.reply_text(
        f"{len(urls)} link masuk antrean. Hasil akan dikirim satu per satu."
    )


def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN belum diatur.")
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.INFO,
    )
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_links))
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
