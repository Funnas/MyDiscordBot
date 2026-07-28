"""
image_system.py
=================================================================
Tách riêng khỏi main.py — Toàn bộ logic liên quan tới ẢNH:

1. process_image_attachment()  -> ĐỌC ảnh user gửi (giữ nguyên
   logic cũ từ main.py, không đổi gì)

2. extract_image_tag()         -> Sempai TỰ GỬI ảnh có sẵn.
   AI tự chèn tag ẩn [IMG:ten_tag] ở cuối câu trả lời khi thấy
   ngữ cảnh phù hợp (không tốn thêm API call nào, chỉ thêm vài
   token cho cái tag). Code ở đây tách tag ra khỏi text hiển thị
   và map sang file ảnh tương ứng để gửi kèm.
=================================================================
"""
import os
import random
import re

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

IMG_TAG_PATTERN = re.compile(r'\[IMG:(\w+)\]')


def extract_image_tag(response_text):
    """
    Tách tag [IMG:xxx] khỏi câu trả lời AI.
    Trả về (clean_text, duong_dan_anh_hoac_None)

    - clean_text: text đã xóa tag, dùng để hiển thị cho user
      (user KHÔNG BAO GIỜ thấy tag [IMG:...] trong tin nhắn)
    - duong_dan_anh: path file ảnh để gửi kèm, None nếu không có
      tag / tag không map được ảnh / file ảnh không tồn tại
    """
    match = IMG_TAG_PATTERN.search(response_text)
    clean_text = IMG_TAG_PATTERN.sub('', response_text).strip()

    if not match:
        return clean_text, None

    tag = match.group(1)
    candidates = _IMAGE_MAP_LOWER.get(tag.lower())
    if not candidates:
        print(f"⚠️ Tag ảnh '{tag}' không có trong IMAGE_MAP, bỏ qua.")
        return clean_text, None

    chosen = random.choice(candidates)
    path = os.path.join(IMAGES_DIR, chosen)

    if not os.path.exists(path):
        print(f"⚠️ File ảnh '{path}' không tồn tại (đã config tag nhưng thiếu file), gửi text thôi.")
        return clean_text, None

    return clean_text, path
