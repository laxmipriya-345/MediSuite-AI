from llm_interface import LLMInterface
from mistralai import Mistral

class MistralImplementation(LLMInterface):
    def __init__(self, api_key, model="mistral-large-latest"):
        """
        Initialize the Mistral LLM implementation.

        Args:
            api_key (str): The API key for authenticating with the Mistral service.
            model (str): The model to use for generating responses.
        """
        self.client = Mistral(api_key=api_key)
        self.model = model

    def generate_response(self, conversation_history, specific_prompt=None):
        """
        Generate a response using the Mistral API.

        Args:
            conversation_history (list): A list of conversation messages in the format:
                                         [{"role": "user", "content": "message"}, ...]
            specific_prompt (str, optional): An additional system-level prompt to guide the response.

        Returns:
            str: The generated response from the Mistral API.
        """
        try:
            # If a specific prompt is provided, prepend it as a system message
            if specific_prompt:
                conversation_history.insert(0, {"role": "system", "content": specific_prompt})

            # Use the Mistral client to generate a response
            chat_response = self.client.chat.complete(
                model=self.model,
                messages=conversation_history
            )

            # Extract and return the content of the response
            return chat_response.choices[0].message.content.strip()
        except Exception as e:
            return f"Error: {str(e)}"