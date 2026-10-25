# Personalized Travel Itinerary Planner

A React/Vite travel planner backed by FastAPI. Supabase provides authentication, per-user trip storage, and shared trip collaboration; Groq generates itinerary suggestions by default (Gemini is an optional alternative); Unsplash supplies destination photography. If the selected AI provider or Unsplash is not configured, demo itineraries and visual fallbacks remain available.

## Project layout

```text
frontend/              React + Vite browser application
backend/               FastAPI API and integrations
backend/schema.sql     Supabase trips table and row-level security policies
```

## Local setup

### 1. Create Supabase resources

1. Create a Supabase project and enable Email authentication in Authentication → Providers.
2. In SQL Editor, run [`backend/schema.sql`](backend/schema.sql). It creates or migrates the trips and collaborators tables, row-level security rules, owner-only invite-code management, per-user AI quotas, and Realtime publication membership. **Rerun this updated file after pulling schema changes** so the ownership guards and AI quota function are installed.
3. Copy the project URL and public anon/publishable key from Project Settings → API.

The app never uses a Supabase service-role key. Database calls use the signed-in user's access token and RLS.

### 2. Configure and start FastAPI

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `SUPABASE_URL` and `SUPABASE_ANON_KEY` in `backend/.env`. For AI itineraries, create a GroqCloud key, set `GROQ_API_KEY`, and leave `AI_PROVIDER=groq`; `GROQ_MODEL` defaults to `openai/gpt-oss-20b`. Gemini remains available by setting `AI_PROVIDER=gemini` and configuring `GEMINI_API_KEY` (optionally set `GEMINI_MODEL`). Add `UNSPLASH_ACCESS_KEY` for destination image search. AI and Unsplash are optional; the app remains usable with demo plans.

```powershell
uvicorn main:app --reload --port 8000
```

API docs: `http://localhost:8000/docs`.

### 3. Configure and start React/Vite

```powershell
cd frontend
Copy-Item .env.example .env
npm.cmd install
npm.cmd run dev
```

Set the Supabase URL and anon/publishable key in `frontend/.env`. Keep `VITE_API_URL=http://localhost:8000` locally. Open `http://localhost:5173`.

## Production deployment

- **Frontend:** deploy `frontend/` to Vercel (Root Directory `frontend`; Build Command `npm run build`; Output Directory `dist`). Add `VITE_API_URL`, `VITE_SUPABASE_URL`, and `VITE_SUPABASE_ANON_KEY` to Vercel environment variables.
- **Backend:** deploy `backend/` to Render as a Python web service (Root Directory `backend`; Build Command `pip install -r requirements.txt`; Start Command `uvicorn main:app --host 0.0.0.0 --port $PORT`). Set `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `FRONTEND_ORIGIN` (the production Vercel origin), `AI_PROVIDER`, the selected provider key/model (`GROQ_API_KEY`/`GROQ_MODEL` or `GEMINI_API_KEY`/`GEMINI_MODEL`), and optionally `UNSPLASH_ACCESS_KEY`.
- Set `VITE_API_URL` to the public Render service URL and redeploy the frontend.
- Configure the Vercel origin in Supabase Auth → URL Configuration, along with local development redirects if needed.

## Features

- Destination recommendations scored by travel vibe, budget, interests, and season heuristics.
- Day plans with neighborhood grouping, sequential time slots, estimated activity costs per traveler and group, and cumulative spend.
- Accommodation neighborhood/style suggestions and links to browse current listings.
- Arrival and local transportation guidance, inter-stop notes, neighborhood-clustered day routes, and links to open the ordered stops in Google Maps for live directions.
- Single-slot swaps and single-day regeneration that preserve the rest of the itinerary.
- Supabase email sign-in, per-user trip history, invite-code collaboration, realtime plan updates, and offline PDF export with stay/transport notes and an emergency checklist.
- Optional Unsplash photo search with photographer attribution in API results.

## Notes

- Seasonal matching, accommodation price ranges, and demo activity costs are planning aids, not live weather, hotel inventory, traffic, or quotations. Recommendations suggest neighborhoods and lodging styles rather than booking-verified properties. Confirm venue hours, routes, fares, prices, and emergency contacts before departure.
- Shared collaboration requires each traveler to create an account and join with the private invite link. Changes to a saved shared itinerary sync through Supabase Realtime; initial preference collection is entered by the trip creator and can be refined by collaborators.
- Route ordering is neighborhood-based itinerary planning. The Maps link opens the proposed stop sequence in Google Maps, which can calculate current turn-by-turn directions when opened; this app itself does not ingest live traffic or transit feeds.
- AI suggestions are not availability-checked. Gemini and Groq credentials stay on the backend. Supabase anon keys are designed to be public; data access is enforced with RLS.
- Before opening public account sign-ups at scale, configure Supabase email confirmation, rate limits, and abuse controls for your use case.
- AI planning, swapping, and day reimagination are limited to 10 requests per signed-in user per hour. Supabase Auth still needs its own sign-up and login rate limits configured for the deployment.
