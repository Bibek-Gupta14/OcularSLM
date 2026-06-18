import os
import json
from PIL import ImageGrab

def write_file(filename, content):
    """
    Creates or updates a file locally with the specified content.
    """
    try:
        # Enforce writing to the current working directory for safety
        base_name = os.path.basename(filename)
        with open(base_name, "w", encoding="utf-8") as f:
            f.write(content)
        return json.dumps({"status": "success", "message": f"Successfully wrote file '{base_name}'"})
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})

def read_file(filename):
    """
    Reads and returns the contents of a local file.
    """
    try:
        base_name = os.path.basename(filename)
        if not os.path.exists(base_name):
            return json.dumps({"status": "error", "message": f"File '{base_name}' not found."})
        
        with open(base_name, "r", encoding="utf-8") as f:
            content = f.read()
        return json.dumps({"status": "success", "content": content})
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})

def take_screenshot():
    """
    Captures a screenshot of the user's primary monitor and saves it locally.
    """
    try:
        # ImageGrab.grab() is cross-platform but works natively on Windows
        screenshot = ImageGrab.grab()
        filename = "screenshot.png"
        screenshot.save(filename)
        return json.dumps({
            "status": "success", 
            "message": "Successfully captured screen and saved as 'screenshot.png'. You can now use the vision tool to inspect it."
        })
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})

def inspect_image(image_path, query):
    """
    Sends an image and a text prompt to the OpenRouter Vision model and returns the text description.
    """
    try:
        base_name = os.path.basename(image_path)
        if not os.path.exists(base_name):
            return json.dumps({"status": "error", "message": f"Image '{base_name}' not found."})
        
        from client import OpenRouterClient, DEFAULT_VISION_MODEL
        client = OpenRouterClient()
        
        print(f" -> [Running Vision Model: {DEFAULT_VISION_MODEL} on '{base_name}']")
        
        description = ""
        # Accumulate the stream chunks
        for chunk in client.generate_vision_response_stream(base_name, query, model=DEFAULT_VISION_MODEL):
            description += chunk
            
        return json.dumps({"status": "success", "description": description.strip()})
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})

# Tool definitions (JSON schemas for OpenRouter)
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Writes or updates text content into a local file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "The name of the file to create or overwrite (e.g. notes.txt)."
                    },
                    "content": {
                        "type": "string",
                        "description": "The full text content to write inside the file."
                    }
                },
                "required": ["filename", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Reads the text content of a local file in the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "The name of the file to read (e.g. notes.txt)."
                    }
                },
                "required": ["filename"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "take_screenshot",
            "description": "Takes a screenshot of the user's current screen and saves it as screenshot.png in the workspace.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "inspect_image",
            "description": "Analyzes an image in the workspace (such as a captured screenshot.png) and answers questions about its contents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "image_path": {
                        "type": "string",
                        "description": "The name or path of the image file to inspect (e.g. screenshot.png)."
                    },
                    "query": {
                        "type": "string",
                        "description": "Specific question to ask about the image (e.g. 'What windows are open?')."
                    }
                },
                "required": ["image_path", "query"]
            }
        }
    }
]

def execute_tool(name, arguments):
    """
    Dispatcher to execute a tool locally by name and string/dict arguments.
    """
    # Parse arguments if passed as string
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except Exception:
            return json.dumps({"status": "error", "message": "Failed to parse arguments JSON."})

    if name == "write_file":
        return write_file(arguments.get("filename"), arguments.get("content"))
    elif name == "read_file":
        return read_file(arguments.get("filename"))
    elif name == "take_screenshot":
        return take_screenshot()
    elif name == "inspect_image":
        return inspect_image(arguments.get("image_path"), arguments.get("query"))
    else:
        return json.dumps({"status": "error", "message": f"Tool '{name}' not found."})

