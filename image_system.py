"""
image_system.py
=================================================================
Tách riêng khỏi main.py — Toàn bộ logic liên quan tới ẢNH/VIDEO:

1. process_image_attachment()  -> ĐỌC ảnh Discord gửi (file đính
   kèm, tải trực tiếp qua discord.py)

2. process_video_attachment()  -> ĐỌC video Discord gửi (cùng cơ
   chế như ảnh, Gemini "xem" được video qua inline bytes, chỉ khác
   mime_type + có giới hạn kích thước vì video ăn token nhiều hơn)

3. download_image_from_url()   -> ĐỌC ảnh Messenger gửi (Facebook
   chỉ cung cấp URL ảnh qua webhook, không phải file đính kèm, nên
   cần tải về bằng HTTP request)

4. extract_image_tag()         -> Sempai TỰ GỬI ảnh có sẵn.
   AI tự chèn tag ẩn [IMG:ten_tag] ở cuối câu trả lời khi thấy
   ngữ cảnh phù hợp (không tốn thêm API call nào, chỉ thêm vài
   token cho cái tag). Code ở đây tách tag ra khỏi text hiển thị
   và map sang file ảnh tương ứng để gửi kèm.

Cả (1), (2), (3) đều trả về CÙNG 1 format: {'data': bytes, 'media_type': str}
để chat_core.py xử lý giống nhau, không cần biết media đến từ đâu
hay là ảnh hay video.
=================================================================
"""
import os
import random
import re

import requests

# =================================================================
# 🖼️ ĐỌC ẢNH USER GỬI (giữ nguyên logic cũ)
# =================================================================
async def process_image_attachment(attachment):
    """
    Tải và xử lý ảnh từ attachment Discord.
    Trả về {'data': bytes_anh_tho, 'media_type':...} hoặc None nếu
    không phải ảnh/fail.

    LƯU Ý: 'data' là bytes THÔ, không phải base64 string — SDK
    google-genai (types.Part.from_bytes) tự lo việc encode khi gửi
    request lên API, không cần encode tay ở đây.
    """
    try:
        if not attachment.filename:
            return None

        if not any(attachment.filename.lower().endswith(ext)
                   for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
            return None

        image_data = await attachment.read()

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

        return {'data': image_data, 'media_type': media_type}
    except Exception as e:
        print(f"❌ Lỗi xử lý ảnh: {e}")
        return None


# =================================================================
# 🎬 ĐỌC VIDEO USER GỬI — Gemini "xem" được video qua inline bytes
# y hệt cơ chế ảnh, chỉ khác extension/mime_type + giới hạn size
# =================================================================
VIDEO_EXTENSIONS_MIME = {
    '.mp4': 'video/mp4',
    '.mov': 'video/quicktime',
    '.webm': 'video/webm',
    '.avi': 'video/x-msvideo',
    '.mkv': 'video/x-matroska',
}

# Video ăn RẤT nhiều token hơn ảnh (mỗi giây video ~ nhiều frame),
# giới hạn kích thước để tránh request quá nặng/tốn quota bất ngờ.
MAX_VIDEO_BYTES = 15 * 1024 * 1024  # 15 MB


async def process_video_attachment(attachment):
    """
    Tải và xử lý VIDEO từ attachment Discord.
    Trả về CÙNG FORMAT với process_image_attachment():
    {'data': bytes_video_tho, 'media_type': str} hoặc None nếu
    không phải video / quá lớn / fail.
    """
    try:
        if not attachment.filename:
            return None

        filename_lower = attachment.filename.lower()
        media_type = None
        for ext, mime in VIDEO_EXTENSIONS_MIME.items():
            if filename_lower.endswith(ext):
                media_type = mime
                break

        if not media_type:
            return None

        if attachment.size and attachment.size > MAX_VIDEO_BYTES:
            print(f"⚠️ Video '{attachment.filename}' quá lớn "
                  f"({attachment.size} bytes > {MAX_VIDEO_BYTES}), bỏ qua.")
            return None

        video_data = await attachment.read()
        return {'data': video_data, 'media_type': media_type}
    except Exception as e:
        print(f"❌ Lỗi xử lý video: {e}")
        return None


# =================================================================
# 🖼️ ĐỌC ẢNH MESSENGER GỬI (Facebook gửi URL, không phải file)
# =================================================================
def download_image_from_url(url):
    """
    Tải ảnh từ URL (Messenger webhook chỉ cung cấp URL, không gửi
    file đính kèm trực tiếp như Discord).

    Trả về CÙNG FORMAT với process_image_attachment():
    {'data': bytes_anh_tho, 'media_type': str} hoặc None nếu fail.
    """
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()

        content_type = resp.headers.get('Content-Type', 'image/jpeg').lower()
        if 'png' in content_type:
            media_type = 'image/png'
        elif 'gif' in content_type:
            media_type = 'image/gif'
        elif 'webp' in content_type:
            media_type = 'image/webp'
        else:
            media_type = 'image/jpeg'

        return {'data': resp.content, 'media_type': media_type}
    except Exception as e:
        print(f"❌ Lỗi tải ảnh từ URL Messenger: {e}")
        return None


# =================================================================
# 📤 SEMPAI TỰ GỬI ẢNH — Tag-based (AI tự quyết định ngữ cảnh)
# =================================================================
IMAGES_DIR = "images"

# Map tag -> danh sách ảnh (nhiều ảnh/tag để random, đỡ lặp lại nhàm)
# Thêm/sửa/xóa tag tại đây, nhớ thêm hướng dẫn dùng tag tương ứng
# trong tinh_cach.txt (phần "HỆ THỐNG TAG ẢNH")
IMAGE_MAP = {
    "happy_food": ["Giving_soda.jpg"],
    "Talk": ["Talk.png"],
    "worried": ["Head_ache.jpg"],
    "shy": ["Shy.jpg"],
    "annoyed": ["Stun_mind.jpg"],
    "phone": ["LookinPhone.jpg"],
    "friendly": ["friendly_finger.jpg"],
    "eyes": ["lovely_eyes.jpg"],
    "home": ["normal_outfit(home).jpg"],
}

# Lookup không phân biệt hoa/thường — AI có thể viết [IMG:talk] hay
# [IMG:Talk] đều khớp được, tránh miss do lệch chữ hoa/thường.
_IMAGE_MAP_LOWER = {k.lower(): v for k, v in IMAGE_MAP.items()}

# Xác suất THỰC SỰ gửi ảnh khi tag đó xuất hiện (0.0 - 1.0).
# Tag không có trong đây mặc định = 1.0 (luôn gửi khi AI chèn tag).
# Dùng để giảm tần suất 1 tag cụ thể mà không cần sửa tinh_cach.txt
# (vì AI không tuân theo tỉ lệ % chính xác được, code random mới
# đảm bảo đúng con số).
#
# "phone": 0.3 -> chỉ thực sự gửi ảnh 30% số lần AI chèn tag này,
# tức GIẢM TẦN SUẤT 70% so với trước (tag vẫn bị xóa khỏi text như
# thường trong 70% còn lại, chỉ là không đính kèm ảnh lần đó).
TAG_SEND_PROBABILITY = {
    "phone": 0.3,
}

IMG_TAG_PATTERN = re.compile(r'\[IMG:(\w+)\]')


def extract_image_tag(response_text):
    """
    Tách tag [IMG:xxx] khỏi câu trả lời AI.
    Trả về (clean_text, duong_dan_anh_hoac_None)

    - clean_text: text đã xóa tag, dùng để hiển thị cho user
      (user KHÔNG BAO GIỜ thấy tag [IMG:...] trong tin nhắn)
    - duong_dan_anh: path file ảnh để gửi kèm, None nếu không có
      tag / tag không map được ảnh / file ảnh không tồn tại / bị
      random loại do TAG_SEND_PROBABILITY (tag vẫn bị xóa khỏi
      text bình thường, chỉ là lần đó không đính kèm ảnh)
    """
    match = IMG_TAG_PATTERN.search(response_text)
    clean_text = IMG_TAG_PATTERN.sub('', response_text).strip()

    if not match:
        return clean_text, None

    tag = match.group(1)
    tag_lower = tag.lower()

    candidates = _IMAGE_MAP_LOWER.get(tag_lower)
    if not candidates:
        print(f"⚠️ Tag ảnh '{tag}' không có trong IMAGE_MAP, bỏ qua.")
        return clean_text, None

    # 🎲 Kiểm tra xác suất gửi ảnh (mặc định 1.0 = luôn gửi nếu không config)
    probability = TAG_SEND_PROBABILITY.get(tag_lower, 1.0)
    if random.random() > probability:
        print(f"🎲 Tag '{tag}' bị random bỏ qua gửi ảnh (probability={probability}).")
        return clean_text, None

    chosen = random.choice(candidates)
    path = os.path.join(IMAGES_DIR, chosen)

    if not os.path.exists(path):
        print(f"⚠️ File ảnh '{path}' không tồn tại (đã config tag nhưng thiếu file), gửi text thôi.")
        return clean_text, None

    return clean_text, path
