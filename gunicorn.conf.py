import multiprocessing

# Bind address
bind = "0.0.0.0:8080"

# Use gevent async workers – required for long-lived SSE streaming connections.
worker_class = "gevent"

# Number of workers
workers = multiprocessing.cpu_count() * 2 + 1

# Increase timeout to 300s (5 min) for the multi-round orchestration endpoint.
# The /api/orchestrate SSE stream can take 60-120s across multiple agent rounds.
timeout = 300

# Keep-alive (seconds) – useful for SSE connections
keepalive = 5

# Graceful timeout for worker shutdown
graceful_timeout = 120
