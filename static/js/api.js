/**
 * Roomora API Client Module
 * Provides standardized fetch wrappers, CSRF token handling, and UUID generation.
 */

export function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

export function generateUUID() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
    const r = Math.random() * 16 | 0, v = c === 'x' ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
}

export function announce(message) {
  const status = document.querySelector("#journey-status");
  if (status) status.textContent = message;
}

export async function apiFetch(endpoint, options = {}) {
  const headers = {
    "Accept": "application/json",
    ...(options.headers || {})
  };

  if (options.method && options.method.toUpperCase() !== "GET") {
    const csrfToken = getCookie("csrftoken");
    if (csrfToken && !headers["X-CSRFToken"]) {
      headers["X-CSRFToken"] = csrfToken;
    }
    if (options.body && typeof options.body === "object" && !(options.body instanceof FormData)) {
      headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(options.body);
    }
  }

  const response = await fetch(endpoint, {
    ...options,
    headers,
    credentials: "same-origin"
  });

  if (!response.ok) {
    let errorDetail = "Thao tác chưa hoàn tất.";
    try {
      const errJson = await response.json();
      errorDetail = errJson.detail || errJson.error || errorDetail;
    } catch {}
    const error = new Error(errorDetail);
    error.status = response.status;
    throw error;
  }

  return response.json();
}
