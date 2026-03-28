import React, { createContext, useContext, useState, useEffect } from 'react';
import api from '../lib/api';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        checkAuth();

        // Add interceptor to handle 401s globally
        const interceptor = api.interceptors.response.use(
            (response) => response,
            (error) => {
                if (error.response?.status === 401) {
                    setUser(null);
                }
                return Promise.reject(error);
            }
        );

        return () => {
            api.interceptors.response.eject(interceptor);
        };
    }, []);

    const checkAuth = async () => {
        try {
            const response = await api.get('/me');
            if (response.data.authenticated) {
                setUser(response.data.user);
            } else {
                setUser(null);
            }
        } catch (error) {
            // Only log error if it's not a 401 (Unauthorized) which is expected when not logged in
            if (error.response?.status !== 401) {
                console.error("Auth check failed", error);
            }
            setUser(null);
        } finally {
            setLoading(false);
        }
    };



    const logout = async () => {
        try {
            // Hit backend HTML logout endpoint to clear session cookie
            await fetch(`${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'}/logout`, { method: 'GET', credentials: 'include' });
        } catch (error) {
            console.error("Logout failed", error);
        } finally {
            setUser(null);
        }
    };

    return (
        <AuthContext.Provider value={{ user, loading, logout, checkAuth }}>
            {children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => useContext(AuthContext);
