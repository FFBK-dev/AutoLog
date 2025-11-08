#!/bin/bash
# Start Footage AI Processing RQ Workers
# Usage: ./start_ftg_ai_workers.sh [start|stop|status|restart]

PROJECT_ROOT="/Users/admin/Documents/Github/Filemaker-Backend"
cd "$PROJECT_ROOT"

# Add Python user scripts to PATH
export PATH="$HOME/Library/Python/3.9/bin:$PATH"

# Fix macOS fork() issue with Objective-C runtime
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES

# Color output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

start_workers() {
    echo -e "${BLUE}🚀 Starting Footage AutoLog Part B (AI) RQ Workers...${NC}"
    
    # Step 1: Assess & Sample (6 workers - CPU-intensive, scene detection)
    echo -e "${GREEN}Starting Step 1 workers (Assess & Sample)...${NC}"
    for i in {1..6}; do
        nohup rq worker ftg_ai_step1 --path "$PROJECT_ROOT" > /tmp/ftg_autolog_B_worker_step1_$i.log 2>&1 &
    done
    
    # Step 2: Gemini Analysis (2 workers - rate limited, expensive)
    echo -e "${GREEN}Starting Step 2 workers (Gemini)...${NC}"
    for i in {1..2}; do
        nohup rq worker ftg_ai_step2 --path "$PROJECT_ROOT" > /tmp/ftg_autolog_B_worker_step2_$i.log 2>&1 &
    done
    
    # Step 3: Create Frames (2 workers - fast, FileMaker writes)
    echo -e "${GREEN}Starting Step 3 workers (Create Frames)...${NC}"
    for i in {1..2}; do
        nohup rq worker ftg_ai_step3 --path "$PROJECT_ROOT" > /tmp/ftg_autolog_B_worker_step3_$i.log 2>&1 &
    done
    
    # Step 4: Audio Transcription (1 worker - occasional, can be slow)
    echo -e "${GREEN}Starting Step 4 workers (Audio Transcription)...${NC}"
    for i in {1..1}; do
        nohup rq worker ftg_ai_step4 --path "$PROJECT_ROOT" > /tmp/ftg_autolog_B_worker_step4_$i.log 2>&1 &
    done
    
    sleep 2
    echo -e "${BLUE}✅ Workers started! Total: 11 workers${NC}"
    echo ""
    status_workers
}

stop_workers() {
    echo -e "${RED}🛑 Stopping all Footage AutoLog Part B (AI) RQ Workers...${NC}"
    pkill -f "rq worker ftg_ai_step"
    sleep 1
    echo -e "${GREEN}✅ All workers stopped${NC}"
}

status_workers() {
    echo -e "${BLUE}📊 Worker Status:${NC}"
    
    for step in {1..4}; do
        count=$(pgrep -f "rq worker ftg_ai_step$step" | wc -l | xargs)
        if [ "$count" -gt 0 ]; then
            echo -e "  ${GREEN}✓${NC} Step $step: $count workers running"
        else:
            echo -e "  ${RED}✗${NC} Step $step: No workers"
        fi
    done
    
    echo ""
    total=$(pgrep -f "rq worker ftg_ai_step" | wc -l | xargs)
    echo -e "${BLUE}Total workers: $total${NC}"
    
    # Show queue sizes
    echo ""
    echo -e "${BLUE}📥 Queue Status:${NC}"
    python3 << 'EOF'
import sys
sys.path.append('/Users/admin/Documents/Github/Filemaker-Backend')
from jobs.ftg_autolog_B_queue_jobs import q_step1, q_step2, q_step3, q_step4

print(f"  Step 1 (Assess):        {len(q_step1)} queued")
print(f"  Step 2 (Gemini):        {len(q_step2)} queued")
print(f"  Step 3 (Create Frames): {len(q_step3)} queued")
print(f"  Step 4 (Transcription): {len(q_step4)} queued")
EOF
}

case "$1" in
    start)
        start_workers
        ;;
    stop)
        stop_workers
        ;;
    status)
        status_workers
        ;;
    restart)
        stop_workers
        sleep 2
        start_workers
        ;;
    *)
        echo "Usage: $0 {start|stop|status|restart}"
        exit 1
        ;;
esac

