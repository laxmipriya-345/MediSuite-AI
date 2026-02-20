import openai
from llm_interface import LLMInterface

class OpenAIImplementation(LLMInterface):
    def __init__(self, api_key):
        openai.api_key = api_key

    def generate_response(self, conversation_history, specific_prompt=None):
        messages = conversation_history.copy()
        if specific_prompt:
            messages.append({"role": "system", "content": specific_prompt})
        
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4.1",
                messages=messages,
                max_tokens=1000,
                temperature=0.7
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"Error: {str(e)}"