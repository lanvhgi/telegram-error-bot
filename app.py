import logging
import os
import json
from functools import lru_cache
from flask import Flask, request
from telegram import Bot, Update, InputFile
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters
from googleapiclient.discovery import build
from google.oauth2 import service_account
import threading
import requests
import time
import re

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
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range="ErrorCodes!A2:D").execute()
        values = result.get('values', [])
        error_codes = {}
        for row in values:
            if len(row) >= 4:
                error_code = row[0].strip()
                error_codes[error_code] = {
                    "description_en": row[1],
                    "description_vi": row[2],
                    "solution": row[3]
                }
        logger.info(f"Loaded error codes: {list(error_codes.keys())}")
        return error_codes
    except Exception as e:
        logger.error(f"Lỗi khi lấy dữ liệu từ Google Sheets: {e}")
        return {}

@lru_cache(maxsize=1)
def get_knowledge_from_sheets():
    try:
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range="Mhdh613!A2:C").execute()
        values = result.get('values', [])
        knowledge_data = {}
        for row in values:
            if len(row) >= 3:
                keyword = row[0].strip().lower()
                knowledge_data[keyword] = {
                    "title": row[1],
                    "content": row[2]
                }
        logger.info(f"Loaded knowledge keywords: {list(knowledge_data.keys())}")
        return knowledge_data
    except Exception as e:
        logger.error(f"Lỗi khi lấy dữ liệu kiến thức từ Google Sheets: {e}")
        return {}

def start(update, context):
    update.message.reply_text(
        "Xin chào! Tôi là Bot Tra cứu Mã Lỗi.\n"
        "Gửi mã lỗi bằng cú pháp /<mã lỗi> (ví dụ: /400 hoặc /401) để tôi giúp bạn tra cứu.\n"
        "Gửi từ khóa kiến thức bằng cú pháp /<từ khóa> (ví dụ: /qtgsttp, /htktm1, /ktdb, /mhdh613).\n"
        "Dùng /help để biết thêm chi tiết."
    )

def help_command(update, context):
    help_text = (
        "📘 <b>Hướng dẫn tra cứu mã lỗi</b> 🔍\n"
        "Vui lòng tìm dòng có chứa <b>FaultID</b> hoặc <b>additionalFaultID</b> trong phiếu xử lý sự cố.\n"
        "🔢 Mã lỗi thường là một dãy số như <code>1907</code>, <code>2004</code>, v.v.\n\n"
        "📌 Gửi mã lỗi theo cú pháp: <code>/[mã lỗi]</code> (ví dụ: <code>/1907</code>).\n"
        "📎 Ví dụ: <code>additionalFaultID=1907</code> (nằm trong phần 'Nội dung cảnh báo')\n\n"
        "🖼 Xem ảnh minh họa bên dưới để dễ hình dung hơn."
    )
    update.message.reply_text(help_text, parse_mode='HTML')
    try:
        with open("guide_image.png", "rb") as img:
            update.message.reply_photo(photo=InputFile(img))
    except FileNotFoundError:
        update.message.reply_text("⚠️ Không tìm thấy ảnh hướng dẫn. Vui lòng kiểm tra file guide_image.png.")

    # Lấy danh sách kiến thức từ sheet Mhdh613
    knowledge_data = get_knowledge_from_sheets()
    knowledge_commands = []
    for keyword, info in knowledge_data.items():
        command = f"• <code>/{keyword}</code> – {info['title']}"
        knowledge_commands.append(command)

    command_info = (
        "✅ <b>Các lệnh hỗ trợ:</b>\n"
        "• <code>/help</code> – Cách tìm mã lỗi và sử dụng bot\n"
        "• <code>/list</code> – Danh sách tất cả mã lỗi hỗ trợ\n"
        "• <code>/refresh</code> – Làm mới dữ liệu mã lỗi từ Google Sheets\n"
        + "\n".join(knowledge_commands)
    )
    update.message.reply_text(command_info, parse_mode='HTML')

def list_command(update, context):
    error_codes = get_error_codes_from_sheets()
    if not error_codes:
        update.message.reply_text("⚠️ Chưa có mã lỗi nào được tải từ Google Sheets.")
        return
    message = "📋 <b>Danh sách mã lỗi đang hỗ trợ:</b>\n\n"
    message += "\n".join(f"• <code>/{code}</code>" for code in sorted(error_codes.keys()))
    update.message.reply_text(message, parse_mode='HTML')

def refresh_cache(update, context):
    try:
        get_error_codes_from_sheets.cache_clear()
        get_knowledge_from_sheets.cache_clear()
        update.message.reply_text("✅ Cache đã được làm mới. Hãy thử lại tra cứu.")
        logger.info("Cache đã được làm mới theo lệnh /refresh.")
    except Exception as e:
        logger.error(f"Lỗi khi làm mới cache: {e}")
        update.message.reply_text("❌ Có lỗi khi làm mới cache.")

def knowledge_command(update, context):
    user_input = update.message.text.strip().lstrip('/').lower()
    logger.info(f"Người dùng tra cứu kiến thức với từ khóa: {user_input}")
    knowledge_data = get_knowledge_from_sheets()

    if user_input in knowledge_data:
        info = knowledge_data[user_input]
        reply = (
            f"📚 <b>{info['title']}</b>\n\n"
            f"{info['content']}"
        )
    else:
        reply = (
            f"❌ Không tìm thấy thông tin cho từ khóa <b>{user_input}</b>.\n"
            "Vui lòng thử từ khóa khác hoặc dùng /help để xem danh sách."
        )
    update.message.reply_text(reply, parse_mode='HTML')

def handle_error_code(update, context):
    user_input = update.message.text.strip().lstrip('/')
    logger.info(f"Người dùng gửi: /{user_input}")
    logger.info(f"Chat ID: {update.effective_chat.id} | Loại: {update.effective_chat.type} | Tên: {update.effective_chat.title}")
    error_codes = get_error_codes_from_sheets()
    if user_input in error_codes:
        info = error_codes[user_input]
        reply = (
            f"📟 <b>Mã Lỗi:</b> <code>{user_input}</code>\n\n"
            f"🇬🇧 <b>Mô tả (EN):</b> {info['description_en']}\n"
            f"🇻🇳 <b>Mô tả (VI):</b> {info['description_vi']}\n\n"
            f"🛠 <b>Cách xử lý:</b>\n{info['solution']}"
        )
    else:
        reply = (
            f"❌ Không tìm thấy thông tin cho mã lỗi <b>{user_input}</b>.\n"
            "Vui lòng kiểm tra lại hoặc dùng lệnh /list để xem danh sách mã lỗi."
        )
    update.message.reply_text(reply, parse_mode='HTML')

def unknown_command(update, context):
    user_input = update.message.text.strip()
    if user_input.startswith('/'):
        update.message.reply_text(
            "⚠️ Lệnh không hợp lệ hoặc mã lỗi không tồn tại.\n"
            "Dùng /help để xem hướng dẫn hoặc /list để xem danh sách mã lỗi hỗ trợ."
        )

# Hàm ping để giữ bot awake
def keep_alive():
    ping_url = RENDER_EXTERNAL_URL
    while True:
        try:
            logger.info(f"Pinging {ping_url} to keep bot alive")
            requests.get(ping_url)
            time.sleep(300)  # Ping mỗi 5 phút (300 giây)
        except Exception as e:
            logger.error(f"Lỗi khi ping: {e}")
            time.sleep(300)

# Khởi động thread ping
ping_thread = threading.Thread(target=keep_alive, daemon=True)
ping_thread.start()

# Tạo regex từ các từ khóa trong knowledge_data
knowledge_data = get_knowledge_from_sheets()
knowledge_keywords = "|".join(re.escape(keyword) for keyword in knowledge_data.keys())
knowledge_pattern = re.compile(fr'^/({knowledge_keywords})$', re.IGNORECASE)
knowledge_handler = MessageHandler(Filters.regex(knowledge_pattern), knowledge_command)

dispatcher.add_handler(MessageHandler(Filters.regex(r'^/(\d+)$'), handle_error_code))
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("help", help_command))
dispatcher.add_handler(CommandHandler("list", list_command))
dispatcher.add_handler(CommandHandler("refresh", refresh_cache))
dispatcher.add_handler(knowledge_handler)
dispatcher.add_handler(MessageHandler(Filters.command, unknown_command))

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