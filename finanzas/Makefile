# Atajos para trabajar en tu computador (Fedora): make test, make lint, make app
.PHONY: instalar test lint app importar datos-claude sugerencias

instalar:
	python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt

test:
	GCP_PROYECTO=test .venv/bin/pytest --cov

lint:
	.venv/bin/ruff check . && .venv/bin/ruff format --check . || true

app:
	.venv/bin/streamlit run app.py

# Carga masiva de la carpeta de operaciones: make importar CARPETA="~/Descargas/3. OPERATIONS"
importar:
	.venv/bin/python scripts/importar_operaciones.py "$(CARPETA)" --usuario "$${DEV_USER:-carga-masiva}"

# Para la tarea agendada de Claude (sin API key): exporta los datos del mes a salidas/
# make datos-claude            → mes anterior     make datos-claude MES=2026-10
datos-claude:
	.venv/bin/python scripts/datos_para_claude.py $(MES)

# Guarda las sugerencias de Claude como precarga en Pendientes (no confirma nada)
sugerencias:
	.venv/bin/python scripts/guardar_sugerencias.py "$(ARCHIVO)"
