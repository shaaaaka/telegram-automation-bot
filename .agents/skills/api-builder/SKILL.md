---
name: api-builder
description: Best practices for building robust, scalable REST APIs using FastAPI, Pydantic V2, and Python async workflows.
---

# API Builder Guidelines (FastAPI & Python Async)

Use this skill when designing, refactoring, or building HTTP endpoints, WebSocket routers, or backend API services.

## Core Architecture Principles

1. **FastAPI & Router Structure**
   - Keep route handlers thin. Delegate business logic to dedicated service modules (e.g. `services/`).
   - Use `APIRouter` per domain module and include them modularly into `app.py`.
   - Always define explicit `response_model` types for endpoints to ensure clear schemas and auto-generated OpenAPI documentation.

2. **Pydantic V2 Models & Validation**
   - Use Pydantic V2 `BaseModel` with strict type annotations for Request Bodies and Query Parameters.
   - Use `Field(..., description=..., ge=..., le=...)` for parameter validation and clarity in OpenAPI docs.
   - Separate Input DTOs (e.g., `UserCreateRequest`) from Output DTOs (e.g., `UserResponse`). Never expose raw internal objects or database models directly in responses.

3. **Asynchronous I/O Best Practices**
   - Use `async def` for endpoints that perform non-blocking I/O operations (database queries with `aiosqlite`, HTTP calls via `httpx`/`aiohttp`, external APIs).
   - Never call blocking synchronous I/O or long-running CPU calculations directly inside `async def` handlers without using `run_in_executor` or `anyio.to_thread.run_sync`.

4. **Error Handling & HTTP Status Codes**
   - Raise explicit `HTTPException(status_code=..., detail=...)` or custom exception handlers defined via `@app.exception_handler`.
   - Return standard HTTP status codes:
     - `200 OK` for success, `201 Created` for resource creation, `204 No Content` for deletion.
     - `400 Bad Request` for invalid parameters, `401 Unauthorized` / `403 Forbidden` for auth issues.
     - `404 Not Found` for missing entities, `422 Unprocessable Entity` for schema validation failures.
     - `500 Internal Server Error` for unhandled exceptions (logged silently with full traceback, never leaking credentials to clients).

5. **WebSocket Management**
   - Handshake endpoints must manage connection lifecycles cleanly (`await websocket.accept()`, `try ... finally: websocket.close()`).
   - Handle disconnects gracefully without crashing event loops (`WebSocketDisconnect` exception handling).
