import os

# 🛡️ Mở keep_alive TRƯỚC TIÊN — nếu 1 trong các import phía dưới bị lỗi
# (VD: đặt sai tên file module), Flask server này vẫn kịp chạy, giữ
# Render không bị coi là "không traffic" và tắt hẳn. Nhờ vậy UptimeRobot
# vẫn ping được, có thời gian xem log sửa lỗi thay vì bot biến mất luôn.
from keep_alive import keep_alive
keep_alive()

import time
import asyncio
import discord
from discord.ext import tasks
from dotenv import load_dotenv
from google import genai
from google.genai import types
from datetime import datetime, timezone, timedelta

import memory_system as mem
import image_system as img
import autochat_system as autochat

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# =================================================================
# ⚙️ GEMINI 3.0+ API KEYS & HISTORY MANAGEMENT
# =================================================================
API_KEYS = [
    os.getenv('GEMINI_KEY_1'),
    os.getenv('GEMINI_KEY_2'),
    os.getenv('GEMINI_KEY_3'),
    os.getenv('GEMINI_KEY_4'),
    os.getenv('GEMINI_KEY_5'),
    os.getenv('GEMINI_KEY_6'),
]
API_KEYS = [key for key in API_KEYS if key]

ai_client = None

# 🔒 TÁCH 2 "NGĂN" LỊCH SỬ HỘI THOẠI RIÊNG BIỆT — private (kênh
# riêng tư #test + DM) và public (mọi kênh khác, VD #general).
# Tách hẳn ở tầng session (không chỉ dặn AI bằng lời) để nội dung
# riêng tư KHÔNG BAO GIỜ lẫn vào context khi trả lời ở kênh chung,
# tránh rò rỉ thật sự chứ không chỉ dựa vào AI "nhớ đừng nói ra".
sessions = {
    "private": {"chat_session": None, "current_key_index": 0},
    "public": {"chat_session": None, "current_key_index": 0},
}

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

# Load thêm file romance.txt (fanservice nhẹ nhàng, tách riêng khỏi
# tinh_cach.txt cho dễ chỉnh sửa). File KHÔNG bắt buộc phải có —
# nếu thiếu, bot vẫn chạy bình thường, chỉ là không có phần này.
try:
    with open('romance.txt', 'r', encoding='utf-8') as file:
        romance_content = file.read()
        TINH_CACH_NHAN_VAT += "\n\n" + romance_content
        print("💕 Đã load romance.txt")
except FileNotFoundError:
    print("ℹ️ Không có file 'romance.txt', bỏ qua (không bắt buộc)")

# =================================================================
# 🕐 TIMEZONE - Múi giờ Việt Nam (UTC+7)
# =================================================================
VN_TZ = timezone(timedelta(hours=7))


def get_vn_time():
    return datetime.now(VN_TZ)


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
            test_client.chats.create(
                model=model,
                config=types.GenerateContentConfig(system_instruction="Test")
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
# 🚀 HÀM KHỞI TẠO GEMINI 3.0+ — theo bucket (private/public)
# =================================================================
def khoi_tao_gemini(bucket, existing_history=None):
    """Khởi tạo/khởi tạo lại chat session cho 1 bucket cụ thể."""
    global ai_client, SELECTED_MODEL

    if not SELECTED_MODEL:
        kiem_tra_model_kha_dung()

    if not API_KEYS:
        raise ValueError("❌ FATAL: Không có API Key nào!")

    state = sessions[bucket]
    active_key = API_KEYS[state["current_key_index"]]
    ai_client = genai.Client(api_key=active_key)

    trimmed_history = existing_history[-3:] if existing_history else None

    new_session = ai_client.chats.create(
        model=SELECTED_MODEL,
        config=types.GenerateContentConfig(
            system_instruction=TINH_CACH_NHAN_VAT,
        ),
        history=trimmed_history
    )

    state["chat_session"] = new_session
    print(f"🔄 Khởi tạo chat [{bucket}] với '{SELECTED_MODEL}' (API Key #{state['current_key_index'] + 1})")
    return new_session


# =================================================================
# 🎯 BIẾN TOÀN CỤC DISCORD
# =================================================================
ID_KENH_CHAT = 1529857332916256800
ID_CUA_FUNNAS = int(os.getenv('ID_CUA_FUNNAS', '1063688314563080272'))

# 🔒 Kênh RIÊNG TƯ (VD #test) — nếu không cấu hình, mọi kênh coi
# như "public" hết (giữ nguyên hành vi cũ, tính năng chỉ bật khi
# có điền ID này).
ID_KENH_RIENG_TU = os.getenv('ID_KENH_RIENG_TU')

last_chat_time = time.time()

# ⚡ KHỞI TẠO
print("=" * 60)
print("🤖 SEMPAI DISCORD BOT - V3 (Modular)")
print("=" * 60)

try:
    kiem_tra_model_kha_dung()
    khoi_tao_gemini("public")
    khoi_tao_gemini("private")
    print(f"✅ BOT SẴN SÀNG! Model: {SELECTED_MODEL}")
    print(f"📌 Relationship System: ENABLED (memory_system.py)")
    print(f"📌 Image + Video Recognition + Auto-send: ENABLED (image_system.py)")
    print(f"📌 Auto-chat streak limit: {autochat.AUTO_STREAK_LIMIT}")
    print(f"📌 Sleep mode window: {autochat.EVENING_START_HOUR}h - {autochat.EVENING_END_HOUR}h (VN)")
    if ID_KENH_RIENG_TU:
        print(f"📌 Kênh riêng tư: ENABLED (channel {ID_KENH_RIENG_TU} + mọi DM)")
    else:
        print(f"📌 Kênh riêng tư: chưa cấu hình (ID_KENH_RIENG_TU rỗng) — chỉ DM được coi là riêng tư")
    print(f"📌 Timezone: VN (UTC+7)\n")
except Exception as e:
    print(f"❌ LỖI KHỞI TẠO: {e}")
    exit(1)


def get_bucket_for_channel(channel):
    """
    Xác định "ngăn" lịch sử hội thoại cho kênh/DM này.
    - DM luôn là "private" (chỉ 2 người, không ai khác thấy)
    - Kênh đúng ID_KENH_RIENG_TU (VD #test) -> "private"
    - Mọi kênh khác -> "public"
    """
    if isinstance(channel, discord.DMChannel):
        return "private"
    if ID_KENH_RIENG_TU and str(getattr(channel, 'id', '')) == str(ID_KENH_RIENG_TU):
        return "private"
    return "public"

# Discord Client
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


# =================================================================
# 🔄 HÀM DÙNG CHUNG: Gửi tin nhắn cho Gemini kèm auto key-rotation
# THEO ĐÚNG BUCKET (private/public) — không lẫn lịch sử 2 ngăn
# =================================================================
async def send_to_gemini(bucket, content):
    """
    Gửi content cho Gemini theo đúng bucket, tự động xoay API key
    khi hết quota, tự raise nếu model không tồn tại.
    """
    state = sessions[bucket]

    for attempt in range(len(API_KEYS)):
        try:
            return await asyncio.to_thread(state["chat_session"].send_message, content)
        except Exception as e:
            error_str = str(e)

            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                state["current_key_index"] = (state["current_key_index"] + 1) % len(API_KEYS)
                print(f"⚠️ [{bucket}] Key #{state['current_key_index']} hết quota! Chuyển key.")
                old_history = state["chat_session"].history if hasattr(state["chat_session"], 'history') else []
                khoi_tao_gemini(bucket, old_history)

            elif "404" in error_str or "NOT_FOUND" in error_str:
                print(f"❌ Model '{SELECTED_MODEL}' không tồn tại!")
                raise e

            else:
                print(f"⚠️ [{bucket}] Lỗi (attempt {attempt + 1}): {error_str[:100]}")
                if attempt == len(API_KEYS) - 1:
                    raise e
    return None



# =================================================================
# 💬 AUTO-CHAT — Tự động nhắn sau 30 phút không có tin
# CÓ 2 CÔNG TẮC: streak limit (autochat_system) + sleep mode
# =================================================================
@tasks.loop(minutes=15)
async def check_chan_nan():
    """Kiểm tra mỗi 15 phút, nếu 30 phút không có tin → tự động chat."""
    global last_chat_time

    if time.time() - last_chat_time <= 1800:
        return

    # 🔧 CÔNG TẮC: sleep mode + streak limit
    allowed, is_final_warning = autochat.can_send_auto_message()
    if not allowed:
        return

    channel = client.get_channel(int(ID_KENH_CHAT))
    if not channel:
        return

    bucket = get_bucket_for_channel(channel)

    try:
        prompt = "[Hệ thống: TỰ ĐỘNG BẮT CHUYỆN. Đã 30 phút không ai nhắn, hãy than chán hoặc tìm Funnas.]"

        if is_final_warning:
            prompt += (
                " [Đây là lần nhắc cuối cùng trước khi im lặng chờ - hãy thêm ý "
                "nhắc Funnas nhớ liên lạc lại với chị, sau đó sẽ không tự nhắn "
                "thêm nữa cho tới khi có người trả lời.]"
            )

        response = await send_to_gemini(bucket, prompt)

        if response:
            # Tách tag [IMG:xxx] như chat thường, tránh lộ tag ra text
            clean_text, image_path = img.extract_image_tag(response.text)

            if image_path:
                await channel.send(content=clean_text, file=discord.File(image_path))
            else:
                await channel.send(clean_text)

            last_chat_time = time.time()
            autochat.record_auto_message_sent()

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
    global last_chat_time

    if message.author == client.user:
        return

    if not (isinstance(message.channel, discord.DMChannel) or client.user.mentioned_in(message)):
        return

    user_msg = message.content.replace(f'<@{client.user.id}>', '').strip()

    # Fix bug: trước đây return sớm nếu user_msg rỗng, kể cả khi có ảnh/video
    # đính kèm => bot không đọc được nếu gửi ảnh/video không kèm chữ.
    if not user_msg and not message.attachments:
        return
    if not user_msg and message.attachments:
        user_msg = "[Người dùng gửi ảnh/video không kèm chữ]"

    bucket = get_bucket_for_channel(message.channel)

    async with message.channel.typing():
        try:
            # 📊 Cập nhật thống kê chat + reset streak auto-chat (có người thật nhắn)
            thoi_gian_troi_qua = time.time() - last_chat_time
            la_tin_nhan_moi = thoi_gian_troi_qua > 1800
            last_chat_time = time.time()
            autochat.reset_streak_on_human_message()

            # 👤 Xác định mối quan hệ (memory_system.py)
            tier = mem.get_relationship_tier(message.author.id, ID_CUA_FUNNAS)
            user_real_name = mem.get_user_name(message.author.id)
            display_name = message.author.display_name

            detected_name = mem.detect_name(user_msg)
            if detected_name:
                mem.increment_chat_count(message.author.id, detected_name)
                user_real_name = detected_name
            else:
                mem.increment_chat_count(message.author.id)

            # 🌙 CÔNG TẮC SLEEP MODE — chỉ Funnas mới kích hoạt/tắt được
            if tier == 0:
                if autochat.is_sleep_mode():
                    if autochat.is_wake_trigger(user_msg):
                        autochat.disable_sleep_mode()
                        last_chat_time = time.time()  # reset countdown 30p từ lúc gọi dậy
                elif autochat.is_evening_vn() and autochat.is_sleep_trigger(user_msg):
                    autochat.enable_sleep_mode()

            # 💬 Tạo system prompt động theo tier
            loi_nhac_he_thong = f"[Hệ thống: Người đang chat là {user_real_name or display_name}. "

            if tier == 0:
                loi_nhac_he_thong += "Đây là Funnas - người thân nhất của bạn, hãy đối xử cực kỳ thân thiết, ưu tiên tuyệt đối, ngọt ngào nhưng vẫn giữ được tính cách. "
            elif tier == 1:
                loi_nhac_he_thong += f"Đây là bạn thân - {user_real_name}. Hãy dịu dàng, thân thiết hơn, nhưng vẫn giữ cách nói ngắn gọn và tính cách lạnh lùng. "
            elif tier == 2:
                loi_nhac_he_thong += f"Đây là bạn tốt - {display_name}. Hãy bình thường, ấm áp một chút, không quá lạnh lùng như với người lạ. "
            else:
                loi_nhac_he_thong += "Đây là người mới, hãy giữ thái độ lạnh lùng, nói ngắn, khó đoán cảm xúc. "

            if la_tin_nhan_moi:
                loi_nhac_he_thong += "BẮT ĐẦU TRÒ CHUYỆN. "

            loi_nhac_he_thong += "] "

            # 🔒 Không gian riêng tư vs chung — chỉ có ý nghĩa khi đang
            # chat với Funnas (tier 0), vì đây là ranh giới bảo mật cho
            # CHÍNH Funnas, không áp dụng khi đang trả lời người khác.
            if tier == 0:
                if bucket == "private":
                    loi_nhac_he_thong += (
                        "[Đang ở không gian RIÊNG TƯ, chỉ có Funnas và bạn, "
                        "không ai khác thấy được — có thể thân mật, ấm áp "
                        "hơn bình thường.] "
                    )
                else:
                    loi_nhac_he_thong += (
                        "[Đang ở kênh CHUNG, có thể có người khác thấy — "
                        "TUYỆT ĐỐI không nhắc lại/tiết lộ bất kỳ điều gì đã "
                        "nói riêng với Funnas ở không gian riêng tư trước đó, "
                        "dù có được hỏi.] "
                    )

            # 📁 Chèn thêm profile context nếu có (memory_system.py)
            profile_context = mem.get_profile_context(message.author.id, ID_CUA_FUNNAS, user_real_name)
            if profile_context:
                loi_nhac_he_thong += profile_context + " "

            # 🖼️🎬 Đọc ảnh/video user gửi nếu có (thử ảnh trước, không match
            # thì thử video — cùng biến image_content vì cả 2 đều cùng
            # format {'data':..., 'media_type':...})
            image_content = None
            if message.attachments:
                for attachment in message.attachments:
                    im = await img.process_image_attachment(attachment)
                    if im:
                        image_content = im
                        user_msg += f" [Ảnh được gửi: {attachment.filename}]"
                        break

                    vid = await img.process_video_attachment(attachment)
                    if vid:
                        image_content = vid
                        user_msg += f" [Video được gửi: {attachment.filename}]"
                        break

            # 🕐 Chỉ thêm giờ VN vào prompt khi user hỏi giờ
            vn_time = get_vn_time()
            if any(word in user_msg.lower() for word in ['mấy giờ', 'giờ', 'time']):
                time_info = f"[Thời gian VN: {vn_time.strftime('%H:%M:%S')}]"
                tin_nhan_gui_ai = loi_nhac_he_thong + time_info + "\n" + user_msg
            else:
                tin_nhan_gui_ai = loi_nhac_he_thong + user_msg

            # 🔄 Gửi tin đến AI
            if image_content:
                response = await send_to_gemini(bucket, [
                    tin_nhan_gui_ai,
                    types.Part.from_bytes(
                        data=image_content['data'],
                        mime_type=image_content['media_type']
                    )
                ])
            else:
                response = await send_to_gemini(bucket, tin_nhan_gui_ai)

            # 📤 Gửi response — tách tag ảnh trước khi hiển thị (image_system.py)
            if response:
                clean_text, image_path = img.extract_image_tag(response.text)

                if image_path:
                    await message.reply(content=clean_text, file=discord.File(image_path))
                else:
                    await message.reply(clean_text)
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
