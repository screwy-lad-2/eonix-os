# Hub API Reference

## Base URL
  http://localhost:7750

## GET /hub/status
Returns full system status.

Response:
{
  "agents": [
    {"name": "GoalEngine", "port": 7735, "healthy": true},
    {"name": "ContextAgent", "port": 7736, "healthy": true},
    {"name": "ResourceAgent", "port": 7737, "healthy": true},
    {"name": "SyncDaemon", "port": 7740, "healthy": true}
  ],
  "all_agents_healthy": true,
  "model_version": "v1.2",
  "model_ready": true,
  "next_retrain_eta": null
}

## GET /hub/health
  {"status": "ok"}

## WebSocket ws://localhost:7750/ws
Live agent health updates streamed as JSON.
