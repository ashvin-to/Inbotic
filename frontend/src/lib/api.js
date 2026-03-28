import axios from 'axios';

const api = axios.create({
    baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
    withCredentials: true, // Important for cookies
    headers: {
        'Accept': 'application/json',
    },
});

// Add a request interceptor to handle API paths consistently
api.interceptors.request.use(config => {
    // Only add /api prefix if the URL doesn't already have it
    if (config.url && !config.url.startsWith('/api/') && !config.url.startsWith('http')) {
        config.url = `/api${config.url.startsWith('/') ? '' : '/'}${config.url}`;
    }
    return config;
});

export default api;
