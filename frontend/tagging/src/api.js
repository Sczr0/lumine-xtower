/**
 * Admin API 客户端
 */
const BASE = '/admin';

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(body.error || `HTTP ${res.status}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

export function listImages(params = {}) {
  const q = new URLSearchParams();
  if (params.status) q.set('status', params.status);
  if (params.page) q.set('page', params.page);
  if (params.per_page) q.set('per_page', params.per_page);
  return request(`/images?${q}`);
}

export function getImage(id) {
  return request(`/images/${encodeURIComponent(id)}`);
}

export function updateImage(id, data) {
  return request(`/images/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

export function getStats() {
  return request('/stats');
}
