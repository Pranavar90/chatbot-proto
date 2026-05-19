import hashlib
import httpx
import json
import re
import threading
from typing import Optional, Dict, Any, List, Union
from config import OLLAMA_BASE, EMBED_MODEL, LLM_MODEL
from cache import cached_llm_response, store_llm_response, InMemoryCache

AVAILABLE_MODELS = [
    "phi3:mini",
    "qwen2.5:3b-instruct-q4_K_S",
    "qwen2.5:7b-instruct-q4_K_S",
    "qwen2.5:14b-instruct-q4_K_S",
    "llama3.2:3b",
    "gemma3:4b",
]

# Cache model list (rarely changes, expensive to fetch)
_model_list_cache = InMemoryCache(maxsize=1, ttl=60)


class OllamaClient:
    def __init__(self, base_url: str = OLLAMA_BASE):
        self.base_url = base_url
        # Connection pooling: keep-alive + reuse across calls
        self.client = httpx.Client(
            timeout=300.0,
            limits=httpx.Limits(
                max_keepalive_connections=5,
                max_connections=10,
                keepalive_expiry=120.0,
            ),
        )

    def is_running(self) -> bool:
        cached = _model_list_cache.get("ollama_running")
        if cached is not None:
            return cached
        try:
            response = self.client.get(f"{self.base_url}/api/tags")
            running = response.status_code == 200
            _model_list_cache.set("ollama_running", running)
            return running
        except:
            _model_list_cache.set("ollama_running", False)
            return False

    def list_models(self) -> List[str]:
        cached = _model_list_cache.get("models")
        if cached is not None:
            return cached
        try:
            response = self.client.get(f"{self.base_url}/api/tags")
            if response.status_code == 200:
                data = response.json()
                models = [m["name"] for m in data.get("models", [])]
                _model_list_cache.set("models", models)
                return models
            return []
        except:
            return []

    def pull_model(self, model: str) -> bool:
        try:
            response = self.client.post(
                f"{self.base_url}/api/pull", json={"name": model}, timeout=None
            )
            return response.status_code == 200
        except Exception as e:
            print(f"Failed to pull model {model}: {e}")
            return False

    def generate(
        self,
        model: str,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.1,
        json_mode: bool = True,
        use_cache: bool = True,
    ) -> Optional[Dict[str, Any]]:
        cache_key = None
        if use_cache and temperature == 0.0 and json_mode:
            cache_key = hashlib.sha256(
                f"{model}:{system}:{prompt}".encode()
            ).hexdigest()
            cached = cached_llm_response(cache_key)
            if cached is not None:
                return cached

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_gpu": 99,
                "num_ctx": 8192,
            },
            "keep_alive": "15m",
        }

        if system:
            payload["system"] = system

        if json_mode:
            payload["format"] = "json"

        try:
            response = self.client.post(f"{self.base_url}/api/generate", json=payload)
            if response.status_code == 200:
                result = response.json()
                if json_mode and "response" in result:
                    raw_response = result["response"]
                    parsed = extract_json_from_response(raw_response)
                    result_to_return = parsed if parsed is not None else {"raw_text": raw_response}
                    if use_cache and temperature == 0.0 and json_mode and result_to_return:
                        store_llm_response(cache_key, result_to_return)
                    return result_to_return
                return result
            return None
        except Exception as e:
            print(f"Generation error: {e}")
            return None

    def embeddings(self, text: str, model: str = EMBED_MODEL) -> Optional[List[float]]:
        try:
            payload = {"model": model, "prompt": text, "options": {"num_gpu": 35}}
            response = self.client.post(f"{self.base_url}/api/embeddings", json=payload)
            if response.status_code == 200:
                data = response.json()
                return data.get("embedding")
            return None
        except Exception as e:
            print(f"Embedding error: {e}")
            return None

    def close(self):
        """No-op for backward compatibility.
        Client is now a singleton with connection pooling;
        connection lifecycle is managed by the module.
        Call shutdown_client() at app exit to release resources."""
        pass


def shutdown_client():
    """Release the singleton client resources.
    Call on application shutdown to clean up connection pool."""
    global _client_instance
    if _client_instance is not None:
        try:
            _client_instance.client.close()
        except Exception:
            pass
        _client_instance = None


_client_instance: Optional[OllamaClient] = None
_client_lock = threading.Lock()


def get_client() -> OllamaClient:
    """Singleton client with connection pooling.
    Reuses httpx connection pool across all API calls.
    Avoids repeated TCP handshake + TLS overhead.
    """
    global _client_instance
    if _client_instance is None:
        with _client_lock:
            if _client_instance is None:
                _client_instance = OllamaClient()
    return _client_instance


def extract_json_from_response(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None

    text = text.strip()

    # Handle Markdown code blocks
    if "```json" in text:
        try:
            json_str = text.split("```json")[1].split("```")[0].strip()
            return json.loads(json_str)
        except:
            pass
    elif "```" in text:
        try:
            json_str = text.split("```")[1].split("```")[0].strip()
            return json.loads(json_str)
        except:
            pass

    # Direct JSON attempt
    if text.startswith("{") and text.endswith("}"):
        try:
            return json.loads(text)
        except:
            pass

    # Regex search for the first valid-looking JSON object
    try:
        # Matches balanced curly braces
        json_match = re.search(r"(\{.*\})", text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))
    except:
        pass

    return None
