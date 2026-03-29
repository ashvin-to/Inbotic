import axios from 'axios';

const api = axios.create({
    baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
    withCredentials: true, // Important for cookies
    headers: {
        'Accept': 'application/json',
    },
});

// Add a request interceptor to handle session tokens and API paths
api.interceptors.request.use(config => {
    // Add session token to header for cross-domain auth support
    const token = localStorage.getItem('session_id');
    if (token) {
        config.headers['Authorization'] = `Bearer ${token}`;
    }

    // Only add /api prefix if the URL doesn't already have it
    if (config.url && !config.url.startsWith('/api/') && !config.url.startsWith('http')) {
        config.url = `/api${config.url.startsWith('/') ? '' : '/'}${config.url}`;
    }
    return config;
});

export default api;
