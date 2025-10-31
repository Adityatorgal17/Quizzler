from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from datetime import datetime, timedelta
import json
import re
from typing import List, Optional
from uuid import uuid4
import pytz
from google import genai
from app.config import settings
from app.database import db
from app.utils.auth_utils import get_current_user, is_admin_user

IST = pytz.timezone('Asia/Kolkata')

router = APIRouter()

client = genai.Client(api_key=settings.gemini_api_key.get_secret_value())

GEMINI_PROMPT = """
You are a QuizBot integrated into a quiz creation platform.
Your ONLY purpose is to create quizzes when users request quiz creation.

CRITICAL: First analyze if the user input is actually requesting quiz creation.

INTENT DETECTION:
- Quiz creation intents: "create quiz", "make quiz", "generate quiz", "build quiz", "quiz on/about", "I want a quiz", etc.
- Non-quiz intents: greetings ("hey", "hello", "hi"), general questions, casual conversation, unrelated topics

RESPONSE RULES:
1. IF the input is NOT about creating a quiz (greetings, general chat, unrelated topics):
   Return this EXACT JSON:
   {{
     "intent": "non_quiz",
     "message": "I'm a Quiz Creation Bot. I can only help you create quizzes. Please describe the quiz you want to create, for example: 'Create a quiz on Python programming with 10 questions' or 'Make a history quiz about World War 2 with 15 questions, duration 45 minutes'."
   }}

2. IF the input IS about creating a quiz:
   Parse the requirements and return this JSON structure:
   {{
     "intent": "quiz_creation",
     "title": "<create a catchy title based on the topic>",
     "description": "<create a detailed description of what the quiz covers>",
     "duration": <duration in minutes>,
     "positive_mark": <marks for correct answer>,
     "negative_mark": <marks deducted for wrong answer>,
     "navigation_type": "omni",
     "tab_switch_exit": true,
     "start_time": "<ISO datetime string in IST timezone or null>",
     "end_time": "<ISO datetime string in IST timezone or null>",
     "is_trivia": false,
     "questions": [
       {{
         "question_text": "<question text max 500 chars>",
         "option_a": "<option A max 200 chars>",
         "option_b": "<option B max 200 chars>",
         "option_c": "<option C max 200 chars>",
         "option_d": "<option D max 200 chars>",
         "correct_option": "<a, b, c, or d>"
       }}
     ]
   }}

Current IST time: {current_time}

IMPORTANT: Return ONLY valid JSON. Do NOT include markdown fences, explanations, or extra text.

Quiz Creation Rules (only when intent is quiz_creation):
1. Generate the requested number of questions (default: 10, max: 20)
2. Each question must have exactly 4 options (a, b, c, d)
3. Only one correct answer per question
4. Questions should be clear and unambiguous
5. Options should be plausible but only one correct
6. For relative times like "10 minutes from now", calculate the actual IST datetime
7. If start_time is specified, calculate end_time as start_time + duration
8. Use IST timezone format: YYYY-MM-DDTHH:MM:SS+05:30

Examples of quiz creation requests:
- "Create a quiz on cars with 10 questions"
- "Make a Python programming quiz with 15 questions, 45 minutes long"
- "Generate a history quiz about World War 2, 12 questions, start tomorrow at 2 PM"
- "I want a science quiz on physics, 8 questions, 30 minutes duration"

Examples of non-quiz requests:
- "Hey", "Hello", "Hi there"
- "How are you?"
- "What's the weather?"
- "Tell me a joke"
- "What can you do?"
"""


class QuizPrompt(BaseModel):
    prompt: str  # Natural language input from user

class QuestionCreate(BaseModel):
    question_text: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_option: str  
    
    def validate_lengths(self):
        if len(self.question_text) > 500:
            raise ValueError("Question text cannot exceed 500 characters")
        if len(self.option_a) > 200:
            raise ValueError("Option A cannot exceed 200 characters")
        if len(self.option_b) > 200:
            raise ValueError("Option B cannot exceed 200 characters")
        if len(self.option_c) > 200:
            raise ValueError("Option C cannot exceed 200 characters")
        if len(self.option_d) > 200:
            raise ValueError("Option D cannot exceed 200 characters")
        if self.correct_option not in ['a', 'b', 'c', 'd']:
            raise ValueError("Correct option must be 'a', 'b', 'c', or 'd'")

class QuizCreate(BaseModel):
    title: str
    description: str
    is_trivia: bool = False
    topic: Optional[str] = None
    start_time: Optional[str] = None 
    end_time: Optional[str] = None   
    duration: int = 60  
    positive_mark: int = 1
    negative_mark: int = 0  
    navigation_type: str = "omni"
    tab_switch_exit: bool = True
    difficulty: Optional[str] = None
    questions: List[QuestionCreate] = []

@router.get("/")
async def chatbot_greeting(current_user: dict = Depends(get_current_user)):
    """Chatbot greeting and instructions"""
    return {
        "message": "Hello! I'm your QuizBot assistant. I can ONLY help you create quizzes.",
        "purpose": "I'm designed specifically for quiz creation - not for general conversation.",
        "instructions": "To create a quiz, describe what kind of quiz you want in plain English!",
        "input_format": {
            "prompt": "Your natural language description of the quiz you want to create"
        },
        "examples": [
            "Create a quiz on cars with 10 questions, duration 20 minutes",
            "I want a Python programming quiz with 15 questions, 45 minutes long",
            "Generate a history quiz about World War 2, 12 questions",
            "Make a science quiz on physics, 8 questions, 30 minutes duration",
            "Create a general knowledge quiz, 20 questions, 2 marks per question"
        ],
        "supported_features": [
            "Any topic or subject",
            "Custom number of questions (1-20)",
            "Duration in minutes",
            "Start time scheduling",
            "Positive and negative marking"
        ],
        "usage": "POST /chatbot/generate with body: { \"prompt\": \"your quiz creation request\" }",
        "important_note": "⚠️ I will only respond to quiz creation requests. For greetings or general questions, I'll politely redirect you to describe the quiz you want to create."
    }

def create_quiz_internal(quiz_data: QuizCreate, current_user: dict):
    """Internal function to create a new quiz"""
    try:
        if len(quiz_data.questions) > 50:
            raise HTTPException(status_code=400, detail="Maximum 50 questions allowed per quiz")
        
        if len(quiz_data.questions) < 1:
            raise HTTPException(status_code=400, detail="At least 1 question is required")

        for i, question in enumerate(quiz_data.questions):
            try:
                question.validate_lengths()
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Question {i+1}: {str(e)}")
        
        current_time = datetime.now(IST)
        start_time = None
        end_time = None

        if quiz_data.start_time:
            try:
                start_dt = datetime.fromisoformat(
                    quiz_data.start_time.replace('Z', '+00:00')
                ).astimezone(IST)

                if start_dt <= current_time:
                    raise HTTPException(
                        status_code=400,
                        detail="Start time must be in the future for scheduled quizzes"
                    )

                start_time = start_dt.isoformat()
                end_dt = start_dt + timedelta(minutes=quiz_data.duration)
                end_time = end_dt.isoformat()
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid start_time format. Use ISO format.")

        elif quiz_data.end_time:
            try:
                end_dt = datetime.fromisoformat(
                    quiz_data.end_time.replace('Z', '+00:00')
                ).astimezone(IST)
                start_dt = end_dt - timedelta(minutes=quiz_data.duration)

                if start_dt <= current_time:
                    raise HTTPException(
                        status_code=400,
                        detail="Quiz duration too long for the specified end time"
                    )

                start_time = start_dt.isoformat()
                end_time = end_dt.isoformat()
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid end_time format. Use ISO format.")
        
        quiz = {
            "id": str(uuid4()),
            "title": quiz_data.title,
            "description": quiz_data.description,
            "creator_id": current_user["id"],
            "is_trivia": False,  # Chatbot only creates regular quizzes
            "topic": None,
            "start_time": start_time,
            "end_time": end_time,
            "duration": quiz_data.duration,
            "positive_mark": quiz_data.positive_mark,
            "negative_mark": quiz_data.negative_mark,
            "navigation_type": quiz_data.navigation_type,
            "tab_switch_exit": quiz_data.tab_switch_exit,
            "difficulty": None,
            "popularity": 0,
            "is_active": True,
            "created_at": datetime.now(IST).isoformat()
        }
        
        created_quiz = db.insert("quizzes", quiz)
        
        if quiz_data.questions:
            for question_data in quiz_data.questions:
                question = {
                    "quiz_id": created_quiz["id"],
                    "question_text": question_data.question_text,
                    "option_a": question_data.option_a,
                    "option_b": question_data.option_b,
                    "option_c": question_data.option_c,
                    "option_d": question_data.option_d,
                    "correct_option": question_data.correct_option,
                    "mark": quiz_data.positive_mark
                }
                db.insert("questions", question)
        
        return {"quiz_id": created_quiz["id"], "title": created_quiz["title"]}
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        if "duplicate key value" in error_msg or "unique" in error_msg.lower():
            raise HTTPException(
                status_code=400, 
                detail="A quiz with this title already exists. Please choose a different title."
            )
        raise HTTPException(status_code=400, detail=f"Failed to create quiz: {error_msg}")

def clean_gemini_json(raw_text: str):
    """
    Cleans Gemini model output and extracts valid JSON.
    Handles markdown fences, parentheses, and extra text.
    """
    cleaned = raw_text.strip()

    cleaned = re.sub(r"^```(?:json)?|```$", "", cleaned, flags=re.IGNORECASE | re.MULTILINE).strip()

    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = cleaned[1:-1].strip()

    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise HTTPException(status_code=400, detail=f"Gemini returned no JSON block.\nOutput:\n{raw_text}")

    cleaned = match.group(0)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Gemini returned invalid JSON: {e}\nCleaned Output:\n{cleaned}")


@router.post("/generate")
async def generate_quiz(prompt: QuizPrompt, current_user: dict = Depends(get_current_user)):
    """Generate quiz questions automatically using Gemini AI from natural language input"""
    try:
        current_ist_time = datetime.now(IST)
        
        detailed_prompt = GEMINI_PROMPT.format(current_time=current_ist_time.isoformat())
        
        full_prompt = f"""
        {detailed_prompt}
        
        User's natural language input:
        "{prompt.prompt}"
        
        Parse this input and generate a complete quiz with questions. Make sure to:
        1. Extract the topic and create a relevant title and description
        2. Parse any time-related information (relative times like "10 minutes from now")
        3. Extract number of questions, duration, marking scheme if mentioned
        4. Generate high-quality questions relevant to the topic
        5. Return only valid JSON in the specified format
        """

        response = client.models.generate_content(
            model="gemini-2.0-flash-exp",
            contents=full_prompt
        )

        if not response.text:
            raise HTTPException(status_code=500, detail="Gemini returned empty response")

        response_json = clean_gemini_json(response.text)
        
        if response_json.get("intent") == "non_quiz":
            return {
                "success": False,
                "intent": "non_quiz",
                "message": response_json.get("message", "I'm a Quiz Creation Bot. Please describe the quiz you want to create."),
                "is_quiz_request": False
            }
        
        if response_json.get("intent") == "quiz_creation":
            quiz_data = {k: v for k, v in response_json.items() if k != "intent"}
            
            quiz_obj = QuizCreate(**quiz_data)
            
            if len(quiz_obj.questions) < 1:
                raise HTTPException(status_code=400, detail="Quiz must have at least 1 question")
            elif len(quiz_obj.questions) > 20:
                quiz_obj.questions = quiz_obj.questions[:20]

            result = create_quiz_internal(quiz_obj, current_user)
            
            return {
                "success": True,
                "intent": "quiz_creation",
                "message": f"Quiz '{result['title']}' created successfully! You can view it in your My Quizzes page.",
                "quiz_id": result["quiz_id"],
                "quiz_title": result["title"],
                "questions_generated": len(quiz_obj.questions),
                "redirect_message": "Check your quiz in /my-quizzes page",
                "parsed_from": prompt.prompt,
                "is_quiz_request": True
            }
        else:
            return {
                "success": False,
                "intent": "unclear",
                "message": "I'm a Quiz Creation Bot. I can only help you create quizzes. Please describe the quiz you want to create, for example: 'Create a quiz on Python programming with 10 questions'.",
                "is_quiz_request": False
            }

    except HTTPException:
        raise
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse AI response as JSON: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Quiz generation failed: {str(e)}")