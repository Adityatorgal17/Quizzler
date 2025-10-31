import os
from typing import Dict, Any

class RealtimeConfig:
    """Configuration for real-time quiz system"""
    
    # Connection limits
    MAX_ROOMS = int(os.getenv("MAX_ROOMS", 100))
    MAX_PLAYERS_PER_ROOM = int(os.getenv("MAX_PLAYERS_PER_ROOM", 100))
    MAX_CONNECTIONS_PER_IP = int(os.getenv("MAX_CONNECTIONS_PER_IP", 100))
    
    # Rate limiting
    RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", 60))  # seconds
    MAX_REQUESTS_PER_WINDOW = int(os.getenv("MAX_REQUESTS_PER_WINDOW", 30))
    
    # Cleanup and monitoring
    CLEANUP_INTERVAL = int(os.getenv("CLEANUP_INTERVAL", 300))  # 5 minutes
    HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", 30))  # 30 seconds
    HEARTBEAT_TIMEOUT = int(os.getenv("HEARTBEAT_TIMEOUT", 60))  # 60 seconds
    SESSION_MAX_AGE = int(os.getenv("SESSION_MAX_AGE", 7200))  # 2 hours
    
    # Performance settings
    MESSAGE_RETRY_COUNT = int(os.getenv("MESSAGE_RETRY_COUNT", 2))
    BATCH_ANSWER_UPDATES = int(os.getenv("BATCH_ANSWER_UPDATES", 5))
    LEADERBOARD_SIZE = int(os.getenv("LEADERBOARD_SIZE", 10))
    
    # Quiz settings
    DEFAULT_QUESTION_TIME = int(os.getenv("DEFAULT_QUESTION_TIME", 30))
    DEFAULT_BASE_POINTS = int(os.getenv("DEFAULT_BASE_POINTS", 100))
    DEFAULT_TIME_BONUS_MULT = float(os.getenv("DEFAULT_TIME_BONUS_MULT", 2.0))
    
    # Memory and resource limits
    MAX_MEMORY_MB = int(os.getenv("MAX_MEMORY_MB", 1000))
    WARNING_MEMORY_MB = int(os.getenv("WARNING_MEMORY_MB", 750))
    
    @classmethod
    def get_quiz_config(cls) -> Dict[str, Any]:
        """Get default quiz configuration"""
        return {
            "question_time_limit": cls.DEFAULT_QUESTION_TIME,
            "base_points": cls.DEFAULT_BASE_POINTS,
            "time_bonus_multiplier": cls.DEFAULT_TIME_BONUS_MULT
        }
    
    @classmethod
    def get_limits_config(cls) -> Dict[str, Any]:
        """Get connection limits configuration"""
        return {
            "max_rooms": cls.MAX_ROOMS,
            "max_players_per_room": cls.MAX_PLAYERS_PER_ROOM,
            "max_connections_per_ip": cls.MAX_CONNECTIONS_PER_IP,
            "rate_limit_window": cls.RATE_LIMIT_WINDOW,
            "max_requests_per_window": cls.MAX_REQUESTS_PER_WINDOW
        }
    
    @classmethod
    def is_production(cls) -> bool:
        """Check if running in production environment"""
        return os.getenv("ENVIRONMENT", "development").lower() == "production"

config = RealtimeConfig()
