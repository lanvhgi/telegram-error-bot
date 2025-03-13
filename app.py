import logging
import os
import json
from functools import lru_cache
from flask import Flask, request
from telegram import Bot, Update
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters
from googleapiclient.discovery import build
from google.oauth2 import service_account

# Thiết lập logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Đọc biến môi trường
TOKEN = os.getenv("TELEGRAM_TOKEN")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
PROJECT_ID = os.getenv("PROJECT_ID")
PRIVATE_KEY_ID = os.getenv("PRIVATE_KEY_ID")
PRIVATE_KEY = os.getenv("PRIVATE_KEY", "").replace('\\n', '\n')
CLIENT_EMAIL = os.getenv("CLIENT_EMAIL")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_X509_CERT_URL = os.getenv("CLIENT_X509_CERT_URL")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")
PORT = int(os.getenv("PORT", 8080))

required_vars = [TOKEN, SPREADSHEET_ID, PROJECT_ID, PRIVATE_KEY_ID, PRIVATE_KEY, CLIENT_EMAIL, CLIENT_ID, CLIENT_X509_CERT_URL, RENDER_EXTERNAL_URL]
if not all(required_vars):
    raise EnvironmentError("Thiếu một hoặc nhiều biến môi trường. Vui lòng kiểm tra .env hoặc Render settings.")

SERVICE_ACCOUNT_INFO = {
    "type": "service_account",
    "project_id": PROJECT_ID,
    "private_key_id": PRIVATE_KEY_ID,
    "private_key": PRIVATE_KEY,
    "client_email": CLIENT_EMAIL,
    "client_id": CLIENT_ID,
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": CLIENT_X509_CERT_URL,
    "universe_domain": "googleapis.com"
}

SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
creds = service_account.Credentials.from_service_account_info(SERVICE_ACCOUNT_INFO, scopes=SCOPES)
service = build('sheets', 'v4', credentials=creds)

app = Flask(__name__)
bot = Bot(token=TOKEN)
dispatcher = Dispatcher(bot, None, use_context=True)

@lru_cache(maxsize=1)
def get_error_codes_from_sheets():
    try:
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range="ErrorCodes!A2:C").execute()
        values = result.get('values', [])
        error_codes = {}
        for row in values:
            if len(row) >= 3:
                error_code = row[0].strip()
                error_codes[error_code] = {
                    "description": row[1],
                    "solution": row[2]
                }
        return error_codes
    except Exception as e:
        logger.error(f"Lỗi khi lấy dữ liệu từ Google Sheets: {e}")
        return {}

def start(update, context):
    update.message.reply_text(
        "Xin chào! Tôi là Bot Tra cứu Mã Lỗi.\n"
        "Gửi mã lỗi như 400 hoặc 401 để tôi giúp bạn tra cứu."
    )

def help_command(update, context):
    update.message.reply_text(
        "Gửi mã lỗi (ví dụ: 400, 401, 500) để tôi trả lời mô tả và cách xử lý.\n"
        "VD: chỉ cần gõ 400"
    )

def refresh_cache(update, context):
    try:
        get_error_codes_from_sheets.cache_clear()
        update.message.reply_text("✅ Cache đã được làm mới. Hãy thử lại tra cứu.")
        logger.info("Cache đã được làm mới theo lệnh /refresh.")
    except Exception as e:
        logger.error(f"Lỗi khi làm mới cache: {e}")
        update.message.reply_text("❌ Có lỗi khi làm mới cache.")

def handle_message(update, context):
    user_input = update.message.text.strip()
    logger.info(f"Người dùng gửi: {user_input}")
    error_codes = get_error_codes_from_sheets()
    if user_input in error_codes:
        info = error_codes[user_input]
        reply = f"\u2728 <b>Mã Lỗi:</b> <code>{user_input}</code>\n\n" \
                f"<b>Mô tả:</b> {info['description']}\n\n" \
                f"<b>Cách xử lý:</b> {info['solution']}"
    else:
        reply = f"❌ Không tìm thấy thông tin cho mã lỗi {user_input}.\nVui lòng thử lại mã khác."
    update.message.reply_text(reply, parse_mode='HTML')

dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("help", help_command))
dispatcher.add_handler(CommandHandler("refresh", refresh_cache))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

@app.route("/webhook", methods=["POST"])
def webhook():
    logger.info("Webhook nhận yêu cầu mới.")
    try:
        data = request.get_json(force=True)
        update = Update.de_json(data, bot)
        dispatcher.process_update(update)
    except Exception as e:
        logger.error(f"Lỗi khi xử lý webhook: {e}", exc_info=True)
        return "Lỗi", 500
    return "OK", 200

@app.route("/")
def index():
    return "Bot đang chạy!", 200

if __name__ == "__main__":
    webhook_url = f"https://{RENDER_EXTERNAL_URL}/webhook"
    bot.set_webhook(url=webhook_url)
    logger.info(f"✅ Đã thiết lập webhook: {webhook_url}")
    app.run(host="0.0.0.0", port=PORT)
