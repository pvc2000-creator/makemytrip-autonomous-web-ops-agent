# Frontend on Vercel / Netlify (optional)

The console is a single static file (`frontend/index.html`) and is also served by the API at `/`.
Deploy it separately only if you want the UI on a CDN:

1. Create a Vercel (or Netlify) project with `frontend/` as the root and no build command.
2. Add a rewrite so `/api/*` and `/mock/*` proxy to the backend, e.g. `vercel.json`:

```json
{ "rewrites": [
  { "source": "/api/:path*",  "destination": "https://YOUR-BACKEND.onrender.com/api/:path*" },
  { "source": "/mock/:path*", "destination": "https://YOUR-BACKEND.onrender.com/mock/:path*" } ] }
```

3. Set `CORS_ORIGINS` on the backend to the Vercel domain.

When the UI cannot reach `/api/health` it switches to demo mode and runs the same pipeline in the
browser, so a static deployment without a backend still gives reviewers a working walkthrough.
Browser workers must never run on Vercel/Netlify serverless functions (no Chromium runtime).
