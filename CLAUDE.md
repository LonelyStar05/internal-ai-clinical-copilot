# Clinical Copilot project

Read @README.md for the architecture, commands, demo accounts, and API inventory.
Read @AGENTS.md before changing frontend code.

## Working rules

- Work from the repository root. The Next.js 16 frontend is in `app/`, `components/`, and `lib/`; the FastAPI backend is in `backend/`.
- Before editing Next.js code, read the relevant local guide under `node_modules/next/dist/docs/`. This project uses a version with breaking changes.
- Keep browser API calls behind `/api/...`; `next.config.ts` proxies them to FastAPI through `API_URL` (default `http://localhost:8000`).
- When an API response changes, update both the Pydantic/backend response and the matching types in `lib/api.ts`.
- Treat every record in `backend/app/data/` as synthetic demo data. Do not add real patient information, credentials, tokens, or API keys.
- Preserve the verifier and citation rules: LLM output is untrusted until it passes deterministic checks.
- Run `npm run lint` and `npm run build` after frontend changes.
- Run `backend/.venv/Scripts/python.exe -m pytest -q` from `backend/` after backend changes.

## Local startup

- Double-click `start.bat`, or run `powershell -ExecutionPolicy Bypass -File scripts/start.ps1`.
- Frontend: `http://localhost:3000`
- FastAPI docs: `http://localhost:8000/docs`
- Demo login: `bs.an` / `demo`
