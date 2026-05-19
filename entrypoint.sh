#!/bin/bash

echo "🚀 Iniciando contenedor unificado (Piston + FastAPI)..."

echo "⚡ Arrancando Piston API Server..."
/piston/packages/api/bin/api &

sleep 3

echo "🛠️ Instalando lenguajes en Piston (Python y Java)..."
piston cli install python java

echo "✅ Compiladores instalados con éxito en Piston."

echo "🌐 Iniciando FastAPI con Uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port 7860
