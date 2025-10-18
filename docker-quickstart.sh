#!/bin/bash
# WebStatus - Docker Quick Start Script

set -e

echo "🐳 WebStatus - Docker Quick Start"
echo "========================================"
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first:"
    echo "   https://docs.docker.com/get-docker/"
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first:"
    echo "   https://docs.docker.com/compose/install/"
    exit 1
fi

echo "✅ Docker and Docker Compose are installed"
echo ""

# Stop any existing native processes
echo "🛑 Stopping any existing native processes..."
killall -9 python python3 2>/dev/null || true
sleep 1

# Build and start the container
echo "🔨 Building Docker image..."
docker-compose build

echo ""
echo "🚀 Starting WebStatus container..."
docker-compose up -d

echo ""
echo "⏳ Waiting for container to be healthy..."
sleep 5

# Check container status
if docker-compose ps | grep -q "Up"; then
    echo ""
    echo "✅ WebStatus is running!"
    echo ""
    echo "📊 Access the web interface:"
    echo "   http://localhost:8000"
    echo ""
    echo "📝 View logs:"
    echo "   docker-compose logs -f"
    echo ""
    echo "🛑 Stop the container:"
    echo "   docker-compose down"
    echo ""
    echo "🔄 Restart the container:"
    echo "   docker-compose restart"
    echo ""
    echo "📖 Full documentation:"
    echo "   See DOCKER.md"
    echo ""
else
    echo ""
    echo "❌ Failed to start container. Check logs:"
    echo "   docker-compose logs"
    exit 1
fi
