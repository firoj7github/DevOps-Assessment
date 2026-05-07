/**
 * api.js — centralised API client
 *
 * Base URL is injected at build time via REACT_APP_API_URL
 * (set in .env or passed as a Docker build-arg / K8s ConfigMap).
 * Falls back to the same origin so relative calls work in production.
 */

const BASE_URL = process.env.REACT_APP_API_URL || '';

async function request(path, options = {}) {
  const url = `${BASE_URL}${path}`;
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }

  if (res.status === 204) return null;
  return res.json();
}

// ── Health ────────────────────────────────────────
export const fetchHealth      = ()          => request('/health');
export const fetchReadiness   = ()          => request('/health/ready');

// ── Tasks ─────────────────────────────────────────
export const fetchTasks       = ()          => request('/api/v1/tasks');
export const createTask       = (title)     => request('/api/v1/tasks', {
  method: 'POST',
  body: JSON.stringify({ title }),
});
export const updateTask       = (id, data)  => request(`/api/v1/tasks/${id}`, {
  method: 'PATCH',
  body: JSON.stringify(data),
});
export const deleteTask       = (id)        => request(`/api/v1/tasks/${id}`, {
  method: 'DELETE',
});

// ── App info ──────────────────────────────────────
export const fetchInfo        = ()          => request('/api/v1/info');