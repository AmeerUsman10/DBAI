"""
LLM Provider Wrapper
Supports Groq and OpenAI with robust error handling and model listing.
"""
import logging
import os
from typing import List, Tuple, Optional, Any
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

class ProviderWrapper:
    """Wrapper for LLM providers (Groq, OpenAI) with robust error handling."""
    
    def __init__(self, provider: str = "groq", api_key: Optional[str] = None):
        """
        Initialize provider wrapper.
        
        Args:
            provider: Provider name ("groq" or "openai")
            api_key: Optional API key (uses env var if not provided)
        """
        self.provider = provider.lower()
        self.api_key = api_key
        self._llm = None
        
        logger.info(f"Initializing provider: {self.provider}")
    
    def _get_api_key(self) -> Optional[str]:
        """Get API key from instance or environment."""
        if self.api_key:
            return self.api_key
        
        if self.provider == "groq":
            return os.getenv("GROQ_API_KEY")
        elif self.provider == "openai":
            return os.getenv("OPENAI_API_KEY")
        
        return None
    
    def get_llm(self, model: str, temperature: float = 0.1, max_tokens: int = 2000):
        """
        Get LLM instance for the specified model.
        
        Args:
            model: Model name
            temperature: Temperature setting
            max_tokens: Maximum tokens
            
        Returns:
            LLM instance
        """
        api_key = self._get_api_key()
        
        if not api_key:
            raise ValueError(f"No API key found for {self.provider}")
        
        try:
            if self.provider == "groq":
                from langchain_groq import ChatGroq
                self._llm = ChatGroq(
                    model=model,
                    api_key=api_key,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
            elif self.provider == "openai":
                from langchain_openai import ChatOpenAI
                self._llm = ChatOpenAI(
                    model=model,
                    api_key=api_key,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
            else:
                raise ValueError(f"Unsupported provider: {self.provider}")
            
            logger.info(f"Created LLM instance: {self.provider}/{model}")
            return self._llm
            
        except Exception as e:
            logger.error(f"Error creating LLM: {e}", exc_info=True)
            raise
    
    def invoke(self, prompt: str, **kwargs) -> str:
        """
        Invoke the LLM with a prompt and extract text response.
        
        Args:
            prompt: Input prompt
            **kwargs: Additional arguments
            
        Returns:
            Text response
        """
        if not self._llm:
            raise RuntimeError("LLM not initialized. Call get_llm() first.")
        
        try:
            response = self._llm.invoke(prompt, **kwargs)
            
            # Try to extract text from various response formats
            if hasattr(response, 'content'):
                return response.content
            elif isinstance(response, str):
                return response
            elif isinstance(response, dict):
                return response.get('content', str(response))
            else:
                return str(response)
                
        except Exception as e:
            logger.error(f"Error invoking LLM: {e}", exc_info=True)
            raise
    
    def list_models(self) -> List[str]:
        """
        List available models for the provider (best-effort).
        
        Returns:
            List of model names
        """
        try:
            if self.provider == "groq":
                # Common Groq models
                return [
                    "llama-3.1-8b-instant",
                    "llama-3.1-70b-versatile",
                    "llama-3.2-1b-preview",
                    "llama-3.2-3b-preview",
                    "llama-3.2-11b-vision-preview",
                    "llama-3.2-90b-vision-preview",
                    "mixtral-8x7b-32768",
                    "gemma2-9b-it",
                ]
            elif self.provider == "openai":
                # Common OpenAI models
                return [
                    "gpt-4o",
                    "gpt-4o-mini",
                    "gpt-4-turbo",
                    "gpt-4",
                    "gpt-3.5-turbo",
                ]
            else:
                return []
        except Exception as e:
            logger.error(f"Error listing models: {e}")
            return []
    
    def test_connection(self, model: str) -> Tuple[bool, str]:
        """
        Test provider connectivity with a simple prompt.
        
        Args:
            model: Model to test
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            api_key = self._get_api_key()
            if not api_key:
                return False, f"No API key found for {self.provider}"
            
            # Create a fresh LLM instance for testing
            llm = self.get_llm(model, temperature=0, max_tokens=50)
            
            # Simple deterministic test prompt
            test_prompt = "Reply with: OK"
            response = self.invoke(test_prompt)
            
            if response:
                return True, f"Connection successful! Response: {response[:100]}"
            else:
                return False, "Empty response from provider"
                
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Provider test failed: {error_msg}", exc_info=True)
            return False, f"Error: {error_msg}"

def create_provider(provider: str, api_key: Optional[str] = None) -> ProviderWrapper:
    """
    Factory function to create a provider wrapper.
    
    Args:
        provider: Provider name ("groq" or "openai")
        api_key: Optional API key
        
    Returns:
        ProviderWrapper instance
    """
    return ProviderWrapper(provider, api_key)
