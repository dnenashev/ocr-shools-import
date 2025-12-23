#!/bin/bash
# Start script for Render deployment

# Create uploads directory if it doesn't exist
mkdir -p uploads

# Run the application
uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}

