import os
import time
import asyncio
import discord
from discord.ext import tasks
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# =================================================================
# ⚙️ GEMINI 3.0+ API KEYS & HISTORY MANAGEMENT
# =================================================================
API_KEYS = [
    os.getenv('GEMINI_KEY_1'),
    os.getenv('GEMINI_KEY_2'),
    os.getenv('GEMINI_KEY_3'),
    os.getenv('GEMINI_KEY_4')
]
API_KEYS = [key for key in API_KEYS if key]

current_key_index = 0
ai_client = None
chat_session = None

# ⚡ GEMINI 3.0+ MODELS (Thứ tự ưu tiên)
# 📌 Tất cả model cũ (2.0, 2.5, 1.5) đã deprecated ngày 1/6/2026
MODELS_TO_TRY = [
    "gemini-3-flash-preview",        # ✅ Flash tốc độ cao (recommended cho bot chat)
    "gemini-3.1-pro-preview",        # ✅ Pro thông minh nhất
    "gemini-3.1-flash-lite-preview", # ✅ Flash-Lite tiết kiệm
]
SELECTED_MODEL = None

# Load tính cách từ file
try:
    with open('tinh_cach.txt', 'r', encoding='utf-8') as file:
        TINH_CACH_NHAN_VAT = file.read()
except FileNotFoundError:
    print("⚠️ Không tìm file 'tinh_cach.txt', dùng prompt mặc định")
    TINH_CACH_NHAN_VAT = "Bạn là trợ lý AI."

# =================================================================
# 🔍 HÀM KIỂM TRA MODEL GEMINI 3.0+ KHẢ DỤNG
# =================================================================
def kiem_tra_model_kha_dung():
    """
    Kiểm tra model nào khả dụng từ danh sách Gemini 3.0+
    Trả về model đầu tiên khả dụng hoặc raise lỗi nếu tất cả fail
    """
    global SELECTED_MODEL
    
    if not API_KEYS:
        raise ValueError("❌ FATAL: Không tìm thấy API Key nào trong ENV!")
    
    print("🔍 Đang kiểm tra các model Gemini 3.0+...")
    
    for i, model in enumerate(MODELS_TO_TRY, 1):
        try:
            test_client = genai.Client(api_key=API_KEYS[0])
            # Tạo session test để xác nhận model khả dụng
            test_session = test_client.chats.create(
                model=model,
                config=types.GenerateContentConfig(
                    system_instruction="Test"
                )
            )
            SELECTED_MODEL = model
            print(f"✅ [{i}/{len(MODELS_TO_TRY)}] Model '{model}' khả dụng!")
            return model
        except Exception as e:
            error_msg = str(e)
            print(f"❌ [{i}/{len(MODELS_TO_TRY)}] Model '{model}' không khả dụng")
            if "404" in error_msg or "NOT_FOUND" in error_msg:
                print(f"   └─ Lý do: Model này không tồn tại (deprecated?)")
            else:
                print(f"   └─ Lý do: {error_msg[:100]}")
            continue
    
    # Nếu tất cả fail
    raise ValueError(
        f"❌ FATAL: Không có model nào khả dụng!\n"
        f"   Đã thử: {', '.join(MODELS_TO_TRY)}\n"
        f"   → Hãy kiểm tra API Key trên: https://aistudio.google.com/app/apikey"
    )

# =================================================================
# 🚀 HÀM KHỞI TẠO GEMINI 3.0+ CHAT SESSION
# =================================================================
def khoi_tao_gemini(existing_history=None):
    """
    Khởi tạo chat session mới với model đã chọn
    - Đồng bộ history gần nhất (tối đa 10 tin nhắn)
    - Dùng API key hiện tại
    - Áp dụng system instruction tính cách
    """
    global ai_client, current_key_index, SELECTED_MODEL
    
    # Double-check model đã được chọn
    if not SELECTED_MODEL:
        kiem_tra_model_kha_dung()
    
    if not API_KEYS:
        raise ValueError("❌ FATAL: Không có API Key nào!")
    
    # Lấy API key hiện tại
    active_key = API_KEYS[current_key_index]
    ai_client = genai.Client(api_key=active_key)
    
    # Cắt gọn history chỉ lấy 10 tin nhắn gần nhất (tiết kiệm token)
    trimmed_history = existing_history[-10:] if existing_history else None
    
    # ✅ Tạo session với Gemini 3.0+
    new_session = ai_client.chats.create(
        model=SELECTED_MODEL,  # Dùng model được xác nhận
        config=types.GenerateContentConfig(
            system_instruction=TINH_CACH_NHAN_VAT
        ),
        history=trimmed_history
    )
    
    print(f"🔄 Khởi tạo chat với '{SELECTED_MODEL}' (API Key #{current_key_index + 1})")
    return new_session

# =================================================================
# 🎯 BIẾN TOÀN CỤC DISCORD
# =================================================================
ID_KENH_CHAT = 1529857332916256800
ID_CUA_FUNNAS = 1063688314563080272
last_chat_time = time.time()

# ⚡ KHỞI TẠO CHAT SESSION NGAY KHI SCRIPT CHẠY
print("=" * 60)
print("🤖 SEMPAI DISCORD BOT - GEMINI 3.0+ VERSION")
print("=" * 60)

try:
    kiem_tra_model_kha_dung()  # Tìm model khả dụng
    chat_session = khoi_tao_gemini()  # Tạo session
    print(f"✅ BOT SẴN SÀNG! Model: {SELECTED_MODEL}\n")
except Exception as e:
    print(f"❌ LỖI KHỞI TẠO: {e}")
    exit(1)

# Discord Client
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# =================================================================
# 💬 AUTO-CHAT - Tự động nói chuyện sau 1 giờ không có tin
# =================================================================
@tasks.loop(minutes=15)
async def check_chan_nan():
    """Kiểm tra mỗi 15 phút, nếu 1h không có tin → tự động chat"""
    global last_chat_time, chat_session, current_key_index
    
    if time.time() - last_chat_time > 3600:  # 3600 giây = 1 giờ
        channel = client.get_channel(int(ID_KENH_CHAT))
        if channel:
            try:
                prompt = "[Hệ thống: TỰ ĐỘNG BẮT CHUYỆN. Đã hơn 1 tiếng không ai nhắn, hãy than chán hoặc tìm Funnas.]"
                
                response = None
                for attempt in range(len(API_KEYS)):
                    try:
                        response = await asyncio.to_thread(chat_session.send_message, prompt)
                        break  # ✅ Thành công, thoát loop
                    except Exception as e:
                        error_str = str(e)
                        
                        # 🔄 Nếu key hết quota → chuyển key
                        if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                            current_key_index = (current_key_index + 1) % len(API_KEYS)
                            print(f"⚠️ Key #{current_key_index} hết quota! Chuyển sang Key #{current_key_index + 1}")
                            old_history = chat_session.history if hasattr(chat_session, 'history') else []
                            chat_session = khoi_tao_gemini(old_history)
                        
                        # ❌ Nếu model không tồn tại → fatal error
                        elif "404" in error_str or "NOT_FOUND" in error_str:
                            print(f"❌ Model '{SELECTED_MODEL}' không tồn tại! Đã bị deprecated?")
                            raise e
                        
                        # Lỗi khác → log và retry
                        else:
                            print(f"⚠️ Lỗi gửi tin tự động (attempt {attempt + 1}): {error_str[:100]}")
                            if attempt == len(API_KEYS) - 1:
                                raise e

                if response:
                    await channel.send(response.text)
                    last_chat_time = time.time()
                    
            except Exception as e:
                print(f"❌ Lỗi auto-chat: {e}")

# =================================================================
# 🟢 BOT ONLINE - Bắt đầu auto-check
# =================================================================
@client.event
async def on_ready():
    print(f"❤️ {client.user.name} đã online!")
    print(f"📌 Model: {SELECTED_MODEL}")
    print(f"📌 Keys: {len(API_KEYS)} API keys sẵn sàng\n")
    
    if not check_chan_nan.is_running():
        check_chan_nan.start()

# =================================================================
# 💭 BOT NHẬN TIN NHẮN - Xử lý chat
# =================================================================
@client.event
async def on_message(message):
    """
    Xử lý tin nhắn từ:
    1. DM (Direct Message)
    2. Mention (@bot)
    """
    global last_chat_time, chat_session, current_key_index
    
    # Bỏ qua tin nhắn của chính bot
    if message.author == client.user:
        return

    # Chỉ xử lý DM hoặc khi bot được mention
    if isinstance(message.channel, discord.DMChannel) or client.user.mentioned_in(message):
        # Trích xuất tin nhắn (xóa mention)
        user_msg = message.content.replace(f'<@{client.user.id}>', '').strip()
        if not user_msg:
            return

        async with message.channel.typing():
            try:
                # Kiểm tra: Đây có phải tin nhắn mới sau 30 phút không?
                thoi_gian_troi_qua = time.time() - last_chat_time
                la_tin_nhan_moi = thoi_gian_troi_qua > 1800  # 1800 giây = 30 phút
                last_chat_time = time.time()
                
                # Xác định người nói chuyện
                la_funnas = (message.author.id == int(ID_CUA_FUNNAS))
                ten_nguoi_nhan = "Funnas (Chủ nhân tối cao)" if la_funnas else message.author.display_name

                # ✅ Tạo system prompt động
                loi_nhac_he_thong = f"[Hệ thống: Người đang nói chuyện là {ten_nguoi_nhan}. "
                if la_funnas:
                    loi_nhac_he_thong += "Đây là MAIN/chủ nhân của bạn, hãy đối xử cực kỳ thân thiết, ưu tiên tuyệt đối và ngọt ngào. "
                else:
                    loi_nhac_he_thong += "Đây chỉ là người khác trong server, hãy trả lời đầy đủ nhưng có thể phũ phàng, cục súc hoặc lạnh lùng hơn, tuyệt đối không được quá dễ dãi như với Funnas. "
                
                if la_tin_nhan_moi:
                    loi_nhac_he_thong += "BẮT ĐẦU TRÒ CHUYỆN. "
                loi_nhac_he_thong += "] "

                tin_nhan_gui_ai = loi_nhac_he_thong + user_msg

                # 🔄 Gửi tin đến AI
                response = None
                for attempt in range(len(API_KEYS)):
                    try:
                        response = await asyncio.to_thread(chat_session.send_message, tin_nhan_gui_ai)
                        break  # ✅ Thành công!
                        
                    except Exception as e:
                        error_str = str(e)
                        
                        # 🔄 Key hết quota → chuyển key
                        if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                            current_key_index = (current_key_index + 1) % len(API_KEYS)
                            print(f"⚠️ Key #{current_key_index} hết quota! Chuyển sang Key #{current_key_index + 1}")
                            old_history = chat_session.history if hasattr(chat_session, 'history') else []
                            chat_session = khoi_tao_gemini(old_history)
                        
                        # ❌ Model không tồn tại → fatal
                        elif "404" in error_str or "NOT_FOUND" in error_str:
                            print(f"❌ Model '{SELECTED_MODEL}' không tồn tại!")
                            raise e
                        
                        # Lỗi khác
                        else:
                            print(f"⚠️ Lỗi message (attempt {attempt + 1}): {error_str[:100]}")
                            if attempt == len(API_KEYS) - 1:
                                raise e

                # 📤 Gửi response
                if response:
                    await message.reply(response.text)
                else:
                    await message.reply("Hmm~, tất cả các kho lưu trữ đều cạn kiệt rồi, từ từ đã!")
                
            except Exception as e:
                print(f"❌ Lỗi xử lý message: {e}")
                await message.reply("Hmm~, mạng lag chút, nói lại xem nào!")

# =================================================================
# 🚀 CHẠY BOT
# =================================================================
if __name__ == "__main__":
    client.run(TOKEN)