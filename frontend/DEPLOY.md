# Frontend Deployment (Vercel)

## Steps

1. Import the GitHub repository into [Vercel](https://vercel.com).
2. Set the **Root Directory** to `frontend/`.
3. Vercel reads `vercel.json` for build settings:
   - Build command: `npm run build`
   - Output directory: `dist`
   - SPA rewrites to `index.html`
4. Add environment variable:
   - `VITE_API_BASE_URL` = your backend URL (e.g. `https://api.example.com`)
5. Deploy.

## Local Development

```bash
cd frontend
npm install
npm run dev
```

Create `frontend/.env.local`:

```
VITE_API_BASE_URL=http://localhost:8000
```

## Tests

```bash
npm test
```
