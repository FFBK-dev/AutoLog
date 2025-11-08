#!/bin/bash
# Start LF AutoLog RQ Workers
# Usage: ./start_lf_workers.sh [start|stop|status]

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
    echo -e "${BLUE}🚀 Starting LF AutoLog RQ Workers...${NC}"
    
    # Step 1: File Info (8 workers - fast, parallel imports)
    echo -e "${GREEN}Starting Step 1 workers (File Info)...${NC}"
    for i in {1..8}; do
        nohup rq worker lf_step1 --path "$PROJECT_ROOT" > /tmp/lf_worker_step1_$i.log 2>&1 &
    done
    
    # Step 2: Thumbnails (8 workers - fast, parallel)
    echo -e "${GREEN}Starting Step 2 workers (Thumbnails)...${NC}"
    for i in {1..8}; do
        nohup rq worker lf_step2 --path "$PROJECT_ROOT" > /tmp/lf_worker_step2_$i.log 2>&1 &
    done
    
    # Step 3: Assess & Sample (16 workers - increased for queue congestion)
    # Note: Frame sampling is optimized (scene detection skipped for <60s videos)
    echo -e "${GREEN}Starting Step 3 workers (Assess & Sample)...${NC}"
    for i in {1..16}; do
        nohup rq worker lf_step3 --path "$PROJECT_ROOT" > /tmp/lf_worker_step3_$i.log 2>&1 &
    done
    
    # Step 4: Gemini Analysis (2 workers - rate limited, expensive)
    echo -e "${GREEN}Starting Step 4 workers (Gemini)...${NC}"
    for i in {1..2}; do
        nohup rq worker lf_step4 --path "$PROJECT_ROOT" > /tmp/lf_worker_step4_$i.log 2>&1 &
    done
    
    # Step 5: Create Frames (4 workers - medium, FileMaker writes)
    echo -e "${GREEN}Starting Step 5 workers (Create Frames)...${NC}"
    for i in {1..4}; do
        nohup rq worker lf_step5 --path "$PROJECT_ROOT" > /tmp/lf_worker_step5_$i.log 2>&1 &
    done
    
    # Step 6: Audio Transcription (3 workers - occasional, can be slow)
    echo -e "${GREEN}Starting Step 6 workers (Audio Transcription)...${NC}"
    for i in {1..3}; do
        nohup rq worker lf_step6 --path "$PROJECT_ROOT" > /tmp/lf_worker_step6_$i.log 2>&1 &
    done
    
    sleep 2
    echo -e "${BLUE}✅ Workers started! Total: 41 workers${NC}"
    echo ""
    status_workers
}

stop_workers() {
    echo -e "${RED}🛑 Stopping all LF AutoLog RQ Workers...${NC}"
    pkill -f "rq worker lf_step"
    sleep 1
    echo -e "${GREEN}✅ All workers stopped${NC}"
}

status_workers() {
    echo -e "${BLUE}📊 Worker Status:${NC}"
    
    for step in {1..6}; do
        count=$(pgrep -f "rq worker lf_step$step" | wc -l | xargs)
        if [ "$count" -gt 0 ]; then
            echo -e "  ${GREEN}✓${NC} Step $step: $count workers running"
        else
            echo -e "  ${RED}✗${NC} Step $step: No workers"
        fi
    done
    
    echo ""
    total=$(pgrep -f "rq worker lf_step" | wc -l | xargs)
    echo -e "${BLUE}Total workers: $total${NC}"
    
    # Show queue sizes
    echo ""
    echo -e "${BLUE}📥 Queue Status:${NC}"
    python3 << 'EOF'
import sys
sys.path.append('/Users/admin/Documents/Github/Filemaker-Backend')
from jobs.lf_queue_jobs import q_step1, q_step2, q_step3, q_step4, q_step5, q_step6

print(f"  Step 1 (File Info):     {len(q_step1)} queued")
print(f"  Step 2 (Thumbnails):    {len(q_step2)} queued")
print(f"  Step 3 (Assess):        {len(q_step3)} queued")
print(f"  Step 4 (Gemini):        {len(q_step4)} queued")
print(f"  Step 5 (Create Frames): {len(q_step5)} queued")
print(f"  Step 6 (Transcription): {len(q_step6)} queued")
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

