#!/bin/bash
# Run Radio Free Luna with Docker - the easiest way!

echo "🎵 Radio Free Luna - Docker Runner"
echo "=================================="
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "Creating .env from template..."
    cp .env.example .env
    echo "⚠️  Please edit .env and add your OPENAI_API_KEY"
    echo ""
fi

# Check if docker-compose exists
if ! command -v docker-compose &> /dev/null; then
    echo "Using docker compose (v2)..."
    DOCKER_COMPOSE="docker compose"
else
    DOCKER_COMPOSE="docker-compose"
fi

echo "Starting Radio Free Luna with Docker..."
echo ""
echo "This will:"
echo "1. Build the Docker image (first time only)"
echo "2. Start Radio Free Luna on http://localhost:8080"
echo "3. Start TTS-WebUI on http://localhost:7860"
echo ""

# Run docker-compose
$DOCKER_COMPOSE up -d

echo ""
echo "✅ Radio Free Luna is starting!"
echo ""
echo "📡 Main interface: http://localhost:8080"
echo "🎤 TTS interface: http://localhost:7860"
echo ""
echo "To view logs: $DOCKER_COMPOSE logs -f"
echo "To stop: $DOCKER_COMPOSE down"