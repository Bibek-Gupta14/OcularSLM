import os
import argparse
import sys
from client import OpenRouterClient, DEFAULT_VISION_MODEL

def main():
    parser = argparse.ArgumentParser(description="Hybrid Agent - Phase 2: OpenRouter Vision Agent")
    parser.add_argument("--image", type=str, help="Path to the local image file")
    parser.add_argument("--prompt", type=str, default="Describe what you see in this image in detail.", help="Question or prompt about the image")
    parser.add_argument("--model", type=str, default=DEFAULT_VISION_MODEL, help="OpenRouter vision model to use")
    
    args = parser.parse_args()

    print("==========================================================")
    print("      Hybrid Agent - Phase 2: OpenRouter Vision Client    ")
    print("==========================================================")

    # Initialize client
    try:
        agent = OpenRouterClient()
    except ValueError as e:
        print(f"\nConfiguration Error: {e}")
        print("Please create a '.env' file in this folder and add your key:")
        print("OPENROUTER_API_KEY=your_actual_key_here\n")
        sys.exit(1)

    # Resolve image path
    image_path = args.image
    if not image_path:
        # If no image path is provided, look for any default test image in the current directory
        default_images = [f for f in os.listdir(".") if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))]
        if default_images:
            image_path = default_images[0]
            print(f"No image path specified. Auto-detecting test image: {image_path}")
        else:
            print("\nError: Please provide an image path.")
            print("Usage example: python vision_main.py --image path/to/your/image.jpg")
            sys.exit(1)

    if not os.path.exists(image_path):
        print(f"\nError: Image file not found at: {image_path}")
        sys.exit(1)

    print(f"\nTarget Image: {image_path}")
    print(f"Prompt: {args.prompt}")
    print(f"Using Model: {args.model}")
    print("\nProcessing image and streaming response...")
    print("----------------------------------------------------------")
    print("Agent: ", end="", flush=True)

    # Request streaming response
    try:
        for chunk in agent.generate_vision_response_stream(image_path, args.prompt, model=args.model):
            print(chunk, end="", flush=True)
        print()
    except KeyboardInterrupt:
        print("\nExiting...")
    print("----------------------------------------------------------")

if __name__ == "__main__":
    main()
