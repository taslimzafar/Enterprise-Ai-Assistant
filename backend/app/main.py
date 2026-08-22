import os

from dotenv import load_dotenv
from fastapi import FastAPI
from openai import OpenAI

load_dotenv()
print("API KEY LOADED:", bool(os.getenv("OPENAI_API_KEY")))

app = FastAPI(
    title="Enterprise AI Assistant",
    description="Agentic Knowledge & Workflow Assistant",
    version="0.1.0"
)

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)


@app.get("/")
def root():
    return {
        "message": "Enterprise AI Assistant API is running!"
    }


@app.get("/ask")
def ask_ai(question: str):
    response = client.responses.create(
        model="gpt-5-mini",
        input=question
    )

    return {
        "question": question,
        "answer": response.output_text
    }