import os
import json
import asyncio
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from client import OpenRouterClient, DEFAULT_MODEL, DEFAULT_VISION_MODEL
from tools import TOOL_SCHEMAS, execute_tool

app = FastAPI()

# Configuration store (in-memory for session)
class Settings:
    def __init__(self):
        self.text_model = DEFAULT_MODEL
        self.vision_model = DEFAULT_VISION_MODEL
        self.api_key = os.getenv("OPENROUTER_API_KEY", "")

settings = Settings()

class ChatRequest(BaseModel):
    message: str
    image: str = None  # Base64 data URI string
    text_model: str = DEFAULT_MODEL
    vision_model: str = DEFAULT_VISION_MODEL

class ConfigUpdate(BaseModel):
    text_model: str
    vision_model: str
    api_key: str

async def agent_execution_generator(user_message: str, image: str = None):
    """
    Generator yielding JSON chunks representing agent thoughts, tool logs, and final streaming text.
    """
    try:
        client = OpenRouterClient()
    except Exception as e:
        yield json.dumps({"type": "error", "content": f"Configuration Error: {str(e)}"}) + "\n"
        return

    conversation_history = []

    # Two-Step Pipeline:
    # 1. If an image is present, decode it and call the Vision model first to extract details.
    if image:
        yield json.dumps({"type": "status", "content": "Decoding pasted image..."}) + "\n"
        await asyncio.sleep(0.1)
        
        try:
            import base64
            # Decode the base64 image payload and write to a temp file
            header, base64_data = image.split(",", 1)
            image_bytes = base64.b64decode(base64_data)
            temp_image_path = "temp_pasted_image.png"
            with open(temp_image_path, "wb") as f:
                f.write(image_bytes)
        except Exception as e:
            yield json.dumps({"type": "error", "content": f"Failed to decode pasted image: {str(e)}"}) + "\n"
            return
            
        yield json.dumps({"type": "status", "content": "Extracting visual specifications..."}) + "\n"
        await asyncio.sleep(0.1)
        
        vision_prompt = (
            f"Analyze this image and extract all relevant text, design structure, layout elements, "
            f"and specifications required to fulfill this user request: '{user_message}'. "
            f"Provide a clear, detailed technical description of what needs to be implemented."
        )
        
        # Log the start of the vision tool call to the UI console
        yield json.dumps({
            "type": "tool_start",
            "tool": "inspect_image",
            "args": {"image_path": "Pasted Image", "query": vision_prompt}
        }) + "\n"
        await asyncio.sleep(0.1)
        
        # Call the Vision model
        extracted_specs = ""
        try:
            for chunk in client.generate_vision_response_stream(temp_image_path, vision_prompt, model=settings.vision_model):
                extracted_specs += chunk
                
            # Log the successful visual analysis to the UI console
            yield json.dumps({
                "type": "tool_end",
                "tool": "inspect_image",
                "result": f"Analysis complete. Specs extracted: {len(extracted_specs)} characters of details."
            }) + "\n"
            await asyncio.sleep(0.1)
            
            # Clean up the temp image file
            if os.path.exists(temp_image_path):
                os.remove(temp_image_path)
        except Exception as e:
            yield json.dumps({"type": "error", "content": f"Vision extraction failed: {str(e)}"}) + "\n"
            return
            
        # Structure the prompt for the text model with the visual context appended
        combined_prompt = (
            f"The user wants to perform this task in their local workspace: '{user_message}'.\n\n"
            f"Here are the visual details and specifications extracted from the image they attached:\n"
            f"=== VISUAL CONTEXT ===\n"
            f"{extracted_specs}\n"
            f"======================\n\n"
            f"Please use your tools (like write_file) to implement the request locally on their computer."
        )
        conversation_history.append({"role": "user", "content": combined_prompt})
    else:
        # Standard text-only prompt
        conversation_history.append({"role": "user", "content": user_message})

    processing = True
    loop_count = 0
    max_loops = 5  # Prevent infinite loops

    while processing and loop_count < max_loops:
        loop_count += 1
        yield json.dumps({"type": "status", "content": "Thinking..."}) + "\n"
        await asyncio.sleep(0.1)  # Allow event loop to breathe

        try:
            # Query the text model (which supports tools)
            response_message = client.generate_agent_response(
                messages=conversation_history,
                tools=TOOL_SCHEMAS,
                model=settings.text_model
            )
        except Exception as e:
            yield json.dumps({"type": "error", "content": f"API Error: {str(e)}"}) + "\n"
            return

        # Check for tool calls
        if hasattr(response_message, "tool_calls") and response_message.tool_calls:
            assistant_msg = {
                "role": "assistant",
                "content": response_message.content or "",
                "tool_calls": []
            }

            for tool_call in response_message.tool_calls:
                assistant_msg["tool_calls"].append({
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments
                    }
                })

            conversation_history.append(assistant_msg)

            # Process each tool call
            for tool_call in response_message.tool_calls:
                tool_name = tool_call.function.name
                tool_args = tool_call.function.arguments
                tool_id = tool_call.id

                # Yield tool invocation log to frontend
                yield json.dumps({
                    "type": "tool_start",
                    "tool": tool_name,
                    "args": tool_args
                }) + "\n"
                await asyncio.sleep(0.1)

                # Execute the tool
                # We run it in executor since it could be blocking (screenshot/file writing)
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, execute_tool, tool_name, tool_args)

                # Yield tool result log to frontend
                yield json.dumps({
                    "type": "tool_end",
                    "tool": tool_name,
                    "result": result
                }) + "\n"
                await asyncio.sleep(0.1)

                # Append tool results to history
                conversation_history.append({
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "name": tool_name,
                    "content": result
                })

            # Continue execution loop
            continue
        else:
            # Final text response
            final_content = response_message.content or "[No text returned]"
            conversation_history.append({"role": "assistant", "content": final_content})
            
            # Stream final message out
            yield json.dumps({"type": "message", "content": final_content}) + "\n"
            processing = False

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    # Temporarily update model settings from requests
    settings.text_model = request.text_model
    settings.vision_model = request.vision_model
    
    return StreamingResponse(
        agent_execution_generator(request.message, request.image),
        media_type="text/event-stream"
    )

@app.get("/api/config")
async def get_config():
    return {
        "text_model": settings.text_model,
        "vision_model": settings.vision_model,
        "api_key": settings.api_key
    }

@app.post("/api/config")
async def update_config(config: ConfigUpdate):
    settings.text_model = config.text_model
    settings.vision_model = config.vision_model
    settings.api_key = config.api_key
    os.environ["OPENROUTER_API_KEY"] = config.api_key
    return {"status": "success"}

@app.get("/screenshot.png")
async def get_screenshot():
    file_path = os.path.join(os.path.dirname(__file__), "screenshot.png")
    if os.path.exists(file_path):
        return FileResponse(file_path)
    # Fallback to test_image.png if no screenshot has been captured yet
    fallback_path = os.path.join(os.path.dirname(__file__), "test_image.png")
    if os.path.exists(fallback_path):
        return FileResponse(fallback_path)
    return {"status": "error", "message": "No capture available."}

# Serve static dashboard files
static_dir = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir)

app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
