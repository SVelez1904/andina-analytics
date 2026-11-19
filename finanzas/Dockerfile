FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Cloud Run entrega el puerto en $PORT (8080 por defecto).
# La misma imagen sirve para el informe mensual: el Job cambia el comando a `python informe/informe_mensual.py`.
CMD streamlit run app.py --server.port=${PORT:-8080} --server.address=0.0.0.0
