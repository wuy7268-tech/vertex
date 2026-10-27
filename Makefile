.PHONY: infra test api web

infra:
	docker compose up -d postgres redis

test:
	cd apps/api && .venv/bin/pytest -q

api:
	cd apps/api && .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000

web:
	cd apps/web && npm run dev
