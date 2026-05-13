"""
Nistula Guest Message Handler
==============================
FastAPI application that receives guest messages via webhook,
normalises them into a unified schema, classifies the query type,
sends to Claude AI for a drafted reply, and returns the result
with a confidence score.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.routes.webhook import router as webhook_router

app = FastAPI(
    title="Nistula Guest Message Handler",
    description="AI-powered guest messaging system for Nistula hospitality platform.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhook_router, prefix="/webhook", tags=["Webhook"])


@app.get("/", tags=["Health"])
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "Nistula Guest Message Handler"}
