FROM python:3.11-slim

# Arbeitsverzeichnis
WORKDIR /app

# System Dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Python Dependencies kopieren und installieren
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App Code kopieren
COPY Skuld/ ./Skuld/

# Streamlit Config Directory erstellen (secrets.toml optional)
RUN mkdir -p ./Skuld/.streamlit /root/.streamlit
RUN echo "[server]" > /root/.streamlit/config.toml && \
    echo "headless = true" >> /root/.streamlit/config.toml && \
    echo "enableCORS = false" >> /root/.streamlit/config.toml && \
    echo "port = 8501" >> /root/.streamlit/config.toml && \
    echo "address = \"0.0.0.0\"" >> /root/.streamlit/config.toml

# Port für Streamlit
EXPOSE 8501

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Start Command
CMD ["python", "-m", "streamlit", "run", "Skuld/app.py"]
