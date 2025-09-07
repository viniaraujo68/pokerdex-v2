FROM python:3.11-slim

# Evita prompts e melhora logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Cria venv dentro do container
RUN python -m venv /venv
ENV PATH="/venv/bin:$PATH"

# Dependências do sistema (build e tz)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential tzdata curl ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

# Diretório de trabalho
WORKDIR /workspace

# Instala deps
COPY requirements.txt /workspace/requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copia código (em dev sobrescreveremos com volume)
COPY . /workspace

# Porta do runserver
EXPOSE 8000

# Comando padrão: Django dev server
CMD ["bash", "-lc", "python manage.py migrate && python manage.py runserver 0.0.0.0:8000"]
