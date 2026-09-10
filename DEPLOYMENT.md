# ORCA Deployment Guide: Production & Cloud Setup

This document provides complete, step-by-step instructions for deploying the **ORCA Marine Decision-Support Platform** to production.

---

## 1. System Architecture Overview

```text
[ User Browser / PWA ]
          │
          ├───► [ Frontend: Next.js 16 (Turbopack + Tailwind v4) ]
          │          │ (Calls public API at NEXT_PUBLIC_ORCA_API_BASE_URL)
          │          ▼
          └───► [ Backend: FastAPI (Python 3.13) ]
                     ├─── In-Memory TTL Cache or Redis
                     ├─── INCOIS Live PFZ Scraper & DMS Parser
                     ├─── Open-Meteo & Copernicus Marine Adapters
                     └─── Google Gemini 2.5/3.7 Flash (Intent Routing & Multilingual Reasoning)
```

---

## 2. Recommended Deployment Methods

Choose the deployment method that fits your infrastructure:

- **Method A: Modern Serverless / Managed Cloud (Recommended)**
  - **Frontend**: [Vercel](https://vercel.com) (Free tier available, global CDN)
  - **Backend**: [Render](https://render.com) or [Railway](https://railway.app) (Docker or Python web service)
- **Method B: Single-Server Docker Deployment**
  - **Platform**: Any Linux VPS (Ubuntu 22.04/24.04 on AWS EC2, DigitalOcean, Hetzner, Linode)
  - **Tooling**: `docker compose up -d` + Caddy / Nginx for automatic HTTPS

---

## 3. Method A: Managed Cloud Deployment (Render + Vercel)

### Step 1: Deploy Backend on Render

1. Push your repository to **GitHub** or **GitLab**.
2. Log into [Render Dashboard](https://dashboard.render.com/) and click **New +** → **Web Service**.
3. Select your repository.
4. Render can automatically detect the included [`render.yaml`](./render.yaml) blueprint, or you can configure it manually:
   - **Name**: `orca-backend`
   - **Region**: Singapore (`singapore`) or closest to India
   - **Environment**: `Docker`
   - **Dockerfile Path**: `./Dockerfile`
   - **Instance Type**: Starter ($7/mo) or Free tier
5. In **Environment Variables**, configure the following:
   ```ini
   APP_NAME=ORCA Base API
   APP_ENV=production
   API_PREFIX=/v1
   CORS_ALLOWED_ORIGINS=["https://your-frontend-domain.vercel.app","http://localhost:3000"]
   ASSISTANT_ENABLED=true
   ASSISTANT_GEMINI_ROUTING_ENABLED=true
   ASSISTANT_MODEL=gemini-3.7-flash
   GOOGLE_API_KEY=your_actual_gemini_api_key_here
   REDIS_ENABLED=false
   ```
   *(Note: `CORS_ALLOWED_ORIGINS` also accepts a simple comma-separated string like `https://your-frontend-domain.vercel.app,http://localhost:3000`)*
6. Click **Create Web Service**. Once built, note your backend URL:
   `https://orca-backend.onrender.com`
7. Test the health endpoint in your browser or terminal:
   ```bash
   curl https://orca-backend.onrender.com/health
   # Expected: {"status":"ok","app_name":"ORCA Base API",...}
   ```

---

### Step 2: Deploy Frontend on Vercel

1. Log into [Vercel](https://vercel.com) and click **Add New...** → **Project**.
2. Select your repository.
3. In **Project Settings**:
   - **Root Directory**: Click *Edit* and select `frontend_candidate`
   - **Framework Preset**: `Next.js`
4. Expand **Environment Variables** and add:
   ```ini
   NEXT_PUBLIC_ORCA_API_BASE_URL=https://orca-backend.onrender.com
   NEXT_PUBLIC_MAP_STYLE_URL=https://tiles.openfreemap.org/styles/liberty
   NEXT_PUBLIC_ORCA_ASSISTANT_MODE=live
   NEXT_PUBLIC_ORCA_DEMO_MODE=false
   NEXT_PUBLIC_ORCA_PRESENTATION_MODE=false
   NEXT_PUBLIC_ORCA_REQUEST_TIMEOUT_MS=90000
   NEXT_PUBLIC_ORCA_DEV_DIAGNOSTICS=false
   ```
5. Click **Deploy**.
6. Once deployed, Vercel will assign a URL like `https://orca-marine.vercel.app`.
7. **Final Step**: Go back to Render (or your backend service), update `CORS_ALLOWED_ORIGINS` with your new Vercel domain, and redeploy the backend.

---

## 4. Method B: Full-Stack Docker Deployment (VPS)

Use this method to host the entire system on a single virtual machine (AWS EC2, DigitalOcean Droplet, Hetzner, etc.).

### Step 1: Server Setup
SSH into your Ubuntu server:
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git docker.io docker-compose-v2
sudo systemctl enable --now docker
```

### Step 2: Clone and Configure
```bash
git clone https://github.com/your-org/orca.git
cd orca

# Create backend environment configuration
cp .env.example .env
nano .env
```
Ensure `.env` contains your Gemini API key and domain:
```ini
GOOGLE_API_KEY=your_gemini_api_key
CORS_ALLOWED_ORIGINS=["https://your-domain.com","http://localhost:3000"]
ASSISTANT_ENABLED=true
ASSISTANT_GEMINI_ROUTING_ENABLED=true
```

### Step 3: Launch Containers
Run the pre-configured `docker-compose.yml`:
```bash
docker compose up -d --build
```
This builds and starts:
1. `orca-backend` on `http://localhost:8000`
2. `orca-frontend` on `http://localhost:3000`
3. `orca-redis` for cache acceleration

Check running containers:
```bash
docker compose ps
docker compose logs -f
```

### Step 4: Automatic HTTPS with Caddy (Recommended)
Install Caddy to handle automatic SSL certificates from Let's Encrypt:
```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
```

Create `/etc/caddy/Caddyfile`:
```caddy
# Frontend
your-domain.com {
    reverse_proxy localhost:3000
}

# Backend API
api.your-domain.com {
    reverse_proxy localhost:8000
}
```

Restart Caddy:
```bash
sudo systemctl restart caddy
```
Your application will now be live with secure HTTPS at `https://your-domain.com` and `https://api.your-domain.com`!

---

## 5. Complete Environment Variables Reference

### Backend Environment Variables (`.env`)

| Variable | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `APP_NAME` | string | `ORCA Base API` | Application identifier. |
| `APP_ENV` | string | `production` | Environment mode (`development`, `production`). |
| `API_PREFIX` | string | `/v1` | Public API routing prefix. |
| `CORS_ALLOWED_ORIGINS` | list / string | `["http://localhost:3000"]` | Allowed frontend domains (JSON array or comma-separated string). Wildcards `*` are rejected for security. |
| `ASSISTANT_ENABLED` | boolean | `true` | Enables the conversational assistant endpoint. |
| `ASSISTANT_GEMINI_ROUTING_ENABLED`| boolean | `true` | Enables Google Gemini intent classification and synthesis. |
| `ASSISTANT_MODEL` | string | `gemini-3.7-flash` | Gemini model name (`gemini-2.5-flash`, `gemini-3.7-flash`). |
| `GOOGLE_API_KEY` | secret | `None` | Google AI Studio Gemini API Key. |
| `REDIS_ENABLED` | boolean | `false` | Enables Redis caching. Set `true` if Redis container is active. |
| `REDIS_URL` | string | `redis://localhost:6379/0` | Connection string for Redis. |
| `INCOIS_BASE_URL` | string | `https://incois.gov.in/MarineFisheries` | Official INCOIS portal URL. |
| `PFZ_FETCH_CONCURRENCY` | int | `4` | Concurrency limit for scraping INCOIS coastal sectors. |
| `PFZ_CACHE_TTL_SECONDS` | int | `1800` | Fresh cache lifespan for PFZ bulletins (30 mins). |

---

### Frontend Environment Variables (`frontend_candidate/.env.local`)

| Variable | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `NEXT_PUBLIC_ORCA_API_BASE_URL` | url | `http://localhost:8000` | Absolute URL of the deployed ORCA backend API. |
| `NEXT_PUBLIC_MAP_STYLE_URL` | url | `https://tiles.openfreemap.org/styles/liberty` | Vector map tile endpoint for MapLibre GL. |
| `NEXT_PUBLIC_ORCA_ASSISTANT_MODE` | enum | `live` | Assistant mode (`live`, `demo`, `disabled`). |
| `NEXT_PUBLIC_ORCA_DEMO_MODE` | boolean | `false` | Set `false` for live marine data. |
| `NEXT_PUBLIC_ORCA_PRESENTATION_MODE`| boolean | `false` | Disables demo banners and mock overlays. |
| `NEXT_PUBLIC_ORCA_REQUEST_TIMEOUT_MS`| int | `90000` | Client HTTP request timeout in milliseconds. |

---

## 6. Post-Deployment Verification Checklist

Verify each of these to confirm full operational health:

1. **Backend Health Check**:
   ```bash
   curl -I https://api.your-domain.com/health
   # HTTP/1.1 200 OK
   ```
2. **Nearest PFZ Service**:
   ```bash
   curl "https://api.your-domain.com/v1/pfz/nearest?latitude=20.5&longitude=72.9"
   # Returns JSON containing nearest INCOIS PFZ coordinates and distance
   ```
3. **Conversational Assistant & Multilingual Routing**:
   ```bash
   curl -X POST https://api.your-domain.com/v1/assistant/query \
     -H "Content-Type: application/json" \
     -d '{"message":"Check marine conditions for fishing near Veraval","latitude":20.9,"longitude":70.36}'
   # Returns status "completed", marine evidence summary, and synthesized answer
   ```
4. **Interactive Map & Vector Tiles**:
   - Open `https://your-domain.com/map` in a browser.
   - Confirm the coastal map loads with active PFZ advisory points and landing centres.
5. **Language Switching**:
   - Switch language to **Hindi (हिन्दी)** or **Gujarati (ગુજરાતી)** in the top bar.
   - Ask a question; verify the response is rendered in the selected native language.

