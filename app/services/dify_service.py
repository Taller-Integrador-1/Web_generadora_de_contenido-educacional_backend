import requests

class DifyService:
    def __init__(self, api_key: str = "app-5pkVOhLwCB5yF0NnMiUlhi8J", base_url: str = "https://api.dify.ai/v1"):
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        self.url = f"{base_url}/chat-messages"

    def enviar_mensaje(self, query: str, user_id: str, conversation_id: str = None) -> dict:
        payload = {
            "inputs": {},
            "query": query,
            "response_mode": "blocking",
            "user": user_id,
            "conversation_id": conversation_id or ""
        }
        response = requests.post(self.url, json=payload, headers=self.headers)
        response.raise_for_status()
        return response.json()