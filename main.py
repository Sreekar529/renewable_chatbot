from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
import pandas as pd
from fuzzywuzzy import fuzz
from fuzzywuzzy import process
import os
import requests
import random
from datetime import datetime
import uuid

load_dotenv()

app = FastAPI()
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

FAQ_FILE = "FAQ.xlsx"

# OpenAI GPT-4.1 via Azure REST AI Inference API
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
AZURE_ENDPOINT = "https://models.github.ai/inference"
MODEL = "openai/gpt-4.1"

# Chat history storage - in-memory for simplicity
chat_sessions = {}

# Welcome intents
WELCOME_INTENTS = ["hi", "hello", "hey", "good morning", "good afternoon", "good evening", "howdy", "greetings"]

# Enhanced renewable energy context with conversation awareness
RENEWABLE_CONTEXT = """You are an expert Renewable Energy Awareness Chatbot. You know everything about:

- Solar, wind, hydro, geothermal, biomass energy
- Green energy technologies and innovations
- Environmental impact and sustainability
- Energy efficiency and conservation
- Climate change and renewable solutions
- Green revolution and sustainable development

You are an expert about these, you also try to give real life examples and tell how the user can use this energy source
Practical applications on energy resources
Daily use of energy and it's carbon footprint, after effects and all, you know all of these things

You will be a guide to beginners, telling them like they are 8 year olds
For people who already know about these, you tend to explain in detail and more interesting things to them

Consider the conversation history when responding to maintain context and continuity.
Provide accurate, helpful responses about renewable energy. Be friendly and informative."""

def get_or_create_session(session_id):
    """Get or create a chat session"""
    if session_id not in chat_sessions:
        chat_sessions[session_id] = []
    return chat_sessions[session_id]

def add_message_to_history(session_id, message, sender):
    """Add a message to the chat history"""
    chat_history = get_or_create_session(session_id)
    chat_history.append({
        'message': message,
        'sender': sender,
        'timestamp': datetime.now().isoformat()
    })
    
    # Keep only last 20 messages to prevent memory issues
    if len(chat_history) > 20:
        chat_history.pop(0)

def build_conversation_context(chat_history):
    """Build conversation context from chat history"""
    conversation_context = ""
    if chat_history:
        for msg in chat_history[-5:]:  # Use last 5 messages for context
            role = "User" if msg['sender'] == 'user' else "Assistant"
            conversation_context += f"{role}: {msg['message']}\n"
    return conversation_context

def get_faq_answer(user_input):
    """Get answer from FAQ Excel file using fuzzy matching"""
    if not os.path.exists(FAQ_FILE):
        return None, 0
    
    try:
        faq_df = pd.read_excel(FAQ_FILE)
        if 'Question' not in faq_df.columns or 'Answer' not in faq_df.columns:
            return None, 0
        
        questions = faq_df['Question'].astype(str).tolist()
        best_match, score = process.extractOne(user_input, questions, scorer=fuzz.token_set_ratio)
        
        if score >= 70:  # Increased threshold for better accuracy
            answer = faq_df.loc[faq_df['Question'] == best_match, 'Answer'].values[0]
            return answer, score
        
        return None, score
    
    except Exception as e:
        print(f"Error reading FAQ: {e}")
        return None, 0

def is_welcome_intent(user_input):
    """Check if user input is a welcome/greeting intent"""
    return any(greeting in user_input.lower() for greeting in WELCOME_INTENTS)

def get_welcome_response():
    """Generate a friendly welcome response"""
    responses = [
        "Hello! 🌱 Welcome to the Renewable Energy Chatbot! I'm here to help you learn about green energy and sustainable solutions. What would you like to know?",
        "Hi there! 🌿 Great to see you interested in renewable energy! I can help with solar, wind, hydro, geothermal, and biomass energy. What's on your mind?",
        "Hey! 🌍 Welcome to your renewable energy guide! Ask me anything about green energy technologies and sustainability!",
        "Greetings! 🌱 I'm your renewable energy expert! What would you like to explore today?",
        "Do you know what is Renewable Energy? Want to know, then ask me!"
    ]
    
    return random.choice(responses)

def get_gpt41_response_with_context(user_input, session_id):
    """Get response from GPT-4.1 API with conversation context"""
    try:
        chat_history = get_or_create_session(session_id)
        conversation_context = build_conversation_context(chat_history)
        
        # Enhanced prompt with context
        enhanced_prompt = f"""
{RENEWABLE_CONTEXT}

Previous conversation context:
{conversation_context}

Current user question: {user_input}

Please respond considering the conversation history and maintain continuity in the discussion.
"""

        headers = {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": enhanced_prompt},
                {"role": "user", "content": user_input}
            ],
            "temperature": 1,
            "top_p": 1
        }

        response = requests.post(
            f"{AZURE_ENDPOINT}/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )

        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()

    except Exception as e:
        print(f"GPT-4.1 API error: {e}")
        return "I'm experiencing technical difficulties. Please try again."

def get_fallback_response():
    """Generate a fallback response for unclear questions"""
    responses = [
        "I'm not quite sure I understood. Could you please rephrase your question about renewable energy?",
        "That's interesting! Could you clarify what aspect of renewable energy you'd like to know more about?",
        "I want to help you better. Could you provide more details about your renewable energy question?",
        "I'm here to help with renewable energy questions! Could you please rephrase your question?"
    ]
    
    return random.choice(responses)

@app.get("/", response_class=HTMLResponse)
async def landing_page(request: Request):
    """Landing page with introduction"""
    return templates.TemplateResponse("landing.html", {"request": request})

@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    """Chat interface page"""
    return templates.TemplateResponse("chat.html", {"request": request})

@app.post("/api/chat")
async def chat_api(request: Request, user_input: str = Form(...), session_id: str = Form(None)):
    """API endpoint for chat responses with context awareness"""
    user_input = user_input.strip()
    
    if not user_input:
        return JSONResponse({"response": "Please enter a question about renewable energy.", "type": "error"})
    
    # Generate session ID if not provided
    if not session_id:
        session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{random.randint(1000, 9999)}"
    
    # Add user message to history
    add_message_to_history(session_id, user_input, 'user')
    
    # Check for welcome intent
    if is_welcome_intent(user_input):
        response = get_welcome_response()
        response_type = "welcome"
    else:
        # Try FAQ first
        faq_answer, faq_score = get_faq_answer(user_input)
        
        if faq_answer and faq_score >= 70:
            response = faq_answer
            response_type = "faq"
        else:
            # Use GPT-4.1 with context
            response = get_gpt41_response_with_context(user_input, session_id)
            response_type = "ai"
            
            # If response seems generic, use fallback
            if len(response) < 50 or "I'm sorry" in response.lower():
                response = get_fallback_response()
                response_type = "fallback"
    
    # Add assistant response to history
    add_message_to_history(session_id, response, 'assistant')
    
    return JSONResponse({
        "response": response,
        "type": response_type,
        "timestamp": datetime.now().strftime("%H:%M"),
        "user_input": user_input,
        "session_id": session_id
    })

# Additional endpoints for chat management
@app.get("/api/chat/history/{session_id}")
async def get_chat_history(session_id: str):
    """Get chat history for a session"""
    chat_history = get_or_create_session(session_id)
    return JSONResponse({"history": chat_history, "session_id": session_id})

@app.delete("/api/chat/history/{session_id}")
async def clear_chat_history(session_id: str):
    """Clear chat history for a session"""
    if session_id in chat_sessions:
        del chat_sessions[session_id]
    return JSONResponse({"message": "Chat history cleared", "session_id": session_id})

@app.get("/api/chat/sessions")
async def get_active_sessions():
    """Get all active chat sessions"""
    sessions = list(chat_sessions.keys())
    return JSONResponse({"sessions": sessions, "count": len(sessions)})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
