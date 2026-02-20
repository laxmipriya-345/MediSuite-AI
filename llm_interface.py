from abc import ABC, abstractmethod

class LLMInterface(ABC):
    @abstractmethod
    def generate_response(self, conversation_history, specific_prompt=None):
        """Generate a response based on the conversation history and an optional specific prompt."""
        pass