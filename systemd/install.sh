#!/bin/bash
# Install script for broll-organizer systemd service

set -e

echo "Installing B-Roll Catalog systemd service..."

# Copy service file
sudo cp systemd/broll-catalog.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable broll-catalog

echo "Service installed. Starting now..."

# Start the service
sudo systemctl start broll-catalog

echo "✅ B-Roll Catalog service installed and started!"
echo ""
echo "Commands:"
echo "  sudo systemctl status broll-catalog  - Check status"
echo "  sudo systemctl stop broll-catalog    - Stop service"
echo "  sudo systemctl start broll-catalog   - Start service"
echo "  sudo systemctl restart broll-catalog - Restart service"
echo ""
echo "Web UI will be available at:"
echo "  http://openclaw-pi.tail5c860f.ts.net:5555 (Tailscale)"
echo "  http://192.168.1.35:5555 (Local network)"
