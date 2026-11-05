FROM python:3.12-slim

WORKDIR /app

# build-essential: prophet instala cmdstanpy, que compila cmdstan (C++) durante
# el pip install del paso siguiente. Sin un compilador en la imagen, esa
# instalacion falla. Se limpia el apt cache despues para no inflar la imagen.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# TensorFlow (LSTM del pronostico) escribe por defecto avisos informativos de
# oneDNN/absl en cada importacion; se dejan solo los errores.
ENV TF_CPP_MIN_LOG_LEVEL=2

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
