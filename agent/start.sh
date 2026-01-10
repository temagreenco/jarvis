#!/bin/bash
# JARVIS Agent - Quick Start Script
# ==================================
#
# USAGE:
#   ./start.sh          # Start interactive agent
#   ./start.sh build    # Rebuild and start
#   ./start.sh logs     # View logs
#   ./start.sh stop     # Stop everything
#   ./start.sh gpu      # Start with GPU support
#
# FIRST RUN:
# - Downloads Ollama image (~1GB)
# - Downloads LLM model (~2GB for llama3.2:3b)
# - Takes 5-10 minutes depending on internet
#
# SUBSEQUENT RUNS:
# - Starts in seconds (models cached)

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Create workspace if it doesn't exist
mkdir -p workspace

case "${1:-}" in
    "build")
        echo -e "${YELLOW}Rebuilding agent container...${NC}"
        docker compose build agent
        docker compose up
        ;;

    "logs")
        echo -e "${YELLOW}Showing agent logs (Ctrl+C to exit)...${NC}"
        docker compose logs -f agent
        ;;

    "stop")
        echo -e "${YELLOW}Stopping all containers...${NC}"
        docker compose down
        echo -e "${GREEN}Stopped!${NC}"
        ;;

    "gpu")
        echo -e "${YELLOW}Starting with GPU support...${NC}"
        echo "Make sure you have nvidia-docker installed!"
        # Enable GPU in compose
        COMPOSE_PROFILES=gpu docker compose up
        ;;

    "status")
        echo -e "${YELLOW}Container status:${NC}"
        docker compose ps
        ;;

    "shell")
        echo -e "${YELLOW}Opening shell in agent container...${NC}"
        docker compose exec agent /bin/bash
        ;;

    "ollama")
        echo -e "${YELLOW}Testing Ollama connection...${NC}"
        curl -s http://localhost:11434/api/tags | python3 -m json.tool
        ;;

    *)
        echo -e "${GREEN}"
        echo "╔═══════════════════════════════════════════╗"
        echo "║         JARVIS Agent - Docker             ║"
        echo "╚═══════════════════════════════════════════╝"
        echo -e "${NC}"

        echo -e "${YELLOW}Starting JARVIS Agent...${NC}"
        echo "First run will download models (may take several minutes)"
        echo ""

        # Start everything
        docker compose up
        ;;
esac
