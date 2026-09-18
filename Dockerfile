FROM python:3.12-slim

WORKDIR /app

# build-essential covers web3's C-extension deps (e.g. cytoolz) on platforms
# without a prebuilt wheel - cheap insurance, this isn't a size-sensitive image.
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501

# Railway injects $PORT at runtime; shell form so it actually expands.
CMD streamlit run app.py --server.port=${PORT:-8501} --server.address=0.0.0.0 --server.headless=true
