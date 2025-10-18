#!/bin/bash
# WebStatus Service Manager
# Usage: ./run.sh [start|stop|restart|status]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PID_FILE="$SCRIPT_DIR/.webstatus.pid"
PORT=8000

stop_service() {
    echo "Stopping WebStatus..."

    # Kill by PID file if exists
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            kill -9 "$PID" 2>/dev/null
            echo "  Killed process $PID"
        fi
        rm -f "$PID_FILE"
    fi

    # Kill any Python processes running main.py
    pkill -9 -f "python.*main.py" 2>/dev/null

    # Clear port 8000
    lsof -ti:$PORT | xargs kill -9 2>/dev/null

    echo "  Service stopped"
    sleep 1
}

start_service() {
    echo "Starting WebStatus..."

    # Activate virtual environment and start
    source venv/bin/activate
    nohup python main.py > logs/app.log 2>&1 &

    # Save PID
    echo $! > "$PID_FILE"

    echo "  Service started (PID: $(cat $PID_FILE))"
    echo "  Web Interface: http://localhost:$PORT"
    echo "  Logs: tail -f logs/app.log"
}

status_service() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "WebStatus is running (PID: $PID)"
            echo "Port usage:"
            lsof -i:$PORT
        else
            echo "WebStatus is not running (stale PID file)"
            rm -f "$PID_FILE"
        fi
    else
        # Check for any running processes
        PIDS=$(pgrep -f "python.*main.py")
        if [ -n "$PIDS" ]; then
            echo "Warning: Found running processes without PID file:"
            ps -p $PIDS -o pid,command
        else
            echo "WebStatus is not running"
        fi
    fi
}

case "$1" in
    start)
        stop_service
        start_service
        ;;
    stop)
        stop_service
        ;;
    restart)
        stop_service
        start_service
        ;;
    status)
        status_service
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        echo ""
        echo "Commands:"
        echo "  start   - Stop any running instances and start fresh"
        echo "  stop    - Stop all WebStatus processes"
        echo "  restart - Stop and start the service"
        echo "  status  - Check if service is running"
        exit 1
        ;;
esac
