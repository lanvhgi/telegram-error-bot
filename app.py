import os
import json
import logging
from flask import Flask, request
from telegram import Bot, Update
from telegram.ext import Dispatcher, CommandHandler

# Thiết lập logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Khởi tạo Flask app
app = Flask(__name__)

# Khởi tạo bot và dispatcher
TOKEN = os.environ.get("TELEGRAM_TOKEN")
bot = Bot(token=TOKEN)
dispatcher = Dispatcher(bot, None, use_context=True)

# === Handlers ===

def start(update, context):
    update.message.reply_text("Xin chào! Tôi là bot báo lỗi.")

def help_command(update, context):
    update.message.reply_text("Gửi tôi một tin nhắn để nhận phản hồi.")

def echo(update, context):
    update.message.reply_text(update.message.text)

# Thêm các handler vào dispatcher
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("help", help_command))
dispatcher.add_handler(CommandHandler(None, echo))  # Xử lý lệnh không rõ

# === Webhook endpoint ===

@app.route("/webhook", methods=["POST"])
def webhook():
    logging.info("Webhook nhận yêu cầu mới.")
    try:
        data = request.get_json(force=True)
        update = Update.de_json(data, bot)
        dispatcher.process_update(update)
    except Exception as e:
        logger.error("Lỗi khi xử lý webhook: %s", str(e), exc_info=True)
        return "Internal Server Error", 500
    return "OK", 200

# === Endpoint kiểm tra trạng thái ===
@app.route("/")
def index():
    return "Bot đang chạy!", 200
