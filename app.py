import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from googleapiclient.discovery import build
from google.oauth2 import service_account
from flask import Flask, request
import os
import asyncio

# Thiết lập logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Token của bot (lấy từ biến môi trường)
TOKEN = os.getenv("TELEGRAM_TOKEN")

# Thông tin Google Sheets
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
RANGE_NAME = "ErrorCodes!A2:C"

# Thiết lập thông tin xác thực Google Sheets từ biến môi trường
SERVICE_ACCOUNT_INFO = {
    "type": "service_account",
    "project_id": os.getenv("PROJECT_ID"),
    "private_key_id": os.getenv("PRIVATE_KEY_ID"),
    "private_key": os.getenv("PRIVATE_KEY").replace('\\n', '\n'),  # Thay thế \n cho private key
    "client_email": os.getenv("CLIENT_EMAIL"),
    "client_id": os.getenv("CLIENT_ID"),
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": os.getenv("CLIENT_X509_CERT_URL"),
    "universe_domain": "googleapis.com"
}

# Thiết lập thông tin xác thực và kết nối với Google Sheets
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
creds = service_account.Credentials.from_service_account_info(SERVICE_ACCOUNT_INFO, scopes=SCOPES)
service = build('sheets', 'v4', credentials=creds)

# Flask app để xử lý webhook
app = Flask(__name__)

# Khởi tạo ứng dụng Telegram
application = Application.builder().token(TOKEN).build()

# Hàm lấy dữ liệu mã lỗi từ Google Sheets
def get_error_codes_from_sheets():
    try:
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
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
        logging.error(f"Error fetching data from Google Sheets: {e}")
        return {}

# Hàm xử lý lệnh /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Xin chào! Tôi là Bot Tra cứu Mã Lỗi.\n"
        "Hãy gửi mã lỗi (ví dụ: 400, 401) để tôi giúp bạn tìm hiểu cách xử lý.\n"
        "Gõ /help để biết thêm thông tin."
    )

# Hàm xử lý lệnh /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hãy gửi mã lỗi (ví dụ: 400, 401, 429) để tôi cung cấp mô tả và cách xử lý.\n"
        "Ví dụ: chỉ cần gõ 400"
    )

# Hàm xử lý tin nhắn người dùng (tra cứu mã lỗi)
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    error_codes = get_error_codes_from_sheets()
    if user_input in error_codes:
        error_info = error_codes[user_input]
        response = f"**Mã Lỗi: {user_input}**\n\n" \
                   f"**Mô tả:** {error_info['description']}\n\n" \
                   f"**Cách xử lý:** {error_info['solution']}"
    else:
        response = f"Xin lỗi, tôi không tìm thấy thông tin về mã lỗi '{user_input}'.\n" \
                   "Vui lòng thử mã lỗi khác hoặc liên hệ hỗ trợ để biết thêm chi tiết."
    await update.message.reply_text(response)

# Thêm các handler
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("help", help_command))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# Route webhook cho Flask
@app.route('/webhook', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    asyncio.run_coroutine_threadsafe(application.process_update(update), loop)
    return "OK", 200

# Hàm thiết lập webhook
async def set_webhook():
    webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_URL')}/webhook"
    await application.bot.set_webhook(url=webhook_url)
    logging.info(f"Webhook set to {webhook_url}")

# Khởi động bot
if __name__ == "__main__":
    # Tạo loop asyncio
    loop = asyncio.get_event_loop()
    application.loop = loop

    # Thiết lập webhook
    loop.run_until_complete(set_webhook())

    # Chạy Flask app
    port = int(os.getenv("PORT"))  # Render sẽ cung cấp cổng qua biến PORT
    app.run(host="0.0.0.0", port=port)