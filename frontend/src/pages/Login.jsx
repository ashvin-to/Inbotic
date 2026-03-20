import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { useNavigate, Link, useLocation } from 'react-router-dom';
import { FiMail, FiLock, FiEye, FiEyeOff, FiLogIn } from 'react-icons/fi';
import { motion } from 'framer-motion';

const Login = () => {
    const [formData, setFormData] = useState({
        username: '',
        password: '',
    });
    const [errors, setErrors] = useState({});
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [showPassword, setShowPassword] = useState(false);
    const [authError, setAuthError] = useState('');
    const { login, isAuthenticated } = useAuth();
    const navigate = useNavigate();
    const location = useLocation();

    // Redirect if already authenticated
    useEffect(() => {
        if (isAuthenticated) {
            navigate(location.state?.from?.pathname || '/', { replace: true });
        }
    }, [isAuthenticated, navigate, location.state]);

    // Handle form input changes
    const handleChange = (e) => {
        const { name, value } = e.target;
        setFormData(prev => ({
            ...prev,
            [name]: value
        }));

        // Clear error for the field being edited
        if (errors[name]) {
            setErrors(prev => ({
                ...prev,
                [name]: ''
            }));
        }

        // Clear auth error when user starts typing
        if (authError) setAuthError('');
    };

    // Form validation
    const validateForm = () => {
        const newErrors = {};

        if (!formData.username.trim()) {
            newErrors.username = 'Username is required';
        }

        if (!formData.password) {
            newErrors.password = 'Password is required';
        } else if (formData.password.length < 6) {
            newErrors.password = 'Password must be at least 6 characters';
        }

        setErrors(newErrors);
        return Object.keys(newErrors).length === 0;
    };

    // Handle form submission
    const handleSubmit = async (e) => {
        e.preventDefault();
        setAuthError('');

        if (!validateForm()) {
            return;
        }

        setIsSubmitting(true);

        try {
            const success = await login(formData.username, formData.password);
            if (success) {
                // Redirect to the home page after successful login
                const redirectTo = location.state?.from?.pathname || '/';
                navigate(redirectTo, { replace: true });
            } else {
                setAuthError('Invalid username or password');
            }
        } catch (err) {
            console.error('Login error:', err);
            setAuthError('An error occurred during login. Please try again.');
        } finally {
            setIsSubmitting(false);
        }
    };

    // Animation variants
    const containerVariants = {
        hidden: { opacity: 0, y: 20 },
        visible: {
            opacity: 1,
            y: 0,
            transition: {
                duration: 0.5,
                ease: 'easeOut'
            }
        }
    };

    return (
        <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-50 dark:from-gray-900 dark:to-gray-800 p-4 transition-colors duration-300">
            <motion.div
                className="w-full max-w-xs bg-white dark:bg-gray-800 rounded-xl shadow-md overflow-hidden border border-gray-100 dark:border-gray-700"
                variants={containerVariants}
                initial="hidden"
                animate="visible"
            >
                {/* Header with gradient background */}
                <div className="bg-gradient-to-r from-blue-600 to-indigo-600 p-4 text-center">
                    <h2 className="text-xl font-bold text-white tracking-tight">Welcome Back</h2>
                    <p className="text-blue-100 text-xs mt-1 opacity-90">
                        Sign in to continue
                    </p>
                </div>

                {/* Form container */}
                <div className="p-5">
                    {authError && (
                        <motion.div
                            className="bg-red-50 dark:bg-red-900/20 border-l-4 border-red-500 p-3 rounded-lg mb-4"
                            initial={{ opacity: 0, y: -10 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0 }}
                            transition={{ duration: 0.2 }}
                        >
                            <div className="flex items-start">
                                <div className="flex-shrink-0 pt-0.5">
                                    <svg className="h-4 w-4 text-red-500" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                                        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                                    </svg>
                                </div>
                                <div className="ml-3">
                                    <p className="text-xs font-medium text-red-800 dark:text-red-200">{authError}</p>
                                </div>
                            </div>
                        </motion.div>
                    )}

                    <form className="space-y-4" onSubmit={handleSubmit} noValidate>
                        <div className="space-y-4">
                            <div>
                                <label htmlFor="username" className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                    Username
                                </label>
                                <div className="relative">
                                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                        <FiMail className="h-3.5 w-3.5 text-gray-400 dark:text-gray-500" />
                                    </div>
                                    <input
                                        id="username"
                                        name="username"
                                        type="text"
                                        autoComplete="username"
                                        className={`block w-full pl-9 pr-3 py-2 text-sm dark:bg-gray-700 dark:text-white ${errors.username
                                            ? 'border-red-300 text-red-900 placeholder-red-300 focus:ring-red-500 focus:border-red-500 dark:border-red-700 dark:text-red-300 dark:placeholder-red-700'
                                            : 'border-gray-300 placeholder-gray-400 focus:ring-blue-500 focus:border-blue-500 dark:border-gray-600 dark:placeholder-gray-500'} 
                                        border rounded-lg focus:ring-1 focus:ring-opacity-50 transition duration-150 shadow-sm`}
                                        placeholder="Enter username"
                                        value={formData.username}
                                        onChange={handleChange}
                                        disabled={isSubmitting}
                                    />
                                </div>
                                {errors.username && (
                                    <p className="mt-1.5 text-xs text-red-600 dark:text-red-400 flex items-center">
                                        <svg className="h-3.5 w-3.5 mr-1" fill="currentColor" viewBox="0 0 20 20">
                                            <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                                        </svg>
                                        {errors.username}
                                    </p>
                                )}
                            </div>

                            <div>
                                <div className="flex justify-between items-center">
                                    <label htmlFor="password" className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                        Password
                                    </label>
                                    <Link to="/forgot-password" className="text-sm font-medium text-blue-600 hover:text-blue-500 dark:text-blue-400 dark:hover:text-blue-300">
                                        Forgot password?
                                    </Link>
                                </div>
                                <div className="relative">
                                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                        <FiLock className="h-3.5 w-3.5 text-gray-400 dark:text-gray-500" />
                                    </div>
                                    <input
                                        id="password"
                                        name="password"
                                        type={showPassword ? 'text' : 'password'}
                                        autoComplete="current-password"
                                        className={`block w-full pl-9 pr-9 py-2 text-sm dark:bg-gray-700 dark:text-white ${errors.password
                                            ? 'border-red-300 text-red-900 placeholder-red-300 focus:ring-red-500 focus:border-red-500 dark:border-red-700 dark:text-red-300 dark:placeholder-red-700'
                                            : 'border-gray-300 placeholder-gray-400 focus:ring-blue-500 focus:border-blue-500 dark:border-gray-600 dark:placeholder-gray-500'} 
                                        border rounded-lg focus:ring-1 focus:ring-opacity-50 transition duration-150 shadow-sm`}
                                        placeholder="Enter password"
                                        value={formData.password}
                                        onChange={handleChange}
                                        disabled={isSubmitting}
                                    />
                                    <button
                                        type="button"
                                        className="absolute inset-y-0 right-0 pr-3 flex items-center text-gray-400 hover:text-gray-500 dark:text-gray-500 dark:hover:text-gray-400 transition-colors"
                                        onClick={() => setShowPassword(!showPassword)}
                                        tabIndex="-1"
                                        disabled={isSubmitting}
                                    >
                                        {showPassword ? (
                                            <FiEyeOff className="h-3.5 w-3.5" />
                                        ) : (
                                            <FiEye className="h-3.5 w-3.5" />
                                        )}
                                    </button>
                                </div>
                                {errors.password && (
                                    <p className="mt-1.5 text-xs text-red-600 dark:text-red-400 flex items-center">
                                        <svg className="h-3.5 w-3.5 mr-1" fill="currentColor" viewBox="0 0 20 20">
                                            <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                                        </svg>
                                        {errors.password}
                                    </p>
                                )}
                            </div>
                        </div>

                        <div className="pt-1">
                            <motion.button
                                type="submit"
                                className={`group relative w-full flex justify-center py-2.5 px-4 border border-transparent text-sm font-medium rounded-lg text-white ${isSubmitting ? 'bg-blue-500' : 'bg-blue-600 hover:bg-blue-700'} focus:outline-none focus:ring-2 focus:ring-offset-1 focus:ring-blue-500 disabled:opacity-80 disabled:cursor-not-allowed transition-all duration-150`}
                                disabled={isSubmitting}
                                whileTap={{ scale: isSubmitting ? 1 : 0.98 }}
                            >
                                <span className="absolute left-0 inset-y-0 flex items-center pl-3">
                                    <FiLogIn className={`h-4 w-4 text-blue-200 group-hover:text-white transition-opacity ${isSubmitting ? 'opacity-0' : 'opacity-100'}`} />
                                </span>
                                {isSubmitting ? (
                                    <div className="flex items-center">
                                        <svg className="animate-spin -ml-1 mr-2 h-3.5 w-3.5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                        </svg>
                                        Signing in...
                                    </div>
                                ) : (
                                    <span className="font-medium">Sign in</span>
                                )}
                            </motion.button>
                        </div>
                    </form>

                    <div className="mt-6">
                        <div className="relative">
                            <div className="absolute inset-0 flex items-center">
                                <div className="w-full border-t border-gray-200 dark:border-gray-700"></div>
                            </div>
                            <div className="relative flex justify-center">
                                <span className="px-3 bg-white dark:bg-gray-800 text-xs text-gray-500 dark:text-gray-400 font-medium">New to Inbotic?</span>
                            </div>
                        </div>

                        <div className="mt-5">
                            <Link
                                to="/register"
                                className="w-full flex justify-center py-2 px-4 border border-gray-300 dark:border-gray-600 rounded-lg text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600 focus:outline-none focus:ring-2 focus:ring-offset-1 focus:ring-blue-500 transition-all duration-150 shadow-sm hover:shadow"
                            >
                                Create an account
                            </Link>
                        </div>
                    </div>
                </div>
            </motion.div>
        </div>
    );
};

export default Login;
