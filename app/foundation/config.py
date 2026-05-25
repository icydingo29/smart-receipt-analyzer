"""Configuration module using Pydantic Settings for environment variables."""
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables. Default values given."""
    
    # Database Configuration
    database_url: str = "postgresql://postgres:postgres@localhost:5432/receipt_analyzer"
    
    # Groq API Configuration
    groq_api_key: str = ""
    
    # LLM Model Configuration
    ocr_model: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    llm_model: str = "llama-3.3-70b-versatile"
    
    # Application Configuration
    app_port: int = 8000
    debug: bool = False
    
    # Storage Configuration
    storage_volume_path: str = "./storage_volume"
    temp_storage_path: str = "./app/storage"
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "allow"
    
    def __init__(self, **data):
        super().__init__(**data)
        # Create storage directories if they don't exist
        Path(self.storage_volume_path).mkdir(parents=True, exist_ok=True)
        Path(self.temp_storage_path).mkdir(parents=True, exist_ok=True)


# Create global settings instance
settings = Settings()
