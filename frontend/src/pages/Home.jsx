import React, { useEffect, useRef, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import api from '../lib/api';
import { Link } from 'react-router-dom';

const Home = () => {
    const { user } = useAuth();
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [processing, setProcessing] = useState(false);
    const [message, setMessage] = useState(null);
    const processFormRef = useRef(null);

    useEffect(() => {
        if (user) {
            const fetchData = async () => {
                try {
                    const response = await api.get('/dashboard');
                    setData(response.data);
                } catch (error) {
                    console.error('Error fetching dashboard data', error);
                }
            };
            fetchData();
        }
    }, [user]);

    const fetchData = async () => {
        try {
            const response = await api.get('/dashboard');
            setData(response.data);
        } catch (error) {
            console.error('Error fetching dashboard data', error);
        }
    };

    const handleProcessEmails = async (e) => {
        e.preventDefault();
        setProcessing(true);
        setMessage(null);

        const formData = new FormData(e.target);

        try {
            const response = await api.post('/process-emails', formData, {
                headers: {
                    'Accept': 'application/json'
                }
            });
            setMessage({ type: 'success', text: response.data.message });
            fetchData(); // Refresh dashboard data
        } catch (error) {
            console.error('Error processing emails', error);
            setMessage({ type: 'error', text: 'Failed to process emails' });
        } finally {
            setProcessing(false);
        }
    };

    if (loading) {
        return (
            <div className="flex justify-center items-center h-64 text-gray-500 dark:text-gray-400">
                Loading dashboard…
            </div>
        );
    }

    if (!user) {
        return (
            <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
                <section className="glass-panel rounded-2xl p-8 sm:p-12 text-center">
                    <p className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-700 dark:text-emerald-300">Minimal workflow</p>
                    <h1 className="display-title text-4xl sm:text-5xl font-bold text-gray-900 dark:text-white mt-4">
                        Inbox to action, without noise.
                    </h1>
                    <p className="mt-4 text-gray-700 dark:text-gray-300 max-w-2xl mx-auto">
                        Connect Gmail once and let Inbotic extract real deadlines into Google Tasks.
                    </p>
                    <div className="mt-8 flex flex-wrap items-center justify-center gap-4">
                        <a
                            href={`${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'}/auth/gmail`}
                            className="btn-primary"
                        >
                            Connect Gmail
                        </a>
                    </div>
                </section>
            </div>
        );
    }

    return (
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
            <section className="glass-panel rounded-2xl p-6 sm:p-8">
                <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-700 dark:text-emerald-300">Workspace</p>
                        <h1 className="display-title text-3xl sm:text-4xl font-bold text-gray-900 dark:text-white mt-2">
                            Hello {user.username}
                        </h1>
                        <p className="mt-2 text-gray-700 dark:text-gray-300">
                            Run extraction and manage outcomes in a clean workflow.
                        </p>
                    </div>

                    <button
                        onClick={() => processFormRef.current?.requestSubmit()}
                        disabled={processing}
                        className="btn-primary"
                    >
                        {processing ? 'Running extraction...' : 'Run extraction'}
                    </button>
                </div>

                {data?.needs_reauth && (
                    <div className="mt-4 max-w-xl alert-error flex items-start gap-4">
                        <div className="flex-1">
                            <p className="font-semibold">
                                {data.error || 'Your Google connection has expired.'}
                            </p>
                            <a
                                href="http://localhost:8000/auth/gmail"
                                className="inline-block mt-3 btn-primary !px-4 !py-2 !text-xs"
                            >
                                Reconnect Gmail
                            </a>
                        </div>
                    </div>
                )}
            </section>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <article className="glass-panel rounded-2xl p-5">
                    <p className="text-xs uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400">Tasks tracked</p>
                    <p className="mt-2 text-3xl font-bold text-gray-900 dark:text-white">{data?.ia_tasks_count || 0}</p>
                </article>
                <article className="glass-panel rounded-2xl p-5">
                    <p className="text-xs uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400">Connection</p>
                    <p className="mt-2 text-3xl font-bold text-gray-900 dark:text-white">Active</p>
                </article>
                <article className="glass-panel rounded-2xl p-5">
                    <p className="text-xs uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400">Profile</p>
                    <p className="mt-2 text-3xl font-bold text-gray-900 dark:text-white truncate">{user.username}</p>
                </article>
            </div>

            {message && (
                <div className={`${message.type === 'success' ? 'alert-success' : 'alert-error'} flex items-center justify-between`}>
                    <span>{message.text}</span>
                    <button
                        onClick={() => setMessage(null)}
                        className="ml-4 text-lg font-bold hover:opacity-70 transition-opacity"
                        aria-label="Close"
                    >
                        ×
                    </button>
                </div>
            )}

            <section className="glass-panel rounded-2xl p-6">
                <div className="flex items-center justify-between mb-6">
                    <div>
                        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Extraction settings</h3>
                        <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                            Keep it strict and fast.
                        </p>
                    </div>
                </div>
                <form ref={processFormRef} onSubmit={handleProcessEmails} className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 items-end">
                    <div>
                        <label className="block text-sm font-medium leading-6 text-gray-900 dark:text-white mb-2" htmlFor="days_back">Days back</label>
                        <input
                            className="form-input"
                            id="days_back"
                            type="number"
                            name="days_back"
                            defaultValue="7"
                            min="1"
                            max="30"
                        />
                    </div>
                    <div>
                        <label className="block text-sm font-medium leading-6 text-gray-900 dark:text-white mb-2" htmlFor="max_emails">Max emails</label>
                        <input
                            className="form-input"
                            id="max_emails"
                            type="number"
                            name="max_emails"
                            defaultValue="10"
                            min="1"
                            max="50"
                        />
                    </div>
                    <div>
                        <label className="block text-sm font-medium leading-6 text-gray-900 dark:text-white mb-2" htmlFor="max_days_ahead">Max days ahead</label>
                        <input
                            className="form-input"
                            id="max_days_ahead"
                            type="number"
                            name="max_days_ahead"
                            defaultValue="60"
                            min="1"
                            max="365"
                            title="Only create tasks when the deadline is within this many days"
                        />
                    </div>
                    <div>
                        <label className="block text-sm font-medium leading-6 text-gray-900 dark:text-white mb-2" htmlFor="pre_reminder_days">Reminder (days)</label>
                        <input
                            className="form-input"
                            id="pre_reminder_days"
                            type="number"
                            name="pre_reminder_days"
                            defaultValue="1"
                            min="0"
                            max="14"
                            title="Create a reminder this many days before the deadline (0 = no reminder)"
                        />
                    </div>
                    <div>
                        <label className="block text-sm font-medium leading-6 text-gray-900 dark:text-white mb-2" htmlFor="pre_reminder_hours">Reminder (hours)</label>
                        <input
                            className="form-input"
                            id="pre_reminder_hours"
                            type="number"
                            name="pre_reminder_hours"
                            defaultValue="1"
                            min="0"
                            max="23"
                            title="Create a reminder N hours before the deadline (e.g., 1 for 1 hour prior)"
                        />
                    </div>
                    <div>
                        <button
                            type="submit"
                            disabled={processing}
                            className="btn-primary w-full"
                        >
                            {processing ? 'Processing...' : 'Process'}
                        </button>
                    </div>
                </form>
            </section>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <Link to="/tasks" className="glass-panel rounded-2xl p-6 group">
                    <h3 className="font-semibold text-gray-900 dark:text-white group-hover:text-emerald-600 dark:group-hover:text-emerald-400 transition-colors">📋 Open Tasks</h3>
                    <p className="text-sm text-gray-600 dark:text-gray-400 mt-2">Review, edit, and complete tasks.</p>
                </Link>
                <Link to="/profile" className="glass-panel rounded-2xl p-6 group">
                    <h3 className="font-semibold text-gray-900 dark:text-white group-hover:text-emerald-600 dark:group-hover:text-emerald-400 transition-colors">⚙️ Profile & Settings</h3>
                    <p className="text-sm text-gray-600 dark:text-gray-400 mt-2">Manage account and OAuth setup.</p>
                </Link>
            </div>
        </div>
    );
};

export default Home;
