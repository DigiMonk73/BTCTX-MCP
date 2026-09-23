# ------------------------------------------------------------------
# Stage 1: Frontend Builder
# ------------------------------------------------------------------
    # Built on the build machine's own architecture: the output is static files,
    # so a multi-arch build doesn't have to run npm under emulation.
    FROM --platform=$BUILDPLATFORM node:22-slim AS frontend-builder

    # 1) Create and move into /app/frontend
    WORKDIR /app/frontend
    
    # 2) Copy package.json + package-lock.json (or yarn.lock) for the frontend
    COPY frontend/package*.json ./
    
    # 3) Install dependencies (includes devDependencies, used for build)
    RUN npm ci
    
    # 4) Copy the rest of your frontend source
    COPY frontend/ ./
    
    # 5) Build the React/Vite app into /app/frontend/dist
    RUN npm run build
    
    # ------------------------------------------------------------------
    # Stage 2: Final (Backend + Frontend)
    # ------------------------------------------------------------------
    FROM python:3.11-slim AS backend
    
    # Ensures stdout/stderr is unbuffered, so logs appear immediately
    ENV PYTHONUNBUFFERED=1
    # Avoid caching pip packages
    ENV PIP_NO_CACHE_DIR=1
    # Database (and the session key beside it) live on the /data volume.
    # Without this the DB would land in /app/backend and vanish on update.
    ENV DATABASE_FILE=/data/btctx.db
    
    # No system packages needed: IRS forms are filled in pure Python (pypdf)

    # Create the /app directory and /data for DB storage
    WORKDIR /app
    RUN mkdir -p /data && chmod 777 /data
    
    # If you remain root in python:3.11-slim, you don't need chown. 
    # But if you switch to a non-root user, do:
    # RUN adduser --disabled-password --gecos '' appuser && chown -R appuser:appuser /data
    
    # Copy Python deps (requirements.txt) and install
    COPY backend/requirements.txt .
    RUN pip install --no-cache-dir -r requirements.txt
    
    # Copy the backend code, and VERSION where backend/version.py reads it
    COPY backend/ ./backend
    COPY VERSION ./VERSION
    
    # Copy the built frontend artifacts from the first stage
    COPY --from=frontend-builder /app/frontend/dist ./frontend/dist
    
    # Expose port 80 for production
    EXPOSE 80
    
    # Final command: run the FastAPI app with Uvicorn on port 80
    CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "80"]
    