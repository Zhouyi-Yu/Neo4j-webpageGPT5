#!/bin/bash

# Neo4j Researcher Search - Service Orchestrator
# This script starts both the FastAPI backend and the Vite frontend.

# Kill any existing processes on these ports
echo "🛑 Cleaning up existing processes..."
lsof -i :5001 -t | xargs kill -9 2>/dev/null
lsof -i :5173 -t | xargs kill -9 2>/dev/null

echo "🚀 Starting Services..."

# Start Backend (FastAPI)
echo "🐍 Starting Backend on port 5001..."
python3 main.py &
BACKEND_PID=$!

# Wait for backend to be ready
echo "⏳ Waiting for backend to initialize..."
sleep 3

# Start Frontend (Vite)
echo "⚛️ Starting Frontend on port 5173..."
cd frontend
npm run dev &
FRONTEND_PID=$!

function cleanup {
  echo "🧹 Shutting down services..."
  kill $BACKEND_PID
  kill $FRONTEND_PID
  exit
}

trap cleanup SIGINT SIGTERM

echo "✅ All services running!"
echo "🌐 Frontend: http://localhost:5173"

wait
