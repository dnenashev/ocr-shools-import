# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Overview

OCR-crm is a web application that recognizes student data from photos using OCR (via OpenRouter API + Gemini), stores the data in MongoDB, and syncs it to AMO CRM. The application consists of a FastAPI backend and vanilla JavaScript frontend.

**Key Technologies:** Python 3.11, FastAPI, MongoDB (Motor), OpenRouter API, AMO CRM API, async/await patterns.

## Essential Commands

### Development Setup

**First time only:**
```bash
python -m venv venv
source venv/bin/activate  # Mac/Linux
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys and configuration
```

### Running the Application

**Development (with auto-reload):**
```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Then access:
- Main app: http://localhost:8000
- Admin panel: http://localhost:8000/admin
- API docs: http://localhost:8000/docs

**Production (without reload):**
```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Testing

There is no automated test suite. Test manually via:
- Web UI: Upload photos and verify OCR extraction
- API docs: Use Swagger UI at `/docs` to test endpoints
- Admin panel: Check data persistence and AMO integration

## Project Architecture

### Backend Structure (`backend/`)

- **main.py** - FastAPI app entry point with lifecycle management (MongoDB connect/disconnect), CORS setup, static file serving
- **config.py** - Settings management via Pydantic (loads from `.env`); uses `lru_cache` singleton pattern for `get_settings()`
- **models/student.py** - Pydantic models for validation and serialization; includes `PyObjectId` for MongoDB ObjectId handling
- **database/mongodb.py** - Motor (async MongoDB) connection and initialization; handles Atlas-specific connection parameters
- **routes/**
  - **upload.py** - Image upload, OCR processing, and student data persistence; endpoints return OCR results for user editing before DB save
  - **admin.py** - Admin authentication (JWT in cookie), student CRUD, AMO sync, statistics, CSV export
- **services/**
  - **ocr.py** - OpenRouter API integration (Gemini 2.0 Flash); prompts for JSON extraction from student photos and feedback forms
  - **amo.py** - AMO CRM API wrapper; creates contacts and leads, searches by phone, verifies lead status, handles tag management

### Frontend Structure (`frontend/`)

- **upload.html** - Student enrollment form; captures photo, allows data editing before submission
- **admin.html** - Admin dashboard for reviewing submissions and sending to AMO
- **admin.js/admin.css** - Admin panel functionality (login, list students, export, send to AMO)

### Data Flow

1. User uploads photo via upload.html
2. Photo sent to `/api/upload` → processed by OCR service (OpenRouter API)
3. Extracted data returned to frontend for editing (NOT saved yet)
4. User confirms data → sent to `/api/upload/save` → stored in MongoDB
5. Admin reviews in `/admin` panel
6. Admin clicks "Send to AMO" → `/api/admin/send-to-amo` → creates contacts/leads in AMO CRM
7. Student record updated with AMO contact/lead IDs

## Key Configuration

### Environment Variables (`.env`)

**Required:**
- `OPENROUTER_API_KEY` - OpenRouter API key for Gemini vision model
- `MONGODB_URI` - MongoDB connection string (MongoDB Atlas or local)
- `ADMIN_PASSWORD` - Admin panel password

**AMO CRM Integration:**
- `AMO_REDIRECT_URI` - AMO domain (e.g., `https://pk1amomabiuru.amocrm.ru`)
- `INTEGRATION_ID` - AMO integration/client ID
- `AMO_SECRET_KEY` - AMO client secret
- `AMO_LONG_TOKEN` - AMO access token (JWT)
- `AMO_SHORT_KEY` - AMO refresh token
- `AMO_CORRECT_PIPELINE_ID` - Pipeline ID for storing synced leads (default: 7797890)

**Optional:**
- `CORS_ORIGINS` - CORS allowed origins (default: "*")
- `UPLOAD_DIR` - Directory for temporary uploads (default: "uploads")

### MongoDB

Uses Motor (async driver). Collections: `students` with indexed fields `created_at` and `sent_to_amo`. On Render, consider using MongoDB GridFS for file storage instead of ephemeral filesystem.

## Architecture Patterns

### Async/Await

All database, external API calls use async patterns (`AsyncIOMotorClient`, `httpx.AsyncClient`). Batch processing uses `asyncio.gather()` for parallelism.

### Error Handling in OCR

`process_image_ocr()` and `process_feedback_image_ocr()` handle JSON parsing from Gemini responses, stripping markdown blocks if present, and validate ratings (1-10).

### Token Refresh

AMO service automatically refreshes `access_token` using `refresh_token` when receiving 401 responses.

### Deduplication

`find_lead_by_phone()` searches existing leads by phone before creating new contacts, filtered by pipeline and tag to prevent duplicates.

## Important Implementation Details

### Student Data Model

Core fields: `fio`, `school`, `class`, `phone`, `application_type`. Optional: `parent_name`, `parent_phone`, `masterclass_rating`, `speaker_rating`, `feedback`, `image_paths` (list for multiple photos). Fields like `sent_to_amo`, `amo_contact_id`, `amo_lead_id` track sync status.

### Image Handling

Images are temporarily saved during upload, sent to OCR API as base64, then stored via `image_paths` list (allows multiple photos per student). On Render, ephemeral filesystem means images are lost after deploy; consider GridFS for production.

### OCR Prompts

- **Student data (page 1):** Extract FIO, school, class, phone, optional parent info
- **Feedback (page 2):** Extract 1-10 ratings for masterclass/speaker, free-form feedback text

Both use low temperature (0.1) for consistency. JSON extraction handles markdown-wrapped responses.

### Admin Authentication

JWT tokens stored in `admin_token` httponly cookie with 60-minute expiration. No database-persisted sessions; purely stateless token validation.

### CSV Export

Includes BOM (UTF-8 with `\ufeff`) for proper Excel display. Supports filtering by `sent_to_amo` status and FIO search.

## Common Tasks

### Adding a New Student Field

1. Update `StudentBase` and related models in `backend/models/student.py`
2. Update OCR prompts in `backend/services/ocr.py` if field should be auto-extracted
3. Update form in `frontend/upload.html`
4. Update MongoDB document structure expectations in routes

### Debugging OCR Issues

- Check OpenRouter API response in logs (status, error message)
- Verify `OPENROUTER_API_KEY` is valid
- Test with simple images first; check prompt clarity
- Review raw OCR response in browser console or admin panel

### Debugging AMO Integration

- Verify tokens haven't expired (check `AMO_LONG_TOKEN` in `.env`)
- Confirm pipeline ID and tag names match AMO setup
- Check `amo.py` logs for 401/403/404 responses
- Use `/api/admin/verify-amo` to detect orphaned/moved leads

## Deployment

Uses `render.yaml` for Render.com deployment. Python 3.11, uvicorn workers, automatic build and start. Set all required env vars in Render dashboard. Remember ephemeral filesystem limitation for uploads.
