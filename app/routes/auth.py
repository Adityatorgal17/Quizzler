from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from typing import Optional
from app.database import supabase, supabase_admin, db
from app.utils.auth_utils import get_current_user
import logging

router = APIRouter()

class SignUpRequest(BaseModel):
    email: EmailStr
    password: str
    name: str

class SignInRequest(BaseModel):
    email: EmailStr
    password: str

class AuthResponse(BaseModel):
    message: str
    user: dict
    access_token: Optional[str] = None

@router.post("/signup", response_model=AuthResponse)
async def signup(request: SignUpRequest):
    """Sign up a new user using Supabase Auth"""
    try:
        auth_response = supabase.auth.sign_up({
            "email": request.email,
            "password": request.password,
            "options": {
                "data": {
                    "name": request.name
                }
            }
        })

        if auth_response.user:
            user_data = {
                "id": auth_response.user.id,
                "name": request.name,
                "email": request.email
            }
            
            db_user = db.insert("users", user_data)
            
            return AuthResponse(
                message="User created successfully. Please check your email for verification.",
                user={
                    "id": db_user["id"],
                    "name": db_user["name"],
                    "email": db_user["email"],
                    "email_confirmed": auth_response.user.email_confirmed_at is not None
                },
                access_token=auth_response.session.access_token if auth_response.session else None
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create user"
            )
            
    except Exception as e:
        logging.error(f"Signup error: {e}")
        if "already registered" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Signup failed: {str(e)}"
        )

@router.post("/signin", response_model=AuthResponse)
async def signin(request: SignInRequest):
    """Sign in user using Supabase Auth"""
    try:
        auth_response = supabase.auth.sign_in_with_password({
            "email": request.email,
            "password": request.password
        })
        
        if auth_response.user and auth_response.session:
            return AuthResponse(
                message="Login successful",
                user={
                    "id": auth_response.user.id,
                    "email": auth_response.user.email,
                    "name": auth_response.user.user_metadata.get("name", ""),
                    "email_confirmed": auth_response.user.email_confirmed_at is not None
                },
                access_token=auth_response.session.access_token
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )
            
    except Exception as e:
        logging.error(f"Signin error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

@router.post("/signout")
async def signout(current_user: dict = Depends(get_current_user)):
    """Sign out user"""
    try:
        supabase.auth.sign_out()
        return {"message": "Signed out successfully"}
    except Exception as e:
        logging.error(f"Signout error: {e}")
        return {"message": "Signed out"}

@router.get("/me")
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """Get current user information"""
    try:
        users = db.select("users", "*", {"id": current_user["id"]})
        
        if not users:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        db_user = users[0]
        return {
            "id": db_user["id"],
            "name": db_user["name"],
            "email": db_user["email"],
            "created_at": db_user["created_at"]
        }
    except Exception as e:
        logging.error(f"Get user info error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get user information"
        )

@router.get("/verify-token")
async def verify_token(current_user: dict = Depends(get_current_user)):
    """Verify if token is valid"""
    return {
        "valid": True,
        "user": current_user
    }