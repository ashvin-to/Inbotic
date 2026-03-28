import React from 'react';
import { Link, NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

const Navbar = () => {
    const { user, logout } = useAuth();
    const navigate = useNavigate();

    const handleLogout = async () => {
        await logout();
        navigate('/login');
    };

    const navClass = ({ isActive }) => {
        const base = 'px-3 py-2 rounded-full text-sm font-semibold transition-all duration-200';
        const active = 'bg-emerald-600 text-white shadow-sm';
        const idle = 'text-gray-700 hover:text-gray-900 hover:bg-white/70 dark:text-gray-200 dark:hover:text-white dark:hover:bg-gray-800/80';
        return `${base} ${isActive ? active : idle}`;
    };

    return (
        <nav className="sticky top-0 z-40 border-b border-black/10 bg-white/65 backdrop-blur-xl dark:border-white/10 dark:bg-gray-900/65 transition-colors duration-300">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex items-center gap-3">
                        <img src="/inbotic_logo.svg" alt="Inbotic Logo" className="h-9 w-9 rounded-md ring-1 ring-black/10 dark:ring-white/15" />
                        <Link to="/" className="display-title text-xl font-bold text-gray-900 dark:text-white">Inbotic</Link>
                        <span className="hidden sm:inline-block text-xs font-semibold tracking-wide uppercase px-2 py-1 rounded-full bg-emerald-100 text-emerald-800 dark:bg-emerald-900/45 dark:text-emerald-200">Manager Console</span>
                    </div>

                    <div className="flex flex-wrap items-center gap-2 sm:gap-3">
                        {user ? (
                            <>
                                <span className="hidden lg:inline text-sm text-gray-700 dark:text-gray-300">Welcome, <strong>{user.username}</strong></span>
                                <NavLink to="/tasks" className={navClass}>Tasks</NavLink>
                                <NavLink to="/profile" className={navClass}>Profile</NavLink>
                                <button
                                    onClick={handleLogout}
                                    className="px-3 py-2 rounded-full text-sm font-semibold text-rose-700 bg-rose-50 hover:bg-rose-100 dark:text-rose-200 dark:bg-rose-950/40 dark:hover:bg-rose-900/50 transition-colors"
                                >
                                    Logout
                                </button>
                            </>
                        ) : (
                            <a
                                href={`${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'}/auth/gmail`}
                                className="px-4 py-2 rounded-full text-sm font-semibold bg-emerald-600 text-white hover:bg-emerald-500 transition-colors"
                            >
                                Login with Gmail
                            </a>
                        )}
                    </div>
                </div>
            </div>
        </nav>
    );
};

export default Navbar;
