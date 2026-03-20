import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

const Navbar = () => {
    const { user, logout } = useAuth();
    const navigate = useNavigate();

    const handleLogout = async () => {
        await logout();
        navigate('/login');
    };

    return (
        <nav className="bg-white dark:bg-gray-800 shadow-lg transition-colors duration-300">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <div className="flex justify-between h-16">
                    <div className="flex items-center space-x-3">
                        <img src="/inbotic_logo.svg" alt="Inbotic Logo" className="h-8 w-8" />
                        <Link to="/" className="text-xl font-bold text-gray-800 dark:text-white">Inbotic</Link>
                    </div>
                    <div className="flex items-center space-x-4">
                        {user ? (
                            <>
                                <span className="text-gray-600 dark:text-gray-300">Welcome, {user.username}!</span>
                                <Link to="/emails" className="text-gray-600 hover:text-gray-900 dark:text-gray-300 dark:hover:text-white">Emails</Link>
                                <Link to="/tasks" className="text-gray-600 hover:text-gray-900 dark:text-gray-300 dark:hover:text-white">Tasks</Link>
                                <Link to="/profile" className="text-gray-600 hover:text-gray-900 dark:text-gray-300 dark:hover:text-white">Profile</Link>
                                <button onClick={handleLogout} className="text-gray-600 hover:text-gray-900 dark:text-gray-300 dark:hover:text-white">Logout</button>
                            </>
                        ) : (
                            <Link to="/login" className="text-gray-600 hover:text-gray-900 dark:text-gray-300 dark:hover:text-white">Login</Link>
                        )}
                    </div>
                </div>
            </div>
        </nav>
    );
};

export default Navbar;
