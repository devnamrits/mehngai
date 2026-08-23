#!/bin/zsh
# Mehngai dev launcher — keeps API + UI alive, detached from this shell
cd "$(dirname "$0")"

pkill -9 -f "uvicorn app.main" 2>/dev/null
pkill -9 -f "next dev" 2>/dev/null
sleep 1

(cd backend && source .venv/bin/activate && nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/mehngai-api.log 2>&1 &)

(cd frontend && nohup npm run dev > /tmp/mehngai-ui.log 2>&1 &)

sleep 6
echo "API: $(curl -s -m 5 localhost:8000/api/v1/health)"
echo "UI : $(curl -s -m 5 -o /dev/null -w '%{http_code}' localhost:3000)"
