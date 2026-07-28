"""
memory_system.py
=================================================================
Tách riêng khỏi main.py — Quản lý:
1. Tier mối quan hệ (0-3) + lưu chat_count/real_name (JSON)
2. Phát hiện tên thật trong tin nhắn
3. Profile file tĩnh (sở thích viết tay) — my_profile.txt (Funnas)
   và friends/{ten}.txt (bạn bè) — KHÔNG dùng AI để tự detect,
   chỉ đọc file text cậu tự viết/sửa tay.

Không đụng gì tới logic Gemini/Discord chính, main.py chỉ import
và gọi các hàm ở đây.
=================================================================
"""
import os
import json
import re

RELATIONSHIPS_FILE = "user_relationships.json"
MY_PROFILE_FILE = "my_profile.txt"
FRIENDS_DIR = "friends"


# =================================================================
# 💾 RELATIONSHIP STORAGE (JSON) — chat_count + real_name
# =================================================================
def load_relationships():
    """Load dữ liệu mối quan hệ từ file."""
    if os.path.exists(RELATIONSHIPS_FILE):
        try:
            with open(RELATIONSHIPS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_relationships(data):
    """Lưu dữ liệu mối quan hệ vào file."""
    with open(RELATIONSHIPS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


relationships = load_relationships()


def get_relationship_tier(user_id, funnas_id):
    """
    0: Funnas (người thân nhất) - ưu tiên tuyệt đối
    1: Bạn thân (đã giới thiệu tên thật) - dịu dàng
    2: Bạn tốt (chat 5+ lần) - bình thường ấm
    3: Bạn bình thường (mọi người khác) - lạnh lùng
    """
    user_key = str(user_id)

    if str(user_id) == str(funnas_id):
        return 0

    if user_key in relationships:
        rel = relationships[user_key]
        if rel.get('real_name'):
            return 1
        if rel.get('chat_count', 0) >= 5:
            return 2

    return 3


def increment_chat_count(user_id, real_name=None):
    """Tăng số lần chat, cập nhật tên thật nếu phát hiện."""
    user_key = str(user_id)
    if user_key not in relationships:
        relationships[user_key] = {'chat_count': 0, 'real_name': None}

    relationships[user_key]['chat_count'] = relationships[user_key].get('chat_count', 0) + 1

    if real_name:
        relationships[user_key]['real_name'] = real_name

    save_relationships(relationships)


def get_user_name(user_id):
    """Lấy tên thật nếu có, nếu không trả về None (main.py tự fallback display_name)."""
    user_key = str(user_id)
    if user_key in relationships and relationships[user_key].get('real_name'):
        return relationships[user_key]['real_name']
    return None


# =================================================================
# 🔎 PHÁT HIỆN TÊN THẬT TRONG TIN NHẮN
# =================================================================
NAME_PATTERNS = [
    r'(?:tôi là|gọi tôi là|mình là|em là)\s+([A-Za-zÀ-ỿ\s]+?)(?:\.|,|$)',
    r'(?:tên|tên của tôi|tên em|tên mình)\s+(?:là|nè|đó)\s+([A-Za-zÀ-ỿ\s]+?)(?:\.|,|$)'
]


def detect_name(user_msg):
    """Tìm tên thật trong câu, trả về tên hoặc None."""
    for pattern in NAME_PATTERNS:
        match = re.search(pattern, user_msg, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            if name:
                return name
    return None


# =================================================================
# 📁 PROFILE FILE — Sở thích viết tay (KHÔNG dùng AI tự extract)
# =================================================================
def _read_file_safe(path):
    """Đọc file text an toàn, trả về None nếu không có/rỗng."""
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                return content if content else None
    except Exception as e:
        print(f"⚠️ Không đọc được profile file '{path}': {e}")
    return None


def _slugify_name(name):
    """Chuẩn hóa tên thật -> tên file (VD: 'Linh' -> 'linh.txt')."""
    slug = name.strip().lower()
    slug = re.sub(r'\s+', '_', slug)
    slug = re.sub(r'[^a-z0-9_À-ỹ]', '', slug)
    return slug


def get_profile_context(user_id, funnas_id, real_name):
    """
    Trả về đoạn text profile (sở thích) để chèn thêm vào system prompt.
    - Là Funnas -> luôn đọc my_profile.txt
    - Có real_name đã lưu -> thử tìm friends/{ten}.txt
    - Không có file nào -> trả về None (không ảnh hưởng gì thêm)

    File này CHỈ đọc tĩnh (giống cách đọc tinh_cach.txt), KHÔNG có
    logic ghi/tự động cập nhật — cậu tự sửa tay file text khi cần.
    """
    if str(user_id) == str(funnas_id):
        content = _read_file_safe(MY_PROFILE_FILE)
        if content:
            return f"[Thông tin thêm về Funnas (đọc để hiểu, không đọc lại nguyên văn):\n{content}\n]"
        return None

    if real_name:
        filename = _slugify_name(real_name)
        path = os.path.join(FRIENDS_DIR, f"{filename}.txt")
        content = _read_file_safe(path)
        if content:
            return f"[Thông tin thêm về {real_name} (đọc để hiểu, không đọc lại nguyên văn):\n{content}\n]"

    return None
