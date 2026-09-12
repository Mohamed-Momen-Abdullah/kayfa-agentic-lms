# Kayfa · كيف

An agentic learning platform: students get an **Academic Help Agent** for
explanations and a **Quiz Agent** that generates practice quizzes straight
from a course's material — by typing or by voice, in Arabic or English.
Instructors see their courses and roster grades; admins see live activity
across both agents.

Everything is backed by MongoDB. There is no mock/demo data baked into the
UI — if a collection is empty, the dashboard says so.

## What's here

```
app/
  core/       settings + auth (JWT, bcrypt)
  db/         MongoDB access layer + seed script
  agents/     academic_agent, quiz_agent, and the supervisor that routes
              a chat message to one or the other
  services/   sentiment analysis, activity tracing
  api/        the FastAPI app (all HTTP endpoints)
frontend/
  templates/portal.html   single-page shell (login + dashboard)
  static/css/style.css    Kayfa brand theme, light + dark
  static/js/app.js        all client logic: auth, chat, voice, quizzes, admin
  static/images/          your Kayfa logo/wordmark files
```

## Setup

1. **Install dependencies**
   ```
   pip install -r requirements.txt
   ```

2. **Configure environment** — copy `.env.example` to `.env` and fill in:
   - `MONGO_URI` / `DATABASE_NAME` — your MongoDB connection
   - `JWT_SECRET` — any long random string
   - `ADMIN_USERNAME` / `ADMIN_PASSWORD` — the Admin login (there's no Admin
     document in Mongo; these are checked directly against the login form)
   - `GROQ_API_KEY` — get one at console.groq.com. Both agents work without
     it, but respond with a clearly-labeled placeholder instead of a real
     generated answer.

3. **Seed demo data** (creates 2 instructors, 3 students, 3 courses with
   real material used for quiz generation):
   ```
   python -m app.db.seed
   ```

4. **Run it**
   ```
   uvicorn app.api.main:app --reload
   ```
   Open http://localhost:8000

   Or with Docker:
   ```
   docker compose up --build
   ```
   (then run the seed command in a separate `docker compose exec app python -m app.db.seed`)

## Demo logins (after seeding)

| Role       | Username      | Password  |
|------------|---------------|-----------|
| Student    | layla.hassan  | study123  |
| Student    | youssef.ali   | study123  |
| Instructor | sarah.ahmed   | teach123  |
| Admin      | *(your `ADMIN_USERNAME`/`ADMIN_PASSWORD`)* |

## Notes on the voice feature

Speech-to-text and text-to-speech run entirely in the browser via the Web
Speech API (`SpeechRecognition` / `speechSynthesis`) — there's no audio sent
to the server and no extra API key needed. It auto-detects Arabic vs.
English for playback. It's best supported in Chrome/Edge; the mic button
simply stays hidden in browsers without `SpeechRecognition` support.

## What changed from the previous version of this repo

This codebase previously had auth code that imported functions which didn't
exist, a frontend calling API routes the backend never defined, an unused
~1GB speech-recognition model and an unused RAG pipeline that both crashed
on import, a `Dockerfile`/`docker-compose.yml` that were empty files, a
`requirements.txt` missing half of what the code actually imports, and an
admin panel with a "cost analytics" tab built on fabricated random numbers.
All of that has been rebuilt, connected end-to-end to MongoDB, and rebranded
to match the actual Kayfa logo assets.
