const API_URL =
  import.meta.env.VITE_API_URL ||
  "https://aktau-incident-graph-production.up.railway.app";

async function request(path, options = {}) {
  const response = await fetch(`${API_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    },
    ...options
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `API error: ${response.status}`);
  }

  return response.json();
}

export const api = {
  health: () => request("/health"),

  incidents: (filters = {}) => {
    const params = new URLSearchParams();

    if (filters.district) {
      params.set("district", filters.district);
    }

    if (filters.severity) {
      params.set("severity", filters.severity);
    }

    if (filters.type) {
      params.set("type", filters.type);
    }

    return request(`/incidents?${params.toString()}`);
  },

  graph: () => request("/graph?min_weight=0"),

  createIncident: (payload) =>
    request("/incidents", {
      method: "POST",
      body: JSON.stringify(payload)
    })
};
