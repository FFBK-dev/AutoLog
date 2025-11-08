#!/bin/bash
# Test script to verify worker auto-start

echo "========================================"
echo "Testing Footage AutoLog Worker Auto-Start"
echo "========================================"
echo ""

# Check if workers are running
echo "1️⃣ Checking current worker status..."
./workers/start_ftg_autolog_B_workers.sh status
echo ""

# Stop any running workers
echo "2️⃣ Stopping any running workers..."
./workers/start_ftg_autolog_B_workers.sh stop
sleep 2
echo ""

# Verify workers are stopped
echo "3️⃣ Verifying workers are stopped..."
./workers/start_ftg_autolog_B_workers.sh status
echo ""

echo "========================================"
echo "✅ Ready to test!"
echo "========================================"
echo ""
echo "Now restart your API server:"
echo ""
echo "  1. Stop current API (Ctrl+C in its terminal)"
echo "  2. Clear cache: rm -rf __pycache__ jobs/__pycache__ utils/__pycache__"
echo "  3. Start API: python3 -m uvicorn API:app --host 0.0.0.0 --port 8081 --reload"
echo ""
echo "You should see in the logs:"
echo "  🤖 Starting Footage AutoLog Part B workers..."
echo "  ✅ Footage AutoLog Part B workers started (20 workers)"
echo ""
echo "Then verify with:"
echo "  ./workers/start_ftg_autolog_B_workers.sh status"
echo ""


