#!/bin/bash
# ============================================
# Run JARVIS with Cloud LLM (no Ollama needed)
# ============================================
#
# SUPPORTED PROVIDERS:
# 1. Together.ai - Free tier, many models
#    Get API key: https://api.together.xyz/
#
# 2. Groq - Very fast, free tier
#    Get API key: https://console.groq.com/
#
# 3. OpenAI - Paid only
#    Get API key: https://platform.openai.com/

cd "$(dirname "$0")"
source .venv/bin/activate

echo "╔═══════════════════════════════════════════════════════════╗"
echo "║         JARVIS Agent - Cloud LLM Mode                     ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""

# Check if API key is set
if [ -z "$LLM_API_KEY" ]; then
    echo "No API key found. Choose a provider:"
    echo ""
    echo "1. Together.ai (free tier, recommended)"
    echo "   export LLM_API_KEY='your-together-api-key'"
    echo "   export LLM_PROVIDER='together'"
    echo ""
    echo "2. Groq (very fast, free tier)"
    echo "   export LLM_API_KEY='your-groq-api-key'"
    echo "   export LLM_PROVIDER='groq'"
    echo ""
    echo "Then run this script again."
    exit 1
fi

# Set provider-specific settings
case "${LLM_PROVIDER:-together}" in
    "together")
        export AGENT_LLM_PROVIDER=openai
        export AGENT_LLM_BASE_URL=https://api.together.xyz/v1
        export AGENT_LLM_MODEL=meta-llama/Llama-3.2-3B-Instruct-Turbo
        export AGENT_LLM_API_KEY="$LLM_API_KEY"
        echo "Using Together.ai with Llama 3.2 3B"
        ;;
    "groq")
        export AGENT_LLM_PROVIDER=openai
        export AGENT_LLM_BASE_URL=https://api.groq.com/openai/v1
        export AGENT_LLM_MODEL=llama-3.1-8b-instant
        export AGENT_LLM_API_KEY="$LLM_API_KEY"
        echo "Using Groq with Llama 3.1 8B"
        ;;
    "openai")
        export AGENT_LLM_PROVIDER=openai
        export AGENT_LLM_BASE_URL=https://api.openai.com/v1
        export AGENT_LLM_MODEL=gpt-4o-mini
        export AGENT_LLM_API_KEY="$LLM_API_KEY"
        echo "Using OpenAI with GPT-4o-mini"
        ;;
esac

echo ""
python main.py
