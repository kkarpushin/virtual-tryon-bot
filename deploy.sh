#!/bin/bash
# Deploy script for Virtual Try-On Bot

set -e

echo "🚀 Deploying Virtual Try-On Bot..."

# Update system
sudo apt update

# Install Python 3.11 if not present
if ! command -v python3.11 &> /dev/null; then
    echo "📦 Installing Python 3.11..."
    sudo apt install -y software-properties-common
    sudo add-apt-repository -y ppa:deadsnakes/ppa
    sudo apt update
    sudo apt install -y python3.11 python3.11-venv python3.11-dev
fi

# Create virtual environment
echo "🐍 Creating virtual environment..."
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
echo "📦 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create data directory
mkdir -p data

# Check .env file
if [ ! -f .env ]; then
    echo "⚠️  .env file not found! Copy from .env.example and fill in values:"
    echo "   cp .env.example .env"
    echo "   nano .env"
    exit 1
fi

# Setup systemd service
echo "⚙️ Setting up systemd service..."
sudo cp deploy/bot.service /etc/systemd/system/tryon-bot.service
sudo systemctl daemon-reload
sudo systemctl enable tryon-bot
sudo systemctl restart tryon-bot

echo "✅ Deployment complete!"
echo ""
echo "📊 Check status: sudo systemctl status tryon-bot"
echo "📜 View logs: sudo journalctl -u tryon-bot -f"
