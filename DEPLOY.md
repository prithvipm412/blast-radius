# Deploying Blast Radius

Backend → Render (free web service). Frontend → Vercel. Database → FalkorDB Cloud (already running; nothing to set up there, just copy its credentials in).

You'll deploy in this order: **backend first** (so you get its URL), **then frontend** (which needs that URL), **then go back to Render once** to tell it the frontend's URL for CORS. Three short stops.

Never commit `.env` or `web/.env.local` — both are gitignored. Every secret below gets typed into Render's or Vercel's dashboard, not into a file in the repo.

---

## 1. Backend on Render

1. Go to [dashboard.render.com](https://dashboard.render.com) and sign in (or create an account) with GitHub.
2. Click **New +** → **Blueprint**.
3. Pick the `blast-radius` repo (the one you just pushed). Render detects `render.yaml` at the repo root automatically and shows a preview of one service: `blast-radius-api`.
4. Click **Apply**. Render creates the service but won't start a working build yet — it's waiting on the env vars marked `sync: false` in `render.yaml`. Go to the new service's **Environment** tab and fill these in:

   | Key | Value |
   |---|---|
   | `FALKORDB_HOST` | from your FalkorDB Cloud instance |
   | `FALKORDB_PORT` | from your FalkorDB Cloud instance |
   | `FALKORDB_USERNAME` | from your FalkorDB Cloud instance |
   | `FALKORDB_PASSWORD` | from your FalkorDB Cloud instance |
   | `GEMINI_API_KEY` | your Gemini API key |
   | `GROQ_API_KEY` | optional — only needed if you want the Gemini→Groq fallback on repeated 429s |
   | `GITHUB_TOKEN` | a GitHub personal access token (public repo read is enough) |
   | `GITHUB_ISSUE_REPO` | optional — only needed if you ever call `create_incident_issue` with `dry_run:false`. A *different* repo than `GITHUB_REPO`, never the upstream `GoogleCloudPlatform/microservices-demo` |
   | `CORS_ORIGINS` | leave blank for now — you'll set this in step 3, after the frontend exists |

   (Find these the same place you got them for your local `.env` — this is copy-paste, not new credentials.)
5. Click **Save Changes**. Render builds and deploys. First build takes a few minutes (installs `requirements.txt` + `graph/requirements.txt`). Watch the **Logs** tab.
6. Once live, note the service URL at the top of the page — something like `https://blast-radius-api.onrender.com`. Sanity-check it:
   ```sh
   curl https://blast-radius-api.onrender.com/api/health
   # {"status":"ok"}
   curl https://blast-radius-api.onrender.com/api/stats
   # real graph stats, or an error if FalkorDB creds are wrong - check step 4 if so
   ```

**About the free tier**: Render spins the instance down after ~15 minutes of no traffic, and the next request takes 30–60s to wake it back up. The frontend already handles this — a request pending past 5 seconds shows "Waking up the graph…" instead of looking broken. You (or your demo audience) will just see that message on the first click after a quiet period.

---

## 2. Frontend on Vercel

1. Go to [vercel.com/new](https://vercel.com/new) and sign in with GitHub.
2. Import the same `blast-radius` repo.
3. On the configure screen:
   - **Root Directory**: click **Edit** and set it to `web` (the repo root is the Python backend — Vercel needs to build from the `web/` subfolder).
   - **Framework Preset**: Vercel should auto-detect **Next.js** once the root directory is set. Leave **Build Command** (`next build` / `npm run build`) and **Output Directory** on their defaults.
4. Open **Environment Variables** and add:

   | Key | Value | Environments |
   |---|---|---|
   | `NEXT_PUBLIC_API_URL` | your Render URL from step 1.6, e.g. `https://blast-radius-api.onrender.com` (no trailing slash) | Production (and Preview if you want previews hitting the live backend too) |
   | `NEXT_PUBLIC_MOCK` | `0` | Production |

   These are `NEXT_PUBLIC_*` vars, so they get baked into the JS bundle at build time — if you change either later, you must redeploy (not just restart) for it to take effect.
5. Click **Deploy**. Takes about a minute. Vercel gives you a URL like `https://blast-radius-xyz.vercel.app`.
6. Open it. You'll see the overview graph and stats load — then clicking "Simulate alert" will fail with a CORS error in the browser console, because Render doesn't know about this origin yet. That's expected — next step fixes it.

---

## 3. Close the loop: tell Render about the frontend

1. Back in the Render dashboard, open `blast-radius-api` → **Environment**.
2. Set `CORS_ORIGINS` to your Vercel URL from step 2.5, e.g. `https://blast-radius-xyz.vercel.app` (comma-separate multiple origins if you also want to allow a custom domain or `localhost:3001` for your own local testing against the deployed backend).
3. Save — Render redeploys automatically (just picking up the new env var, so it's quick).
4. Reload the Vercel site and try "Simulate alert on cartservice" again. Should stream normally now.

---

## Updating later

- **Backend change**: push to `main` → Render redeploys automatically (auto-deploy is on by default for Blueprint services).
- **Frontend change**: push to `main` → Vercel redeploys automatically.
- **Env var change on either**: changing a var and saving triggers a redeploy on both platforms; you don't need to manually trigger one.
- **Rotating a secret** (e.g. `GEMINI_API_KEY`): update it in Render's Environment tab only — it's never in the repo, so there's nothing else to touch.

## If something's wrong

- **`/api/health` times out or 502s**: check Render's **Logs** tab — usually a missing/wrong `FALKORDB_*` var (connection refused/DNS error) or a bad `GEMINI_API_KEY`.
- **Frontend loads but the graph/stats never appear**: open the browser console. A CORS error means step 3 above wasn't done (or `CORS_ORIGINS` has a typo — must match the Vercel URL's scheme+host exactly, no trailing slash, no path).
- **"Waking up the graph…" never resolves**: the backend is actually down, not just asleep — check Render's dashboard for a failed deploy or crashed instance, not just the logs of a sleeping one.
- **PageRank-sized nodes / "0 entities" on a fresh deploy**: `critical_services()` needs to run at least once to populate `Service.criticality` (it's not automatic on startup). From your own machine, with the deployed FalkorDB creds in your local `.env`: `python -c "from graph.tools import critical_services; critical_services()"`.
