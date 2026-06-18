import os
import io
import time
import base64
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image

# Load variables from .env file
load_dotenv()

# Set up default models
DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"
DEFAULT_VISION_MODEL = "nvidia/nemotron-nano-12b-v2-vl:free"

class OpenRouterClient:
    def __init__(self):
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        if not self.api_key or "your_openrouter_api_key" in self.api_key or self.api_key.strip() == "":
            raise ValueError(
                "Missing OPENROUTER_API_KEY. Please set your key in the '.env' file "
                "or export it as an environment variable."
            )
        
        # OpenRouter uses the OpenAI SDK structure. We point it to the OpenRouter endpoint.
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=self.api_key,
        )

    def encode_image_to_base64(self, image_path, max_size=(1024, 1024), quality=80):
        """
        Reads a local image, resizes it if it exceeds max_size, compresses it, and returns a Base64 string.
        """
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found at path: {image_path}")
        
        try:
            # Open the image using PIL
            with Image.open(image_path) as img:
                # Convert RGBA/palette to RGB so we can compress as JPEG
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                
                # Check dimensions and resize proportionally if too large
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
                
                # Compress image to memory buffer as JPEG
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=quality)
                encoded_string = base64.b64encode(buffer.getvalue()).decode("utf-8")
                
            return f"data:image/jpeg;base64,{encoded_string}"
        except Exception as e:
            # Fallback to raw bytes if PIL compression fails
            with open(image_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
            ext = os.path.splitext(image_path)[1].lower().replace(".", "")
            if ext == "jpg":
                ext = "jpeg"
            return f"data:image/{ext};base64,{encoded_string}"

    def _call_with_retry(self, api_func, *args, max_retries=3, initial_delay=2, **kwargs):
        """
        Helper method to retry API calls with exponential backoff when encountering rate limits or server drops.
        """
        delay = initial_delay
        for attempt in range(max_retries + 1):
            try:
                return api_func(*args, **kwargs)
            except Exception as e:
                err_str = str(e).lower()
                is_rate_limit = "429" in err_str or "rate limit" in err_str or "too many requests" in err_str
                is_server_err = "500" in err_str or "503" in err_str or "bad gateway" in err_str or "timeout" in err_str
                
                if (is_rate_limit or is_server_err) and attempt < max_retries:
                    print(f"\n[API busy or rate-limited. Retrying in {delay}s... (Attempt {attempt + 1}/{max_retries})]")
                    time.sleep(delay)
                    delay *= 2  # Double the wait time
                else:
                    raise e

    def generate_chat_response_stream(self, messages, model=DEFAULT_MODEL):
        """
        Sends chat messages to the OpenRouter API and yields response chunks as they stream.
        """
        try:
            response = self._call_with_retry(
                self.client.chat.completions.create,
                model=model,
                messages=messages,
                stream=True
            )
            for chunk in response:
                if chunk.choices and len(chunk.choices) > 0:
                    content = chunk.choices[0].delta.content
                    if content:
                        yield content
        except Exception as e:
            yield f"\n[Error communicating with OpenRouter API: {str(e)}]"

    def generate_vision_response_stream(self, image_path, prompt, model=DEFAULT_VISION_MODEL):
        """
        Sends an optimized image and a text prompt to OpenRouter and streams the response.
        """
        try:
            # Compresses the image before sending (reducing size from MBs to ~100KB)
            base64_image = self.encode_image_to_base64(image_path)
            
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": base64_image
                            }
                        }
                    ]
                }
            ]
            
            response = self._call_with_retry(
                self.client.chat.completions.create,
                model=model,
                messages=messages,
                stream=True
            )
            for chunk in response:
                if chunk.choices and len(chunk.choices) > 0:
                    content = chunk.choices[0].delta.content
                    if content:
                        yield content
        except Exception as e:
            yield f"\n[Error communicating with OpenRouter Vision API: {str(e)}]"

    def generate_agent_response(self, messages, tools=None, model=DEFAULT_MODEL):
        """
        Sends messages and tool schemas to the model. Returns the message response object.
        """
        try:
            kwargs = {
                "model": model,
                "messages": messages,
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"
                
            response = self._call_with_retry(
                self.client.chat.completions.create,
                **kwargs
            )
            return response.choices[0].message
        except Exception as e:
            class DummyMessage:
                def __init__(self, err_msg):
                    self.content = f"[Error communicating with OpenRouter API: {err_msg}]"
                    self.tool_calls = None
            return DummyMessage(str(e))



