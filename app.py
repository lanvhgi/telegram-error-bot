import logging
import os
import json
from functools import lru_cache
from flask import Flask, request
from telegram import Bot, Update, InputFile
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
        return error_codes
    except Exception as e:
        logger.error(f"Lỗi khi lấy dữ liệu từ Google Sheets: {e}")
        return {}

def start(update, context):
    update.message.reply_text(
        "Xin chào! Tôi là Bot Tra cứu Mã Lỗi.\n"
        "Gửi mã lỗi bằng cú pháp /<mã lỗi> (ví dụ: /400 hoặc /401) để tôi giúp bạn tra cứu.\n"
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

    command_info = (
        "✅ <b>Các lệnh hỗ trợ:</b>\n"
        "• <code>/help</code> – Cách tìm mã lỗi và sử dụng bot\n"
        "• <code>/list</code> – Danh sách tất cả mã lỗi hỗ trợ\n"
        "• <code>/refresh</code> – Làm mới dữ liệu mã lỗi từ Google Sheets\n"
        "• <code>/qtgsttp</code> – Chức năng nhiệm vụ của Quản trị giám sát mức T/TP\n"
        "• <code>/htktm1</code> – Chức năng nhiệm vụ của Hỗ trợ kỹ thuật mức 1\n"
        "• <code>/ktdb</code> – Chức năng nhiệm vụ của Kỹ thuật địa bàn"
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
        update.message.reply_text("✅ Cache đã được làm mới. Hãy thử lại tra cứu.")
        logger.info("Cache đã được làm mới theo lệnh /refresh.")
    except Exception as e:
        logger.error(f"Lỗi khi làm mới cache: {e}")
        update.message.reply_text("❌ Có lỗi khi làm mới cache.")

def qtgsttp(update, context):
    message = (
        "📋 <b>Chức năng nhiệm vụ của Quản trị giám sát mức T/TP</b>\n\n"
        "<b>QTGS Quản trị, giám sát, điều hành chất lượng dịch vụ di động mức Tỉnh/TP có 6 chức năng và nhiệm vụ là:</b>\n"
        "1. Quản trị, giám sát công tác xử lý phản ánh khách hàng, chất lượng chủ động, Cell chất lượng kém và sự cố trạm vô tuyến trong phạm vi toàn tỉnh theo các chỉ tiêu về thời gian xử lý và tỷ lệ phiếu đúng hạn\n"
        "2. Đánh giá, phân tích các tồn tại và thực hiện đôn đốc, điều hành các đơn vị xử lý phản ánh khách hàng, chất lượng chủ động, Cell chất lượng kém và sự cố trạm vô tuyến trong phạm vi toàn tỉnh\n"
        "3. Tổng hợp, báo cáo định kỳ và đảm bảo tính chính xác về số liệu đánh giá công tác xử lý phản ánh khách hàng, chất lượng chủ động, Cell chất lượng kém và sự cố trạm vô tuyến trong phạm vi toàn tỉnh\n"
        "4. Đề xuất điều chỉnh tính năng các công cụ chuyển đổi số hỗ trợ công tác đảm bảo, nâng cao chất lượng xử lý phản ánh khách hàng, chất lượng chủ động, Cell chất lượng kém và sự cố trạm vô tuyến\n"
        "5. Quản lý và thực hiện điều phối vật tư xử lý phản ánh khách hàng, chất lượng chủ động, Cell chất lượng kém và sự cố trạm vô tuyến trong phạm vi toàn tỉnh khi cần\n"
        "6. Tiếp nhận và xử lý yêu cầu từ đơn vị quản trị, giám sát, điều hành chất lượng dịch vụ mức toàn quốc"
    )
    update.message.reply_text(message, parse_mode='HTML')

def htktm1(update, context):
    message = (
        "📋 <b>Chức năng nhiệm vụ của Hỗ trợ kỹ thuật mức 1</b>\n\n"
        "<b>HỔ TRỢ KỸ THUẬT MỨC 1 CÓ 8 CHỨC NĂNG VÀ NHIỆM VỤ LÀ:</b>\n"
        "1. Phân tích logfile đo kiểm, đề xuất phương án (CRs) điều chỉnh hiện trường để xử lý đảm bảo chất lượng dịch vụ, chất lượng vùng phủ sóng tại địa bàn, gửi đơn vị hỗ trợ kỹ thuật mức 2 phê duyệt\n"
        "2. Cập nhật thông tin về CSHT nhà trạm, cột cao trên các hệ thống quản lý và đảm bảo độ chính xác thông số RF (độ cao, góc ngẩng, góc phương vị…) tại hiện trường\n"
        "3. Chủ trì xử lý cell/site chất lượng kém\n"
        "4. Tiếp nhận và hỗ trợ nhân viên kỹ thuật địa bàn xử lý sự cố: CSHT nhà trạm (nguồn điện, truyền dẫn,…). Phần cứng trạm vô tuyến\n"
        "5. Thực hiện đo kiểm vùng phủ sóng phục vụ Tối ưu hóa và Nâng cao chất lượng vô tuyến theo kế hoạch\n"
        "6. Khảo sát, đề xuất điều chỉnh vị trí tối ưu CSHT\n"
        "7. Tháo dỡ, lắp đặt, di dời trạm riêng lẻ phạm vi nội tỉnh phục vụ tối ưu CSHT, xử lý, nâng cao chất lượng mạng, xử lý phản ánh khách hàng\n"
        "8. Gửi yêu cầu tới các đơn vị hỗ trợ kỹ thuật mức cao hơn (cấu hình tham số hệ thống, cung cấp vật tư,…)"
    )
    update.message.reply_text(message, parse_mode='HTML')

def ktdb(update, context):
    message = (
        "📋 <b>Chức năng nhiệm vụ của Kỹ thuật địa bàn</b>\n\n"
        "<b>Kỹ thuật địa bàn gồm có 10 chức năng và nhiệm vụ là:</b>\n"
        "1. Đảm bảo hoạt động, chất lượng và xử lý sự cố nguồn điện\n"
        "2. Đảm bảo hoạt động, chất lượng và xử lý sự cố truyền dẫn tại trạm\n"
        "3. Đảm bảo hoạt động, chất lượng và xử lý sự cố các hạng mục CSHT khác (điều hoà, cảnh báo ngoài, điện chiếu sáng, tiếp đất, chống sét,…)\n"
        "4. Theo dõi chất lượng và vùng phủ sóng của các trạm vô tuyến được giao\n"
        "5. Đảm bảo các thông số RF tại hiện trường (độ cao, góc ngẩng, góc phương vị, trạng thái feeder, connector…) không sai lệch so với số liệu trên các hệ thống quản lý\n"
        "6. Điều chỉnh các thông số tại hiện trường (độ cao, góc ngẩng, góc phương vị…) theo CRs đã được phê duyệt\n"
        "7. Xử lý cảnh báo phần cứng tại trạm vô tuyến\n"
        "8. Thực hiện bảo dưỡng trạm vô tuyến\n"
        "9. Tiếp nhận thông tin về phản ánh khách hàng và kiểm tra, xác minh, xử lý tại hiện trường\n"
        "10. Gửi yêu cầu tới đơn vị hỗ trợ kỹ thuật mức 1 nếu cần"
    )
    update.message.reply_text(message, parse_mode='HTML')

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
    # Không trả lời nếu không có /

# Thêm handler cho các lệnh mã lỗi tùy chỉnh
dispatcher.add_handler(MessageHandler(Filters.regex(r'^/(\d+)$'), handle_error_code))
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("help", help_command))
dispatcher.add_handler(CommandHandler("list", list_command))
dispatcher.add_handler(CommandHandler("refresh", refresh_cache))
dispatcher.add_handler(CommandHandler("qtgsttp", qtgsttp))
dispatcher.add_handler(CommandHandler("htktm1", htktm1))
dispatcher.add_handler(CommandHandler("ktdb", ktdb))
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