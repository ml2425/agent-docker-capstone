# Docker Deployment Guide

This guide explains how to containerize and deploy the Medical MCQ Writer Agent using Docker.

## Overview

The application is containerized for deployment on cloud platforms such as Google Cloud Run, AWS ECS, Azure Container Instances, Railway, Fly.io, and other Docker-compatible platforms.

## Prerequisites

- Docker installed on your local machine (for testing)
- Docker account or container registry access (for cloud deployment)
- API keys for the LLM services you plan to use

## Building the Docker Image

### Local Build

```bash
# Build the image
docker build -t mcq-generator .

# Verify the image was created
docker images | grep mcq-generator
```

### Build with Tag (for registry push)

```bash
# Tag for Google Container Registry
docker build -t gcr.io/YOUR_PROJECT_ID/mcq-generator:latest .

# Tag for Docker Hub
docker build -t YOUR_DOCKERHUB_USERNAME/mcq-generator:latest .
```

## Running the Container Locally

### Basic Run

```bash
docker run -p 7860:7860 \
  -e GEMINI_API_KEY=your_gemini_key_here \
  -e OPENAI_API_KEY=your_openai_key_here \
  mcq-generator
```

The application will be available at `http://localhost:7860`

### Run with All Environment Variables

```bash
docker run -p 7860:7860 \
  -e GEMINI_API_KEY=your_gemini_key \
  -e OPENAI_API_KEY=your_openai_key \
  -e TAVILY_API_KEY=your_tavily_key \
  -e NCBI_EMAIL=your_email@example.com \
  -e PORT=7860 \
  mcq-generator
```

### Run in Detached Mode

```bash
docker run -d -p 7860:7860 \
  -e GEMINI_API_KEY=your_key \
  --name mcq-generator \
  mcq-generator

# View logs
docker logs mcq-generator

# Stop container
docker stop mcq-generator
```

### Run with Custom Port

```bash
# Container listens on port 8080 (set via PORT env var)
docker run -p 8080:8080 \
  -e PORT=8080 \
  -e GEMINI_API_KEY=your_key \
  mcq-generator
```

## Environment Variables

### Required

- **GEMINI_API_KEY** (or **GOOGLE_API_KEY**): Required for Gemini LLM and image generation
- **OPENAI_API_KEY**: Optional, required if using ChatGPT 4o mini

### Optional

- **TAVILY_API_KEY**: For Tavily search integration (used with ChatGPT)
- **NCBI_EMAIL**: Email for PubMed API (recommended)
- **PORT**: Port number for the application (default: 7860)
  - Cloud Run sets this automatically
  - For local testing, defaults to 7860 if not set

### Database URLs (Advanced)

- **DATABASE_URL**: SQLite database URL (default: `sqlite:///./medical_mcq.db`)
- **SESSION_DB_URL**: Session database URL (default: `sqlite:///./agent_sessions.db`)

Note: In containerized deployments, databases are ephemeral (created fresh on each container start). For production persistence, consider using external databases or volume mounts.

## Deployment to Google Cloud Run

### Prerequisites

1. Google Cloud Project with billing enabled
2. Cloud Run API enabled
3. Cloud Build API enabled
4. Artifact Registry API enabled (for image storage)

### Method 1: Build and Push Using Cloud Shell (Recommended)

This method uses Google Cloud Shell (browser-based) and doesn't require local Docker or gcloud CLI installation.

#### Step 1: Open Cloud Shell

1. Go to: https://shell.cloud.google.com
2. Cloud Shell opens in your browser (free to use)

#### Step 2: Clone Your Repository

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
cd YOUR_REPO
git checkout docker-deployment  # or main, depending on your branch
```

#### Step 3: Create Artifact Registry Repository (One-Time Setup)

```bash
# Set your project
gcloud config set project YOUR_PROJECT_ID

# Create repository
gcloud artifacts repositories create mcq-repo \
  --repository-format=docker \
  --location=us-central1 \
  --description="MCQ Generator Docker images"
```

#### Step 4: Build and Push Image

```bash
# Build and push in one command (uses Cloud Build)
gcloud builds submit --tag us-central1-docker.pkg.dev/YOUR_PROJECT_ID/mcq-repo/mcq-generator:latest .
```

This command:
- Builds the Docker image using Cloud Build
- Pushes it to Artifact Registry
- Takes 5-10 minutes for first build

#### Step 5: Deploy from Image in Cloud Run Console

1. Go to [Cloud Run Console](https://console.cloud.google.com/run)
2. Click "Create Service" (or edit existing service)
3. Select **"Deploy one revision from an existing container image"**
4. Enter image URL: `us-central1-docker.pkg.dev/YOUR_PROJECT_ID/mcq-repo/mcq-generator:latest`
5. Continue with configuration (see "Deploy via Console" section below)

### Method 2: Build Locally and Push (Alternative)

If you prefer to build locally:

```bash
# Set your project ID
export PROJECT_ID=your-project-id

# Authenticate Docker with Artifact Registry
gcloud auth configure-docker us-central1-docker.pkg.dev

# Build locally
docker build -t us-central1-docker.pkg.dev/$PROJECT_ID/mcq-repo/mcq-generator:latest .

# Push to Artifact Registry
docker push us-central1-docker.pkg.dev/$PROJECT_ID/mcq-repo/mcq-generator:latest
```

**Note**: Requires Docker Desktop running and gcloud CLI installed locally.

### Deploy to Cloud Run

```bash
gcloud run deploy mcq-generator \
  --image gcr.io/$PROJECT_ID/mcq-generator:latest \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars GEMINI_API_KEY=your_key,OPENAI_API_KEY=your_key \
  --memory 1Gi \
  --cpu 1 \
  --port 8080
```

### Deploy via Console

1. Go to [Cloud Run Console](https://console.cloud.google.com/run)
2. Click "Create Service" (or "EDIT & DEPLOY NEW REVISION" for existing service)
3. Select **"Deploy one revision from an existing container image"**
4. Enter image URL: `us-central1-docker.pkg.dev/YOUR_PROJECT_ID/mcq-repo/mcq-generator:latest`
   - Replace `YOUR_PROJECT_ID` with your actual project ID
   - Replace `us-central1` with your region if different
5. Configure:
   - **Service name**: `mcq-generator`
   - **Region**: Choose your region (e.g., `us-central1`, `europe-west1`)
   - **Authentication**: Allow unauthenticated invocations (for public access)
6. Under "Variables & Secrets" tab:
   - Click "ADD VARIABLE"
   - Add environment variables:
     - `GEMINI_API_KEY`: Your Gemini API key (required)
     - `PORT`: `8080` (optional - Cloud Run sets this automatically)
     - `OPENAI_API_KEY`: Your OpenAI API key (optional)
     - `TAVILY_API_KEY`: Your Tavily key (optional)
     - `NCBI_EMAIL`: Your email for PubMed (optional)
7. Under "Container" tab:
   - **Port**: 8080 (Cloud Run sets `$PORT` automatically)
   - **Memory**: 1 GiB (recommended minimum, can use 512 MiB for cost savings)
   - **CPU**: 1 (can be reduced to 0.5 to save costs)
   - **Startup timeout**: 240 seconds (maximum allowed)
   - **Min instances**: 0 (scales to zero when idle - saves costs)
   - **Max instances**: 2-10 (adjust based on expected traffic)
8. Click "CREATE" (or "DEPLOY" for existing service)

### Access Your Deployed Service

After deployment, Cloud Run provides a URL like:
```
https://mcq-generator-xxxxx-uc.a.run.app
```

## Deployment to Other Platforms

### Railway

1. Connect your GitHub repository
2. Railway auto-detects Dockerfile
3. Add environment variables in Railway dashboard:
   - `GEMINI_API_KEY`
   - `OPENAI_API_KEY`
   - `PORT` (Railway sets this automatically)
4. Deploy

### Fly.io

```bash
# Install flyctl
# Create fly.toml (or use: fly launch)

# Deploy
fly deploy

# Set secrets
fly secrets set GEMINI_API_KEY=your_key
fly secrets set OPENAI_API_KEY=your_key
```

### AWS ECS/Fargate

1. Build and push to Amazon ECR
2. Create task definition with environment variables
3. Deploy service

### Azure Container Instances

```bash
az container create \
  --resource-group myResourceGroup \
  --name mcq-generator \
  --image mcq-generator:latest \
  --environment-variables GEMINI_API_KEY=your_key \
  --ports 7860
```

## Testing the Container

### Quick Health Check

```bash
# Build and run
docker build -t mcq-generator .
docker run -d -p 7860:7860 \
  -e GEMINI_API_KEY=dummy_key \
  --name mcq-test \
  mcq-generator

# Wait a few seconds for startup
sleep 5

# Check if container is running
docker ps | grep mcq-test

# Check logs
docker logs mcq-test

# Test HTTP endpoint
curl http://localhost:7860

# Cleanup
docker stop mcq-test
docker rm mcq-test
```

### Verify Port Configuration

```bash
# Test with custom port
docker run -d -p 8080:8080 \
  -e PORT=8080 \
  -e GEMINI_API_KEY=dummy \
  --name mcq-port-test \
  mcq-generator

# Verify it's listening on 8080
curl http://localhost:8080

# Cleanup
docker stop mcq-port-test && docker rm mcq-port-test
```

## Container Details

### Image Size

- Base image: `python:3.11-slim` (~150MB)
- Dependencies: ~200-300MB
- Application code: ~5-10MB
- **Total**: ~400-500MB

### Resource Requirements

- **Memory**: Minimum 512MB, recommended 1GB
- **CPU**: 1 vCPU sufficient for moderate usage
- **Storage**: Ephemeral (databases and media created fresh on each start)

### Port Configuration

- Default port: `7860`
- Cloud Run: Uses `$PORT` environment variable (typically `8080`)
- The application automatically reads `PORT` env var and falls back to `7860` if not set

## Troubleshooting

### Container Won't Start

1. Check logs: `docker logs <container_name>` (for local testing)
2. For Cloud Run: Check logs in Cloud Run → Your service → LOGS tab
3. Verify environment variables are set correctly
4. Ensure port is not already in use: `docker ps`

### Application Not Accessible (503 Service Unavailable)

1. **Check Cloud Run logs** for Python errors or tracebacks
2. **Verify environment variables** are set (especially `GEMINI_API_KEY`)
3. **Increase startup timeout** to 240 seconds (maximum)
4. **Check revision status** - should show "Ready" not "Not Ready"
5. Common issues:
   - Missing API keys causing app crash
   - Import errors (check logs)
   - Database initialization errors
   - Port binding issues

### FileNotFoundError for Schema File

If you see: `FileNotFoundError: .../schema/schema.yaml`

- **Solution**: Schema file is now in `app/schema/schema.yaml` (moved from `plan/schema/`)
- The file is automatically included when building from `app/` directory
- No special configuration needed - it's part of the application code

### Application Not Accessible (Local)

1. Verify `server_name="0.0.0.0"` in `app.py` (already configured)
2. Check port mapping: `-p HOST_PORT:CONTAINER_PORT`
3. For Cloud Run: Ensure service allows unauthenticated access

### Database Issues

- SQLite databases are created automatically on first run
- In ephemeral deployments, data is lost on container restart
- For persistence, use volume mounts or external databases

### API Key Errors

- Verify environment variables are set correctly in Cloud Run console
- Check API key format (no extra spaces or quotes)
- Ensure API keys have proper permissions
- For Cloud Run: Use "Variables & Secrets" tab, not "Secrets" tab

## Security Best Practices

1. **Never commit API keys** to Git
2. **Use environment variables** for all secrets
3. **Use Secret Manager** (Cloud Run Secret Manager, AWS Secrets Manager, etc.) for production
4. **Restrict container access** (use authentication for production deployments)
5. **Keep base images updated** (regularly rebuild with latest security patches)

## Notes

- The container uses ephemeral storage: databases and media files are created fresh on each container start
- This is suitable for demos and competition submissions
- **Schema file location**: The schema file (`schema.yaml`) is located in `app/schema/` directory and is automatically included in the Docker image as part of the application code
- For production with data persistence, consider:
  - Volume mounts for databases
  - Cloud storage for media files
  - External database services (PostgreSQL, etc.)

## Recommended Deployment Method

**For Cloud Run deployment, use Method 1 (Cloud Shell)** as described above:
- No local Docker or gcloud CLI installation required
- Uses Cloud Build (free tier: 120 build-minutes/day)
- Most reliable method for first-time deployment
- Browser-based, works from any computer

## Support

For issues or questions:
1. Check container logs: `docker logs <container_name>`
2. Verify environment variables are set correctly
3. Test locally before deploying to cloud
4. Review platform-specific documentation for deployment issues

