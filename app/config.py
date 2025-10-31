from pydantic_settings import BaseSettings
from pydantic import SecretStr
import os
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    app_name: str = "Quizzler API"
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"
    
    # Database Configuration
    user: str = os.getenv("user", "postgres")
    password: SecretStr = os.getenv("password", "")
    host: str = os.getenv("host", "localhost")
    port: int = int(os.getenv("port", 5432))
    dbname: str = os.getenv("dbname", "postgres")
    
    # Supabase Configuration
    supabase_url: str = os.getenv("SUPABASE_URL")
    supabase_anon_key: SecretStr = os.getenv("SUPABASE_ANON_KEY", "")
    supabase_service_role_key: SecretStr = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    use_supabase_rest: bool = os.getenv("USE_SUPABASE_REST", "false").lower() == "true"
    
    # JWT Configuration
    jwt_secret: str = os.getenv("JWT_SECRET", "your-fallback-secret-key")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    
    # Gemini AI Configuration
    gemini_api_key: SecretStr = os.getenv("GEMINI_API_KEY", "")

    @property
    def DATABASE_URL(self):
        return f"postgresql+psycopg2://{self.user}:{self.password.get_secret_value()}@{self.host}:{self.port}/{self.dbname}?sslmode=require"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  

settings = Settings()