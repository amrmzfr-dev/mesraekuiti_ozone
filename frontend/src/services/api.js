// API Configuration for Ozone Telemetry Backend
const API_CONFIG = {
  BASE_URL: 'https://www.ozone-p2.mesraekuiti.com',
  ENDPOINTS: {
    LOGIN: '/api/auth/login/',
    LOGOUT: '/api/auth/logout/',
    REGISTER: '/api/auth/register/',
    USER_INFO: '/api/auth/user/',
    CHECK_AUTH: '/api/auth/check/',
    CSRF: '/api/csrf/',
    TELEMETRY: '/api/telemetry/',
    DEVICES: '/api/devices/',
    MACHINES: '/api/machines/',
    OUTLETS: '/api/outlets/',
    HANDSHAKE: '/api/handshake/',
    DEVICE_EVENTS: '/api/device/events/',
    DEVICES_DATA: '/api/devices-data/',
    STATS: '/api/test/stats/',
    STATS_OPTIONS: '/api/test/stats-options/',
    STATS_EXPORT: '/api/test/stats-export.csv',
    EXPORT: '/api/export/',
    FLUSH: '/api/flush/',
  }
};

export const buildApiUrl = (endpoint) => `${API_CONFIG.BASE_URL}${endpoint}`;

export const getApiHeaders = (token = null) => {
  const headers = { 'Content-Type': 'application/json' };
  const jwt = token || window.localStorage.getItem('jwt');
  if (jwt) { headers['Authorization'] = `Bearer ${jwt}`; }
  return headers;
};

export const apiService = {
  // Ensure CSRF cookie is set and return token from cookie header echo (backend just sets cookie)
  login: async (credentials) => {
    const response = await fetch(buildApiUrl(API_CONFIG.ENDPOINTS.LOGIN), {
      method: 'POST', headers: getApiHeaders(), body: JSON.stringify(credentials),
    });
    const data = await response.json();
    if (data && data.token) {
      window.localStorage.setItem('jwt', data.token);
    }
    return data;
  },
  logout: async () => {
    window.localStorage.removeItem('jwt');
    return { success: true };
  },
  register: async (userData) => {
    const response = await fetch(buildApiUrl(API_CONFIG.ENDPOINTS.REGISTER), { method: 'POST', headers: getApiHeaders(), body: JSON.stringify(userData) });
    return response.json();
  },
  getUserInfo: async () => {
    const response = await fetch(buildApiUrl(API_CONFIG.ENDPOINTS.USER_INFO), { method: 'GET', headers: getApiHeaders() });
    return response.json();
  },
  checkAuth: async () => {
    const response = await fetch(buildApiUrl(API_CONFIG.ENDPOINTS.CHECK_AUTH), { method: 'GET', headers: getApiHeaders() });
    return response.json();
  },
  getTelemetryData: async (params = {}) => {
    const queryString = new URLSearchParams(params).toString();
    const url = buildApiUrl(API_CONFIG.ENDPOINTS.TELEMETRY) + (queryString ? `?${queryString}` : '');
    const response = await fetch(url, { method: 'GET', headers: getApiHeaders() });
    return response.json();
  },
  getDevices: async () => {
    const response = await fetch(buildApiUrl(API_CONFIG.ENDPOINTS.DEVICES), { method: 'GET', headers: getApiHeaders() });
    return response.json();
  },
  getMachines: async () => {
    const response = await fetch(buildApiUrl(API_CONFIG.ENDPOINTS.MACHINES), { method: 'GET', headers: getApiHeaders() });
    return response.json();
  },
  getOutlets: async () => {
    const response = await fetch(buildApiUrl(API_CONFIG.ENDPOINTS.OUTLETS), { method: 'GET', headers: getApiHeaders() });
    return response.json();
  },
  handshake: async (deviceData) => {
    const response = await fetch(buildApiUrl(API_CONFIG.ENDPOINTS.HANDSHAKE), { method: 'POST', headers: getApiHeaders(), body: JSON.stringify(deviceData) });
    return response.json();
  },
  submitDeviceEvent: async (eventData, token) => {
    const response = await fetch(buildApiUrl(API_CONFIG.ENDPOINTS.DEVICE_EVENTS), { method: 'POST', headers: getApiHeaders(token), body: JSON.stringify(eventData) });
    return response.json();
  },
  getDevicesData: async () => {
    const response = await fetch(buildApiUrl(API_CONFIG.ENDPOINTS.DEVICES_DATA), { method: 'GET', headers: getApiHeaders() });
    return response.json();
  },
  getStats: async (params = {}) => {
    const queryString = new URLSearchParams(params).toString();
    const url = buildApiUrl(API_CONFIG.ENDPOINTS.STATS) + (queryString ? `?${queryString}` : '');
    const response = await fetch(url, { method: 'GET', headers: getApiHeaders(), credentials: 'include' });
    return response.json();
  },
  getStatsOptions: async (params = {}) => {
    const queryString = new URLSearchParams(params).toString();
    const url = buildApiUrl(API_CONFIG.ENDPOINTS.STATS_OPTIONS) + (queryString ? `?${queryString}` : '');
    const response = await fetch(url, { method: 'GET', headers: getApiHeaders(), credentials: 'include' });
    return response.json();
  },
  exportStats: async (params = {}) => {
    const queryString = new URLSearchParams(params).toString();
    const url = buildApiUrl(API_CONFIG.ENDPOINTS.STATS_EXPORT) + (queryString ? `?${queryString}` : '');
    const response = await fetch(url, { method: 'GET', headers: getApiHeaders(), credentials: 'include' });
    return response.blob();
  },
  exportData: async (params = {}) => {
    const queryString = new URLSearchParams(params).toString();
    const url = buildApiUrl(API_CONFIG.ENDPOINTS.EXPORT) + (queryString ? `?${queryString}` : '');
    const response = await fetch(url, { method: 'GET', headers: getApiHeaders(), credentials: 'include' });
    return response.blob();
  },
  flushData: async () => {
    const response = await fetch(buildApiUrl(API_CONFIG.ENDPOINTS.FLUSH), { method: 'POST', headers: getApiHeaders(), credentials: 'include' });
    return response.json();
  },
  flushAllData: async () => {
    const response = await fetch(buildApiUrl(API_CONFIG.ENDPOINTS.FLUSH), { method: 'POST', headers: getApiHeaders(), credentials: 'include' });
    return response.json();
  },
};

export { API_CONFIG };


