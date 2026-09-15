from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/documents']
SERVICE_ACCOUNT_FILE = 'gen-lang-client-0424081789-xxxxx.json'  # đổi thành đúng tên file JSON của bạn
DOCUMENT_ID = 'DÁN_DOCUMENT_ID_CỦA_BẠN_VÀO_ĐÂY'  # lấy từ URL Google Doc

def get_docs_service():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return build('docs', 'v1', credentials=creds)

def append_memory(fact_text):
    """Ghi thêm 1 dòng thông tin mới vào cuối Google Doc."""
    try:
        service = get_docs_service()
        doc = service.documents().get(documentId=DOCUMENT_ID).execute()
        end_index = doc['body']['content'][-1]['endIndex'] - 1

        requests = [{
            'insertText': {
                'location': {'index': end_index},
                'text': f"\n- {fact_text}"
            }
        }]
        service.documents().batchUpdate(
            documentId=DOCUMENT_ID, body={'requests': requests}).execute()
        print(f"📝 Đã lưu memory: {fact_text}")
    except Exception as e:
        print(f"❌ Lỗi ghi Google Doc: {e}")

def read_all_memory():
    """Đọc toàn bộ nội dung Doc, trả về dạng text."""
    try:
        service = get_docs_service()
        doc = service.documents().get(documentId=DOCUMENT_ID).execute()
        text = ""
        for elem in doc['body']['content']:
            if 'paragraph' in elem:
                for run in elem['paragraph'].get('elements', []):
                    text += run.get('textRun', {}).get('content', '')
        return text.strip()
    except Exception as e:
        print(f"❌ Lỗi đọc Google Doc: {e}")
        return ""
