import os
import random

# Map tag cảm xúc sang danh sách tên file ảnh trong thư mục images/
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

def get_image_for_tag(tag):
    if tag not in IMAGE_MAP:
        return None
    files = IMAGE_MAP[tag]
    if not files:
        return None

    # Chọn ngẫu nhiên 1 file trong danh sách của tag đó
    filename = random.choice(files)
    image_path = os.path.join("images", filename)

    if os.path.exists(image_path):
        return image_path
    else:
        print(f"⚠️ Console log: File ảnh '{filename}' không tồn tại trong folder images/")
        return None
