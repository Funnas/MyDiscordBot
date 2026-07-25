import os
import time
import asyncio
import discord
from discord.ext import tasks
from dotenv import load_dotenv
from google import genai
from google.genai import types
import json
from datetime import datetime, timezone, timedelta
import re
import io
import base64
from keep_alive import keep_alive

# Gọi hàm mở cổng web trước khi bot chạy
keep_alive()

# --- Phần code chạy bot Discord hiện tại của bạn ở dưới ---
# Ví dụ:
# bot.run(os.getenv("DISCORD_TOKEN"))

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# =================================================================
# 💾 RELATIONSHIP STORAGE - Nhớ mối quan hệ người dùng
# =================================================================
RELATIONSHIPS_FILE = "user_relationships.json"

def load_relationships():
    """Load dữ liệu mối quan hệ từ file"""
    if os.path.exists(RELATIONSHIPS_FILE):
        try:
            with open(RELATIONSHIPS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_relationships(data):
    """Lưu dữ liệu mối quan hệ vào file"""
    with open(RELATIONSHIPS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# Load từ đầu
relationships = load_relationships()

def get_relationship_tier(user_id):
    """
    Xác định tier mối quan hệ
    0: Funnas (người thân nhất) - ưu tiên tuyệt đối
    1: Bạn thân (đã giới thiệu tên thật) - dịu dàng
    2: Bạn tốt (chat 5+ lần) - bình thường ấm
    3: Bạn bình thường (mọi người khác) - lạnh lùng
    """
    user_key = str(user_id)
    funnas_id = os.getenv('ID_CUA_FUNNAS', '1063688314563080272')
    
    if str(user_id) == str(funnas_id):
        return 0
    
    if user_key in relationships:
        rel = relationships[user_key]
        if rel.get('real_name'):
            return 1
        chat_count = rel.get('chat_count', 0)
        if chat_count >= 5:
            return 2
    
    return 3

def increment_chat_count(user_id, real_name=None):
    """Tăng số lần chat, cập nhật tên thật nếu phát hiện"""
    user_key = str(user_id)
    if user_key not in relationships:
        relationships[user_key] = {'chat_count': 0, 'real_name': None}
    
    relationships[user_key]['chat_count'] = relationships[user_key].get('chat_count', 0) + 1
    
    if real_name:
        relationships[user_key]['real_name'] = real_name
    
    save_relationships(relationships)

def get_user_name(user_id):
    """Lấy tên thật nếu có, nếu không lấy display name"""
    user_key = str(user_id)
    if user_key in relationships and relationships[user_key].get('real_name'):
        return relationships[user_key]['real_name']
    return None

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

# ⚡ GEMINI 3.0+ MODELS
MODELS_TO_TRY = [
    "gemini-3-flash-preview",
    "gemini-3.1-pro-preview",
    "gemini-3.1-flash-lite-preview",
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
# 🕐 TIMEZONE - Múi giờ Việt Nam (UTC+7)
# =================================================================
VN_TZ = timezone(timedelta(hours=7))

def get_vn_time():
    """Lấy thời gian hiện tại ở VN"""
    return datetime.now(VN_TZ)

def format_vn_time(dt):
    """Format thời gian kiểu VN"""
    return dt.strftime("%H:%M:%S")

# =================================================================
# 🖼️ IMAGE PROCESSING - Xử lý hình ảnh
# =================================================================
async def process_image_attachment(attachment):
    """
    Tải và xử lý ảnh từ attachment
    Trả về base64 encoded image hoặc None nếu fail
    """
    try:
        if not attachment.filename:
            return None
        
        # Chỉ xử lý ảnh
        if not any(attachment.filename.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
            return None
        
        # Tải ảnh
        image_data = await attachment.read()
        base64_image = base64.b64encode(image_data).decode('utf-8')
        
        # Xác định media type
        filename_lower = attachment.filename.lower()
        if filename_lower.endswith('.png'):
            media_type = "image/png"
        elif filename_lower.endswith(('.jpg', '.jpeg')):
            media_type = "image/jpeg"
        elif filename_lower.endswith('.gif'):
            media_type = "image/gif"
        elif filename_lower.endswith('.webp'):
            media_type = "image/webp"
        else:
            return None
        
        return {
            'base64': base64_image,
            'media_type': media_type
        }
    except Exception as e:
        print(f"❌ Lỗi xử lý ảnh: {e}")
        return None

# =================================================================
# 🔍 HÀM KIỂM TRA MODEL
# =================================================================
def kiem_tra_model_kha_dung():
    """Kiểm tra model nào khả dụng từ danh sách Gemini 3.0+"""
    global SELECTED_MODEL
    
    if not API_KEYS:
        raise ValueError("❌ FATAL: Không tìm thấy API Key nào trong ENV!")
    
    print("🔍 Đang kiểm tra các model Gemini 3.0+...")
    
    for i, model in enumerate(MODELS_TO_TRY, 1):
        try:
            test_client = genai.Client(api_key=API_KEYS[0])
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
    
    raise ValueError(
        f"❌ FATAL: Không có model nào khả dụng!\n"
        f"   Đã thử: {', '.join(MODELS_TO_TRY)}\n"
        f"   → Hãy kiểm tra API Key"
    )

# =================================================================
# 🚀 HÀM KHỞI TẠO GEMINI 3.0+
# =================================================================
def khoi_tao_gemini(existing_history=None):
    """Khởi tạo chat session mới với model đã chọn"""
    global ai_client, current_key_index, SELECTED_MODEL
    
    if not SELECTED_MODEL:
        kiem_tra_model_kha_dung()
    
    if not API_KEYS:
        raise ValueError("❌ FATAL: Không có API Key nào!")
    
    active_key = API_KEYS[current_key_index]
    ai_client = genai.Client(api_key=active_key)
    
    trimmed_history = existing_history[-3:] if existing_history else None
    
    new_session = ai_client.chats.create(
    model=SELECTED_MODEL,
    config=types.GenerateContentConfig(
        system_instruction=TINH_CACH_NHAN_VAT,
        caching_config={"ttl": "3600s"}  # Cache 1 hour
    ),
    history=trimmed_history
)
    
    print(f"🔄 Khởi tạo chat với '{SELECTED_MODEL}' (API Key #{current_key_index + 1})")
    return new_session

# =================================================================
# 🎯 BIẾN TOÀN CỤC DISCORD
# =================================================================
ID_KENH_CHAT = 1529857332916256800
ID_CUA_FUNNAS = int(os.getenv('ID_CUA_FUNNAS', '1063688314563080272'))
last_chat_time = time.time()

# ⚡ KHỞI TẠO
print("=" * 60)
print("🤖 SEMPAI DISCORD BOT - UPGRADED V2")
print("=" * 60)

try:
    kiem_tra_model_kha_dung()
    chat_session = khoi_tao_gemini()
    print(f"✅ BOT SẴN SÀNG! Model: {SELECTED_MODEL}")
    print(f"📌 Relationship System: ENABLED")
    print(f"📌 Image Recognition: ENABLED")
    print(f"📌 Timezone: VN (UTC+7)\n")
except Exception as e:
    print(f"❌ LỖI KHỞI TẠO: {e}")
    exit(1)

# Discord Client
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# =================================================================
# 💬 AUTO-CHAT - Tự động nhắn sau 30 phút không có tin (đã sửa từ 3600s)
# =================================================================
@tasks.loop(minutes=15)
async def check_chan_nan():
    """Kiểm tra mỗi 15 phút, nếu 30 phút không có tin → tự động chat"""
    global last_chat_time, chat_session, current_key_index
    
    if time.time() - last_chat_time > 1800:  # 1800 giây = 30 phút (đã sửa)
        channel = client.get_channel(int(ID_KENH_CHAT))
        if channel:
            try:
                prompt = "[Hệ thống: TỰ ĐỘNG BẮT CHUYỆN. Đã 30 phút không ai nhắn, hãy than chán hoặc tìm Funnas.]"
                
                response = None
                for attempt in range(len(API_KEYS)):
                    try:
                        response = await asyncio.to_thread(chat_session.send_message, prompt)
                        break
                    except Exception as e:
                        error_str = str(e)
                        
                        if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                            current_key_index = (current_key_index + 1) % len(API_KEYS)
                            print(f"⚠️ Key #{current_key_index} hết quota! Chuyển sang Key #{current_key_index + 1}")
                            old_history = chat_session.history if hasattr(chat_session, 'history') else []
                            chat_session = khoi_tao_gemini(old_history)
                        
                        elif "404" in error_str or "NOT_FOUND" in error_str:
                            print(f"❌ Model '{SELECTED_MODEL}' không tồn tại!")
                            raise e
                        
                        else:
                            print(f"⚠️ Lỗi auto-chat (attempt {attempt + 1}): {error_str[:100]}")
                            if attempt == len(API_KEYS) - 1:
                                raise e

                if response:
                    await channel.send(response.text)
                    last_chat_time = time.time()
                    
            except Exception as e:
                print(f"❌ Lỗi auto-chat: {e}")

# =================================================================
# 🟢 BOT ONLINE
# =================================================================
@client.event
async def on_ready():
    print(f"❤️ {client.user.name} đã online!")
    print(f"📌 Model: {SELECTED_MODEL}")
    print(f"📌 Keys: {len(API_KEYS)} API keys\n")
    
    if not check_chan_nan.is_running():
        check_chan_nan.start()

# =================================================================
# 💭 BOT NHẬN TIN NHẮN
# =================================================================
@client.event
async def on_message(message):
    """Xử lý tin nhắn từ DM hoặc mention"""
    global last_chat_time, chat_session, current_key_index
    
    if message.author == client.user:
        return

    if isinstance(message.channel, discord.DMChannel) or client.user.mentioned_in(message):
        user_msg = message.content.replace(f'<@{client.user.id}>', '').strip()
        if not user_msg:
            return

        async with message.channel.typing():
            try:
                # 📊 Cập nhật thống kê chat
                thoi_gian_troi_qua = time.time() - last_chat_time
                la_tin_nhan_moi = thoi_gian_troi_qua > 1800
                last_chat_time = time.time()
                
                # 👤 Xác định mối quan hệ
                tier = get_relationship_tier(message.author.id)
                user_real_name = get_user_name(message.author.id)
                display_name = message.author.display_name
                
                # Phát hiện nếu trong message có giới thiệu tên thật
                # Ví dụ: "Tôi là [Tên]" hoặc "Gọi tôi là [Tên]"
                name_patterns = [
                    r'(?:tôi là|gọi tôi là|mình là|em là)\s+([A-Za-zÀ-ỿ\s]+?)(?:\.|,|$)',
                    r'(?:tên|tên của tôi|tên em|tên mình)\s+(?:là|nè|đó)\s+([A-Za-zÀ-ỿ\s]+?)(?:\.|,|$)'
                ]
                
                detected_name = None
                for pattern in name_patterns:
                    match = re.search(pattern, user_msg, re.IGNORECASE)
                    if match:
                        detected_name = match.group(1).strip()
                        if detected_name:
                            increment_chat_count(message.author.id, detected_name)
                            user_real_name = detected_name
                            break
                
                if not detected_name:
                    increment_chat_count(message.author.id)
                
                # 💬 Tạo system prompt động theo tier
                loi_nhac_he_thong = f"[Hệ thống: Người đang chat là {user_real_name or display_name}. "
                
                if tier == 0:  # Funnas
                    loi_nhac_he_thong += "Đây là Funnas - người thân nhất của bạn, hãy đối xử cực kỳ thân thiết, ưu tiên tuyệt đối, ngọt ngào nhưng vẫn giữ được tính cách. "
                elif tier == 1:  # Bạn thân
                    loi_nhac_he_thong += f"Đây là bạn thân - {user_real_name}. Hãy dịu dàng, thân thiết hơn, nhưng vẫn giữ cách nói ngắn gọn và tính cách lạnh lùng. "
                elif tier == 2:  # Bạn tốt
                    loi_nhac_he_thong += f"Đây là bạn tốt - {display_name}. Hãy bình thường, ấm áp một chút, không quá lạnh lùng như với người lạ. "
                else:  # Bạn bình thường / mọi người
                    loi_nhac_he_thong += "Đây là người mới, hãy giữ thái độ lạnh lùng, nói ngắn, khó đoán cảm xúc. "
                
                if la_tin_nhan_moi:
                    loi_nhac_he_thong += "BẮT ĐẦU TRÒ CHUYỆN. "
                
                loi_nhac_he_thong += "] "
                
                # 🖼️ Xử lý ảnh nếu có
                image_content = None
                if message.attachments:
                    for attachment in message.attachments:
                        img = await process_image_attachment(attachment)
                        if img:
                            image_content = img
                            user_msg += f" [Ảnh được gửi: {attachment.filename}]"
                            break
                
                # 🕐 Thêm thời gian hiện tại vào prompt (cho bot biết múi giờ)
                vn_time = get_vn_time()
                if any(word in user_msg.lower() for word in ['mấy giờ', 'giờ', 'time']):
                    time_info = f"[Thời gian VN: {vn_time.strftime('%H:%M:%S')}]"
                    tin_nhan_gui_ai = loi_nhac_he_thong + time_info + "\n" + user_msg
                else:
                    tin_nhan_gui_ai = loi_nhac_he_thong + user_msg
                
                # 🔄 Gửi tin đến AI
                response = None
                for attempt in range(len(API_KEYS)):
                    try:
                        if image_content:
                            # Gửi với ảnh
                            response = await asyncio.to_thread(
                                lambda: chat_session.send_message(
                                    content=[
                                        tin_nhan_gui_ai,
                                        types.Part.from_data(
                                            data=image_content['base64'],
                                            mime_type=image_content['media_type']
                                        )
                                    ]
                                )
                            )
                        else:
                            response = await asyncio.to_thread(chat_session.send_message, tin_nhan_gui_ai)
                        break
                        
                    except Exception as e:
                        error_str = str(e)
                        
                        if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                            current_key_index = (current_key_index + 1) % len(API_KEYS)
                            print(f"⚠️ Key #{current_key_index} hết quota!")
                            old_history = chat_session.history if hasattr(chat_session, 'history') else []
                            chat_session = khoi_tao_gemini(old_history)
                        
                        elif "404" in error_str or "NOT_FOUND" in error_str:
                            print(f"❌ Model '{SELECTED_MODEL}' không tồn tại!")
                            raise e
                        
                        else:
                            print(f"⚠️ Lỗi (attempt {attempt + 1}): {error_str[:100]}")
                            if attempt == len(API_KEYS) - 1:
                                raise e

                # 📤 Gửi response
                if response:
                    await message.reply(response.text)
                else:
                    await message.reply("Hmm~, tất cả các kho lưu trữ đều cạn kiệt rồi...")
                
            except Exception as e:
                print(f"❌ Lỗi: {e}")
                await message.reply("Hmm~, có chuyện gì đó không ổn...")

# =================================================================
# 🚀 CHẠY BOT
# =================================================================
if __name__ == "__main__":
    client.run(TOKEN)
