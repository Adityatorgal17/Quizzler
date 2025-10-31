from pydantic import BaseModel
from typing import Dict, List, Optional, Any
from enum import Enum
import time
from datetime import datetime

class MessageType(str, Enum):
    # Host messages
    CREATE_ROOM = "create_room"
    ROOM_CREATED = "room_created"
    NEW_QUESTION = "new_question"
    CLOSE_ROOM = "close_room"
    RESULTS = "results"
    
    # Player messages
    JOIN_ROOM = "join_room"
    PLAYER_JOINED = "player_joined"
    ANSWER = "answer"
    
    # Broadcast messages
    QUESTION = "question"
    QUESTION_ENDED = "question_ended"
    ROOM_CLOSED = "room_closed"
    
    # Status messages
    ERROR = "error"
    PLAYER_COUNT = "player_count"
    ANSWER_COUNT = "answer_count"
    HEARTBEAT = "heartbeat"

class BaseMessage(BaseModel):
    type: MessageType
    timestamp: Optional[float] = None
    
    def __init__(self, **data):
        if 'timestamp' not in data:
            data['timestamp'] = time.time()
        super().__init__(**data)

# Host Messages
class CreateRoomMessage(BaseMessage):
    type: MessageType = MessageType.CREATE_ROOM
    quiz_config: Dict[str, Any] = {
        "question_time_limit": 30, 
        "base_points": 100,
        "time_bonus_multiplier": 2
    }

class RoomCreatedMessage(BaseMessage):
    type: MessageType = MessageType.ROOM_CREATED
    room_code: str

class NewQuestionMessage(BaseMessage):
    type: MessageType = MessageType.NEW_QUESTION
    question: str
    options: List[str]
    correct_answer: int  
    time_limit: Optional[int] = 30  

class CloseRoomMessage(BaseMessage):
    type: MessageType = MessageType.CLOSE_ROOM

# Player Messages
class JoinRoomMessage(BaseMessage):
    type: MessageType = MessageType.JOIN_ROOM
    room_code: str
    username: str

class PlayerJoinedMessage(BaseMessage):
    type: MessageType = MessageType.PLAYER_JOINED
    username: str
    player_count: int

class AnswerMessage(BaseMessage):
    type: MessageType = MessageType.ANSWER
    option: int  # selected option index (0-3)

# Broadcast Messages
class QuestionMessage(BaseMessage):
    type: MessageType = MessageType.QUESTION
    question: str
    options: List[str]
    time_limit: int
    question_start_time: float

class QuestionEndedMessage(BaseMessage):
    type: MessageType = MessageType.QUESTION_ENDED
    correct_answer: int

class ResultsMessage(BaseMessage):
    type: MessageType = MessageType.RESULTS
    top_5: List[Dict[str, Any]]  # [{name, score, time, correct}, ...]
    total_answers: int
    correct_answers: int

class RoomClosedMessage(BaseMessage):
    type: MessageType = MessageType.ROOM_CLOSED
    reason: str = "Host closed the room"

# Status Messages
class ErrorMessage(BaseMessage):
    type: MessageType = MessageType.ERROR
    message: str

class PlayerCountMessage(BaseMessage):
    type: MessageType = MessageType.PLAYER_COUNT
    count: int

class AnswerCountMessage(BaseMessage):
    type: MessageType = MessageType.ANSWER_COUNT
    answered: int
    total: int

class HeartbeatMessage(BaseMessage):
    type: MessageType = MessageType.HEARTBEAT

# Data Models for in-memory storage
class Player(BaseModel):
    id: str
    username: str
    ws: Any = None  # WebSocket connection
    score: int = 0
    current_answer: Optional[int] = None
    answer_time: Optional[float] = None
    connected: bool = True
    
    class Config:
        arbitrary_types_allowed = True

class Question(BaseModel):
    text: str
    options: List[str]
    correct_answer: int
    time_limit: int
    start_time: float
    answers: Dict[str, Dict[str, Any]] = {}  # player_id: {option, timestamp}

class GameSession(BaseModel):
    room_code: str
    host_ws: Any = None
    host_id: str
    players: Dict[str, Player] = {}
    current_question: Optional[Question] = None
    created_at: float
    quiz_config: Dict[str, Any] = {
        "question_time_limit": 30,
        "base_points": 100,
        "time_bonus_multiplier": 2
    }
    is_active: bool = True
    
    class Config:
        arbitrary_types_allowed = True
    
    def get_connected_players(self) -> Dict[str, Player]:
        return {pid: player for pid, player in self.players.items() if player.connected}
    
    def get_player_count(self) -> int:
        return len(self.get_connected_players())
    
    def get_answer_count(self) -> int:
        if not self.current_question:
            return 0
        return len(self.current_question.answers)
    
    def calculate_scores(self) -> List[Dict[str, Any]]:
        if not self.current_question:
            return []
        
        results = []
        question = self.current_question
        base_points = self.quiz_config["base_points"]
        time_bonus_multiplier = self.quiz_config["time_bonus_multiplier"]
        
        # Process answers efficiently
        for player_id, answer_data in question.answers.items():
            if player_id not in self.players:
                continue
                
            player = self.players[player_id]
            is_correct = answer_data["option"] == question.correct_answer
            
            # Calculate time bonus (faster answers get more points)
            time_taken = answer_data["timestamp"] - question.start_time
            time_remaining = max(0, question.time_limit - time_taken)
            time_bonus = int(time_remaining * time_bonus_multiplier) if is_correct else 0
            
            question_score = base_points + time_bonus if is_correct else 0
            
            # Update player's total score
            if is_correct:
                player.score += question_score
            
            results.append({
                "name": player.username,
                "score": player.score,
                "time": round(time_taken, 2),
                "correct": is_correct,
                "question_score": question_score
            })
        
        # Efficient sorting and return top performers
        results.sort(key=lambda x: (-x["score"], x["time"]))  # Score desc, time asc for tiebreaker
        return results[:10]  # Return top 10 instead of 5 for better competition
    
    def get_full_leaderboard(self) -> List[Dict[str, Any]]:
        """Get complete leaderboard of all players"""
        leaderboard = []
        
        for player in self.players.values():
            if player.connected:  # Only include active players
                leaderboard.append({
                    "name": player.username,
                    "score": player.score,
                    "connected": player.connected
                })
        
        # Sort by score (descending)
        leaderboard.sort(key=lambda x: x["score"], reverse=True)
        return leaderboard

# In-memory storage
class GameStorage:
    def __init__(self):
        self.sessions: Dict[str, GameSession] = {}
    
    def create_session(self, room_code: str, host_id: str, host_ws: Any, quiz_config: Dict[str, Any] = None) -> GameSession:
        config = quiz_config or {
            "question_time_limit": 30,
            "base_points": 100,
            "time_bonus_multiplier": 2
        }
        
        session = GameSession(
            room_code=room_code,
            host_id=host_id,
            host_ws=host_ws,
            created_at=time.time(),
            quiz_config=config
        )
        self.sessions[room_code] = session
        return session
    
    def get_session(self, room_code: str) -> Optional[GameSession]:
        return self.sessions.get(room_code)
    
    def remove_session(self, room_code: str) -> None:
        if room_code in self.sessions:
            del self.sessions[room_code]
    
    def cleanup_inactive_sessions(self, max_age_hours: int = 2) -> int:
        """Clean up inactive sessions and return count of removed sessions"""
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        
        to_remove = []
        for room_code, session in self.sessions.items():
            # Remove if inactive, old, or has no connected players
            if (not session.is_active or 
                (current_time - session.created_at) > max_age_seconds or
                session.get_player_count() == 0):
                to_remove.append(room_code)
        
        removed_count = len(to_remove)
        for room_code in to_remove:
            self.remove_session(room_code)
        
        return removed_count
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """Get memory usage statistics"""
        total_sessions = len(self.sessions)
        total_players = sum(len(session.players) for session in self.sessions.values())
        active_players = sum(session.get_player_count() for session in self.sessions.values())
        
        return {
            "total_sessions": total_sessions,
            "total_players": total_players,
            "active_players": active_players,
            "avg_players_per_room": round(active_players / max(total_sessions, 1), 2)
        }

# Global game storage instance
game_storage = GameStorage()
