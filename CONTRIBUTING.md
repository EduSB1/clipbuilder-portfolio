# Contributing to ClipBuilder

## Running it locally

```bash
cp .env.example .env    # fill in DB_PASSWORD, SECRET_KEY and ADMIN_PASSWORD
chmod 600 .env
docker compose up -d --build
```

The frontend serves on `http://localhost` and the API on `http://localhost/api/`.

### Certificates (production)

`cloudflare.ini` is **not versioned**. Create it from the template before
bringing certbot up:

```bash
cp cloudflare.ini.example cloudflare.ini
chmod 600 cloudflare.ini
```

## Development

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

ruff check .          # lint
ruff check . --fix    # autofix what can be fixed
ruff format .         # formatting
pytest                # tests
```

### Frontend

```bash
cd frontend
npm ci

npm run dev           # dev server (port 5173)
npm run lint          # eslint
npm run format        # prettier
npm run build         # production build
```

## Before opening a PR

CI runs `ruff check`, `pytest`, `eslint`, `npm run build` and builds both Docker
images. Running those locally first saves a round trip.

## Rules worth knowing

### Nothing blocking inside an `async` handler

The API runs with **a single uvicorn worker**. Calling LibreOffice, ffmpeg,
python-docx or a synchronous Gemini request straight from an `async def` freezes
the entire server for as long as the operation takes.

Use the helpers in `main.py`:

```python
# General heavy work (synchronous network calls, ffmpeg)
result = await _run_blocking(heavy_function, arg1, kwarg=value)

# DOCX/PDF generation — same idea, but with a concurrency cap
# (CLIPBUILDER_EXPORT_CONCURRENCY, default 2) so the VPS does not run out of RAM
pdf = await _run_export(markdown_to_pdf_via_libreoffice, markdown, title=title)
```

`tests/test_no_blocking_call_in_async.py` fails the PR if one of those calls
finds its way back onto the event loop.

### New routes go in `main.py` or in a router under `app/`

There is no second entrypoint any more: Docker runs `main:app`, and that is it.

### New pages must be lazy-loaded

Routes in `App.jsx` use `React.lazy`. Importing a page directly drops its code
into everyone's initial bundle.

### Secrets

No file carrying a credential goes into the repository. If you need a new
variable, add it to `.env.example` with an empty value and document what it is
for.
