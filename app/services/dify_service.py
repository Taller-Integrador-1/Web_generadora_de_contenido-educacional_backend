import requests
import os
import dotenv

dotenv.load_dotenv()

class DifyService:
    def __init__(self, api_key: str = None, base_url: str = "https://api.dify.ai/v1"):
        api_key = api_key or os.getenv("DIFY_API_KEY_TUTOR")
        if not api_key:
            raise ValueError("Falta la variable de entorno DIFY_API_KEY_TUTOR en el archivo .env")
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        self.url = f"{base_url}/chat-messages"

    def enviar_mensaje(self, query: str, user_id: str, conversation_id: str = None, inputs: dict = None) -> dict:
        payload = {
            "inputs": inputs or {},
            "query": query,
            "response_mode": "blocking",
            "user": user_id,
            "conversation_id": conversation_id or ""
        }
        response = requests.post(self.url, json=payload, headers=self.headers)
        response.raise_for_status()
        return response.json()