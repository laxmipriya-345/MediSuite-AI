import os
import argparse
from Agent import MedicalCodingAgent
from openai_implementation import OpenAIImplementation
from mistral_implementation import MistralImplementation

def main():
    """Main entry point for the CLI."""
    # Parse CLI arguments
    parser = argparse.ArgumentParser(description="Choose the LLM implementation to use.")
    parser.add_argument(
        "--llm",
        choices=["openai", "mistral"],
        default="mistral",
        help="Specify which LLM implementation to use: 'openai' or 'mistral'. Default is 'mistral'."
    )
    args = parser.parse_args()

    tesseract_cmd = os.getenv('TESSERACT_CMD', '/usr/bin/tesseract')  # Default for Linux
    poppler_path = os.getenv('POPPLER_PATH', '/usr/bin')  # Default for Linux
    openai_api_key = os.getenv('OPENAI_API_KEY', 'your-default-api-key')
    mistral_api_key = os.getenv('MISTRAL_API_KEY', 'your-default-api-key')

    # Initialize the chosen LLM implementation
    if args.llm == "openai":
        llm = OpenAIImplementation(api_key=openai_api_key)
    elif args.llm == "mistral":
        llm = MistralImplementation(api_key=mistral_api_key)

    # Inject configurations into the MedicalCodingAgent
    agent = MedicalCodingAgent(
        tesseract_cmd=tesseract_cmd,
        poppler_path=poppler_path,
        llm=llm,
    )
    agent.start_conversation()

if __name__ == "__main__":
    main()