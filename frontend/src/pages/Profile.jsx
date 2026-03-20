import React, { useEffect, useState } from 'react';
import Layout from '../components/Layout';
import api from '../lib/api';
import { Link } from 'react-router-dom';

const Profile = () => {
    const [profile, setProfile] = useState(null);
    const [loading, setLoading] = useState(true);
    const [message, setMessage] = useState(null);
    const [error, setError] = useState(null);

    // Form states
    const [isEditingUsername, setIsEditingUsername] = useState(false);
    const [newUsername, setNewUsername] = useState('');
    const [passwordForm, setPasswordForm] = useState({
        new_password: '',
        confirm_password: ''
    });

    useEffect(() => {
        fetchProfile();
    }, []);

    const fetchProfile = async () => {
        try {
            setLoading(true);
            // Fetch user data
            const response = await api.get('/me');

            const userData = response.data.user || response.data;
            setProfile(userData);
            setNewUsername(userData.username);

            // If there's a profile photo, preload it
            if (userData.profile_photo) {
                const img = new Image();
                const photoUrl = userData.profile_photo.startsWith('http')
                    ? userData.profile_photo
                    : `http://localhost:8000${userData.profile_photo}`;
                img.src = photoUrl;
            }

            setError(null);
        } catch (error) {
            console.error("Error fetching profile:", error);
            setError("Failed to load profile");

            // If unauthorized, redirect to login
            if (error.response?.status === 401) {
                window.location.href = '/login';
            }
        } finally {
            setLoading(false);
        }
    };

    const handlePhotoUpload = async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        // Validate file type and size
        if (!file.type.startsWith('image/')) {
            setError('Only image files are allowed');
            setTimeout(() => setError(null), 3000);
            return;
        }

        // Check file size (5MB max)
        if (file.size > 5 * 1024 * 1024) {
            setError('File size too large. Maximum 5MB allowed.');
            setTimeout(() => setError(null), 3000);
            return;
        }

        const formData = new FormData();
        formData.append('file', file);

        try {
            setLoading(true);
            const response = await api.post('/api/profile/update-photo', formData, {
                headers: {
                    'Content-Type': 'multipart/form-data',
                    'Accept': 'application/json'
                }
            });

            // Use the full_photo_url if available, otherwise construct it
            const photoUrl = response.data.full_photo_url ||
                `http://localhost:8000${response.data.profile_photo}?t=${Date.now()}`;

            // Update both profile state and local storage
            const updatedProfile = {
                ...profile,
                profile_photo: response.data.profile_photo,
                full_photo_url: photoUrl
            };

            setProfile(updatedProfile);

            // Store in local storage for persistence
            try {
                const userData = JSON.parse(localStorage.getItem('user') || '{}');
                localStorage.setItem('user', JSON.stringify({
                    ...userData,
                    profile_photo: response.data.profile_photo,
                    full_photo_url: photoUrl
                }));
            } catch (storageError) {
                console.error('Error updating local storage:', storageError);
            }

            setMessage('Profile photo updated successfully');
            setTimeout(() => setMessage(null), 3000);
        } catch (err) {
            console.error('Upload error:', err);
            const errorMessage = err.response?.data?.error ||
                err.message ||
                'Failed to update profile photo';
            setError(errorMessage);
            setTimeout(() => setError(null), 3000);
        } finally {
            setLoading(false);
            // Reset the file input
            e.target.value = '';
        }
    };

    const handleUpdateUsername = async (e) => {
        e.preventDefault();
        const formData = new FormData();
        formData.append('new_username', newUsername);

        try {
            const response = await api.post('/profile/update-username', formData, {
                headers: {
                    'Accept': 'application/json'
                }
            });
            setProfile({ ...profile, username: response.data.username });
            setIsEditingUsername(false);
            setMessage("Username updated successfully");
            setTimeout(() => setMessage(null), 3000);
        } catch (err) {
            console.error(err);
            setError("Failed to update username");
            setTimeout(() => setError(null), 3000);
        }
    };

    const handleUpdatePassword = async (e) => {
        e.preventDefault();
        if (passwordForm.new_password !== passwordForm.confirm_password) {
            setError("Passwords do not match");
            return;
        }

        const formData = new FormData();
        formData.append('new_password', passwordForm.new_password);
        formData.append('confirm_password', passwordForm.confirm_password);

        try {
            await api.post('/profile/update-password', formData, {
                headers: {
                    'Accept': 'application/json'
                }
            });
            setPasswordForm({ new_password: '', confirm_password: '' });
            setMessage("Password updated successfully");
            setTimeout(() => setMessage(null), 3000);
        } catch (err) {
            console.error(err);
            setError("Failed to update password");
            setTimeout(() => setError(null), 3000);
        }
    };

    if (loading) {
        return (
            <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8 text-center">
                Loading...
            </div>
        );
    }

    if (!profile) {
        return (
            <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8 text-center">
                Error loading profile.
            </div>
        );
    }

    return (
        <div className="max-w-7xl mx-auto py-6 px-4 sm:px-6 lg:px-8">
            <div className="mb-8">
                <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Profile Settings</h1>
                <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">Manage your account information and security preferences.</p>
            </div>

            {message && (
                <div className="mb-4 p-4 rounded-md bg-green-50 border border-green-200 text-green-700 dark:bg-green-900/20 dark:border-green-800 dark:text-green-200">
                    {message}
                </div>
            )}
            {error && (
                <div className="mb-4 p-4 rounded-md bg-red-50 border border-red-200 text-red-700 dark:bg-red-900/20 dark:border-red-800 dark:text-red-200">
                    {error}
                </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                {/* Profile Photo Section */}
                <div className="md:col-span-1">
                    <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6 text-center">
                        <div className="relative inline-block group">
                            {profile.profile_photo ? (
                                <img
                                    className="h-32 w-32 rounded-full object-cover mx-auto ring-4 ring-white dark:ring-gray-700 shadow-lg"
                                    src={profile.full_photo_url || (profile.profile_photo.startsWith('http') ? profile.profile_photo : `http://localhost:8000${profile.profile_photo}?t=${Date.now()}`)}
                                    alt={profile.username}
                                    onError={(e) => {
                                        // If image fails to load, fallback to default avatar
                                        e.target.onerror = null;
                                        e.target.style.display = 'none';
                                        // Also try to remove the broken image from DOM or show fallback
                                        e.target.parentElement.innerHTML = `<div class="h-32 w-32 rounded-full bg-indigo-100 dark:bg-indigo-900/50 flex items-center justify-center mx-auto ring-4 ring-white dark:ring-gray-700 shadow-lg"><span class="text-4xl font-medium text-indigo-600 dark:text-indigo-400">${profile.username[0].toUpperCase()}</span></div>`;
                                    }}
                                />
                            ) : (
                                <div className="h-32 w-32 rounded-full bg-indigo-100 dark:bg-indigo-900/50 flex items-center justify-center mx-auto ring-4 ring-white dark:ring-gray-700 shadow-lg">
                                    <span className="text-4xl font-medium text-indigo-600 dark:text-indigo-400">
                                        {profile.username[0].toUpperCase()}
                                    </span>
                                </div>
                            )}
                            <label htmlFor="photo-upload" className="absolute bottom-0 right-0 bg-white dark:bg-gray-700 rounded-full p-2 shadow-lg cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors border border-gray-200 dark:border-gray-600">
                                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-gray-600 dark:text-gray-300" viewBox="0 0 20 20" fill="currentColor">
                                    <path d="M13.586 3.586a2 2 0 112.828 2.828l-.793.793-2.828-2.828.793-.793zM11.379 5.793L3 14.172V17h2.828l8.38-8.379-2.83-2.828z" />
                                </svg>
                                <input
                                    id="photo-upload"
                                    type="file"
                                    className="hidden"
                                    accept="image/*"
                                    onChange={handlePhotoUpload}
                                />
                            </label>
                        </div>
                        <div className="mt-6 border-t border-gray-200 dark:border-gray-700 pt-4">
                            <h3 className="text-lg font-medium text-gray-900 dark:text-white">{profile.username}</h3>
                            <p className="text-sm text-gray-500 dark:text-gray-400">{profile.email}</p>
                        </div>
                    </div>
                </div>

                {/* Forms Section */}
                <div className="md:col-span-2 space-y-6">
                    {/* Update Username */}
                    <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6">
                        <div className="flex justify-between items-center mb-4">
                            <h3 className="text-lg font-medium leading-6 text-gray-900 dark:text-white">Profile Information</h3>
                            {!isEditingUsername && (
                                <button
                                    onClick={() => setIsEditingUsername(true)}
                                    className="text-sm text-indigo-600 dark:text-indigo-400 hover:text-indigo-500"
                                >
                                    Edit
                                </button>
                            )}
                        </div>

                        {isEditingUsername ? (
                            <form onSubmit={handleUpdateUsername} className="space-y-4">
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Username</label>
                                    <div className="mt-1 flex rounded-md shadow-sm">
                                        <input
                                            type="text"
                                            value={newUsername}
                                            onChange={(e) => setNewUsername(e.target.value)}
                                            className="flex-1 block w-full rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2"
                                            required
                                            minLength={3}
                                            maxLength={30}
                                        />
                                    </div>
                                </div>
                                <div className="flex justify-end gap-2">
                                    <button
                                        type="button"
                                        onClick={() => setIsEditingUsername(false)}
                                        className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md text-sm font-medium text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700"
                                    >
                                        Cancel
                                    </button>
                                    <button
                                        type="submit"
                                        className="px-3 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
                                    >
                                        Save
                                    </button>
                                </div>
                            </form>
                        ) : (
                            <div className="space-y-3">
                                <div>
                                    <label className="block text-sm font-medium text-gray-500 dark:text-gray-400">Username</label>
                                    <p className="mt-1 text-sm text-gray-900 dark:text-white">{profile.username}</p>
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-500 dark:text-gray-400">Email</label>
                                    <p className="mt-1 text-sm text-gray-900 dark:text-white">{profile.email}</p>
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Update Password */}
                    <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6">
                        <h3 className="text-lg font-medium leading-6 text-gray-900 dark:text-white mb-4">Security</h3>
                        <form onSubmit={handleUpdatePassword} className="space-y-4">
                            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">New Password</label>
                                    <input
                                        type="password"
                                        value={passwordForm.new_password}
                                        onChange={(e) => setPasswordForm({ ...passwordForm, new_password: e.target.value })}
                                        className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2"
                                        required
                                        minLength={6}
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Confirm Password</label>
                                    <input
                                        type="password"
                                        value={passwordForm.confirm_password}
                                        onChange={(e) => setPasswordForm({ ...passwordForm, confirm_password: e.target.value })}
                                        className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2"
                                        required
                                        minLength={6}
                                    />
                                </div>
                            </div>
                            <div className="flex justify-end">
                                <button
                                    type="submit"
                                    className="inline-flex justify-center py-2 px-4 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 transition-colors"
                                >
                                    Update Password
                                </button>
                            </div>
                        </form>
                    </div>

                    {/* Account Status */}
                    <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6">
                        <h3 className="text-lg font-medium leading-6 text-gray-900 dark:text-white mb-4">Account Status</h3>
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-sm font-medium text-gray-700 dark:text-gray-300">Gmail Connection</p>
                                <p className="text-xs text-gray-500 dark:text-gray-400">
                                    {profile.gmail_tokens_connected ? 'Connected and active.' : 'Not connected.'}
                                </p>
                            </div>
                            {profile.gmail_tokens_connected ? (
                                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300">
                                    Active
                                </span>
                            ) : (
                                <a href="http://localhost:8000/auth/gmail" className="inline-flex items-center px-3 py-1.5 border border-transparent text-xs font-medium rounded text-indigo-700 bg-indigo-100 hover:bg-indigo-200 dark:bg-indigo-900/30 dark:text-indigo-300 dark:hover:bg-indigo-900/50 transition-colors">
                                    Connect
                                </a>
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default Profile;
