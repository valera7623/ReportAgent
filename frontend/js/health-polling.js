let healthTimer = null;

export function stopHealthPolling() {
  if (healthTimer) {
    clearInterval(healthTimer);
    healthTimer = null;
  }
}

export function startHealthPolling(fn, intervalMs = 30000) {
  stopHealthPolling();
  healthTimer = setInterval(fn, intervalMs);
}
