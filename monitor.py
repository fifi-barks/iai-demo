#!/usr/bin/env python3
"""IAI Agent Monitor Dashboard — real-time visibility & controls."""

import subprocess
import os
import json
import requests
from datetime import datetime
from flask import Flask, render_template_string, jsonify
import threading
import time

app = Flask(__name__)

# Configuration
AGENT_LOG_PATH = "/tmp/iai-agent.log"
OLLAMA_URL = "http://localhost:11434"
SCREEN_SESSION = "iai-agent"

# State
state = {
    "agent_running": False,
    "agent_status": "unknown",
    "ollama_alive": False,
    "ollama_model": "phi",
    "last_logs": [],
    "last_card": None,
    "error_count": 0,
}

def check_agent_status():
    """Check if agent screen session is running."""
    try:
        result = subprocess.run(
            ["screen", "-ls"],
            capture_output=True,
            text=True,
        )
        return SCREEN_SESSION in result.stdout
    except:
        return False

def check_ollama_status():
    """Check if Ollama is responsive."""
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
        return response.status_code == 200
    except:
        return False

def get_recent_logs(lines=30):
    """Read recent agent logs."""
    try:
        if os.path.exists(AGENT_LOG_PATH):
            with open(AGENT_LOG_PATH) as f:
                all_lines = f.readlines()
                return all_lines[-lines:]
        return []
    except:
        return []

def monitor_loop():
    """Continuously update state."""
    while True:
        state["agent_running"] = check_agent_status()
        state["ollama_alive"] = check_ollama_status()
        state["last_logs"] = get_recent_logs(20)

        # Count errors in recent logs
        state["error_count"] = sum(1 for log in state["last_logs"] if "error" in log.lower())

        time.sleep(2)

@app.route("/")
def dashboard():
    """Main dashboard."""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>IAI Agent Monitor</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }
            .container {
                max-width: 1200px;
                margin: 0 auto;
            }
            h1 {
                color: white;
                margin-bottom: 30px;
                font-size: 2em;
            }
            .grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 20px;
                margin-bottom: 20px;
            }
            .card {
                background: white;
                border-radius: 12px;
                padding: 20px;
                box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
                transition: transform 0.2s;
            }
            .card:hover {
                transform: translateY(-5px);
            }
            .status-badge {
                display: inline-block;
                padding: 8px 16px;
                border-radius: 20px;
                font-weight: bold;
                margin: 10px 0;
                font-size: 0.9em;
            }
            .status-running {
                background: #10b981;
                color: white;
            }
            .status-stopped {
                background: #ef4444;
                color: white;
            }
            .status-unknown {
                background: #f59e0b;
                color: white;
            }
            .button-group {
                display: flex;
                gap: 10px;
                margin-top: 15px;
            }
            button {
                flex: 1;
                padding: 10px 15px;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                cursor: pointer;
                transition: all 0.2s;
                font-size: 0.9em;
            }
            .btn-primary {
                background: #667eea;
                color: white;
            }
            .btn-primary:hover {
                background: #5568d3;
            }
            .btn-danger {
                background: #ef4444;
                color: white;
            }
            .btn-danger:hover {
                background: #dc2626;
            }
            .btn-success {
                background: #10b981;
                color: white;
            }
            .logs {
                background: #1f2937;
                color: #10b981;
                padding: 15px;
                border-radius: 6px;
                font-family: "Monaco", "Courier New", monospace;
                font-size: 0.85em;
                max-height: 400px;
                overflow-y: auto;
                margin-top: 15px;
                line-height: 1.4;
            }
            .error-line {
                color: #ef4444;
            }
            .warning-line {
                color: #f59e0b;
            }
            .info-line {
                color: #3b82f6;
            }
            h2 {
                color: #1f2937;
                font-size: 1.2em;
                margin-bottom: 12px;
            }
            .metric {
                margin: 10px 0;
                padding: 8px;
                background: #f3f4f6;
                border-left: 4px solid #667eea;
                border-radius: 4px;
            }
            .metric-label {
                font-weight: bold;
                color: #374151;
            }
            .metric-value {
                color: #667eea;
                font-size: 1.1em;
            }
            .full-width {
                grid-column: 1 / -1;
            }
            .timestamp {
                color: #999;
                font-size: 0.8em;
                margin-top: 10px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🚀 IAI Agent Monitor</h1>

            <div class="grid">
                <!-- Agent Status -->
                <div class="card">
                    <h2>Agent Status</h2>
                    <div id="agent-status" class="status-badge status-unknown">Loading...</div>
                    <div class="metric">
                        <span class="metric-label">Session:</span>
                        <span class="metric-value" id="agent-session">-</span>
                    </div>
                    <div class="button-group">
                        <button class="btn-danger" onclick="restartAgent()">🔄 Restart Agent</button>
                        <button class="btn-primary" onclick="viewLogs()">📋 View Logs</button>
                    </div>
                </div>

                <!-- Ollama Status -->
                <div class="card">
                    <h2>Ollama Model</h2>
                    <div id="ollama-status" class="status-badge status-unknown">Loading...</div>
                    <div class="metric">
                        <span class="metric-label">Model:</span>
                        <span class="metric-value" id="ollama-model">phi</span>
                    </div>
                    <div class="button-group">
                        <button class="btn-danger" onclick="restartOllama()">🔄 Restart Ollama</button>
                        <button class="btn-primary" onclick="testOllama()">⚡ Test</button>
                    </div>
                </div>

                <!-- Logs -->
                <div class="card full-width">
                    <h2>Recent Logs</h2>
                    <div class="metric">
                        <span class="metric-label">Errors detected:</span>
                        <span class="metric-value" id="error-count">0</span>
                    </div>
                    <div class="logs" id="logs">
                        <div style="color: #999;">Waiting for logs...</div>
                    </div>
                    <div class="timestamp" id="timestamp">Updated: -</div>
                </div>
            </div>
        </div>

        <script>
            function updateStatus() {
                fetch('/api/status')
                    .then(r => r.json())
                    .then(data => {
                        // Agent status
                        const agentBadge = document.getElementById('agent-status');
                        if (data.agent_running) {
                            agentBadge.textContent = '✓ Running';
                            agentBadge.className = 'status-badge status-running';
                        } else {
                            agentBadge.textContent = '✗ Stopped';
                            agentBadge.className = 'status-badge status-stopped';
                        }
                        document.getElementById('agent-session').textContent = data.agent_running ? 'iai-agent (active)' : 'iai-agent (inactive)';

                        // Ollama status
                        const ollamaBadge = document.getElementById('ollama-status');
                        if (data.ollama_alive) {
                            ollamaBadge.textContent = '✓ Online';
                            ollamaBadge.className = 'status-badge status-running';
                        } else {
                            ollamaBadge.textContent = '✗ Offline';
                            ollamaBadge.className = 'status-badge status-stopped';
                        }

                        // Logs
                        const logsDiv = document.getElementById('logs');
                        if (data.last_logs.length > 0) {
                            logsDiv.innerHTML = data.last_logs
                                .map(line => {
                                    let cls = 'info-line';
                                    if (line.includes('ERROR') || line.includes('error')) cls = 'error-line';
                                    else if (line.includes('WARNING') || line.includes('warning')) cls = 'warning-line';
                                    return `<div class="${cls}">${escapeHtml(line.trim())}</div>`;
                                })
                                .join('');
                        }

                        // Error count
                        document.getElementById('error-count').textContent = data.error_count;
                        document.getElementById('timestamp').textContent = `Updated: ${new Date().toLocaleTimeString()}`;
                    })
                    .catch(e => console.error('Status fetch failed:', e));
            }

            function escapeHtml(text) {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }

            function restartAgent() {
                if (confirm('Restart the IAI agent? (takes ~5 seconds)')) {
                    fetch('/api/restart-agent', { method: 'POST' })
                        .then(r => r.json())
                        .then(data => {
                            alert(data.message);
                            updateStatus();
                        });
                }
            }

            function restartOllama() {
                if (confirm('Restart Ollama? (takes ~10 seconds)')) {
                    fetch('/api/restart-ollama', { method: 'POST' })
                        .then(r => r.json())
                        .then(data => {
                            alert(data.message);
                            updateStatus();
                        });
                }
            }

            function testOllama() {
                fetch('/api/test-ollama', { method: 'POST' })
                    .then(r => r.json())
                    .then(data => alert(data.message));
            }

            function viewLogs() {
                alert('Full logs available in /tmp/iai-agent.log on the server');
            }

            // Update every 2 seconds
            updateStatus();
            setInterval(updateStatus, 2000);
        </script>
    </body>
    </html>
    """
    return render_template_string(html)

@app.route("/api/status")
def api_status():
    """Return current status as JSON."""
    return jsonify({
        "agent_running": state["agent_running"],
        "ollama_alive": state["ollama_alive"],
        "ollama_model": state["ollama_model"],
        "error_count": state["error_count"],
        "last_logs": [log.strip() for log in state["last_logs"] if log.strip()],
    })

@app.route("/api/restart-agent", methods=["POST"])
def restart_agent():
    """Restart the agent."""
    try:
        subprocess.run(["screen", "-S", SCREEN_SESSION, "-X", "quit"], capture_output=True)
        time.sleep(1)
        subprocess.Popen([
            "bash", "-c",
            f"cd ~/iai-demo && screen -dm -S {SCREEN_SESSION} bash -c 'source venv/bin/activate && python3 -m bot.telegram_bot'"
        ])
        return jsonify({"message": "✓ Agent restarting..."})
    except Exception as e:
        return jsonify({"message": f"✗ Failed: {str(e)}"})

@app.route("/api/restart-ollama", methods=["POST"])
def restart_ollama():
    """Restart Ollama."""
    try:
        subprocess.run(["pkill", "ollama"], capture_output=True)
        time.sleep(2)
        subprocess.Popen(["bash", "-c", "ollama serve &"])
        return jsonify({"message": "✓ Ollama restarting..."})
    except Exception as e:
        return jsonify({"message": f"✗ Failed: {str(e)}"})

@app.route("/api/test-ollama", methods=["POST"])
def test_ollama():
    """Test Ollama connectivity."""
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        if response.status_code == 200:
            return jsonify({"message": "✓ Ollama is healthy"})
        return jsonify({"message": "✗ Ollama returned error"})
    except Exception as e:
        return jsonify({"message": f"✗ Ollama unreachable: {str(e)}"})

if __name__ == "__main__":
    # Start monitoring thread
    monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
    monitor_thread.start()

    print("🚀 IAI Monitor running on http://localhost:8000")
    app.run(host="0.0.0.0", port=8000, debug=False)
