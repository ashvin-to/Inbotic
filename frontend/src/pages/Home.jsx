import React, { useEffect, useState, useRef } from 'react';
import { useAuth } from '../context/AuthContext';
import api from '../lib/api';
import { Link } from 'react-router-dom';

const onboardingHighlights = [
    {
        title: 'Connect Gmail first',
        description: 'Secure OAuth 2.0 flow keeps your inbox private while giving Inbotic the minimum scope it needs.'
    },
    {
        title: 'Auto registration',
        description: 'We create your account the moment Gmail is linked - no additional forms, passwords or friction.'
    },
    {
        title: 'Realtime extraction',
        description: 'Inbotic parses deadlines, commitments and action items from email bodies and drafts Google Tasks.'
    }
];

const quickActions = [
    {
        to: '/emails',
        title: 'View Emails',
        copy: 'Browse enriched email summaries, attachments and extracted metadata.',
        icon: '📬'
    },
    {
        to: '/tasks',
        title: 'Manage Tasks',
        copy: 'Check what was created inside Google Tasks and mark outcomes.',
        icon: '✅'
    },
    {
        to: '/profile',
        title: 'Profile & Tokens',
        copy: 'Update notification preferences and reset OAuth credentials.',
        icon: '⚙️'
    }
];

const Home = () => {
    const { user } = useAuth();
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [processing, setProcessing] = useState(false);
    const [message, setMessage] = useState(null);
    const [chatInput, setChatInput] = useState('');
    // Load chat history from sessionStorage on init
    const [chatHistory, setChatHistory] = useState(() => {
        try {
            const saved = sessionStorage.getItem('inbotic_chat_history');
            return saved ? JSON.parse(saved) : [];
        } catch {
            return [];
        }
    });
    const [chatLoading, setChatLoading] = useState(false);
    const chatEndRef = useRef(null);

    // Auto-scroll to bottom when new messages arrive
    useEffect(() => {
        chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [chatHistory, chatLoading]);

    // Save chat history to sessionStorage whenever it changes
    useEffect(() => {
        if (chatHistory.length > 0) {
            sessionStorage.setItem('inbotic_chat_history', JSON.stringify(chatHistory));
        }
    }, [chatHistory]);

    useEffect(() => {
        // Show dashboard immediately, load data in background
        setLoading(false);

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

    const handleChatSubmit = async (e) => {
        e.preventDefault();
        if (!chatInput.trim()) return;

        const message = chatInput;
        setChatInput('');
        setChatHistory(prev => [...prev, { role: 'user', content: message }]);
        setChatLoading(true);

        const formData = new FormData();
        formData.append('chat_message', message);

        try {
            const response = await api.post('/chat/send', formData, {
                headers: {
                    'Accept': 'application/json'
                }
            });
            setChatHistory(prev => [...prev, { role: 'assistant', content: response.data.reply }]);
        } catch (error) {
            console.error('Error sending message', error);
            setChatHistory(prev => [...prev, { role: 'assistant', content: 'Sorry, something went wrong.' }]);
        } finally {
            setChatLoading(false);
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
            <div className="flex flex-col gap-8 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
                <section className="relative overflow-hidden rounded-2xl bg-gray-900 px-6 py-12 text-center shadow-xl sm:px-12 sm:py-16">
                    <div className="absolute inset-0 bg-gradient-to-br from-blue-600/20 to-purple-600/20" />
                    <span className="relative inline-flex items-center rounded-full bg-gray-800/50 px-3 py-1 text-sm font-medium text-gray-300 ring-1 ring-inset ring-gray-700/50 mb-6">
                        Gmail-first automation
                    </span>
                    <h1 className="relative text-3xl font-bold tracking-tight text-white sm:text-5xl mb-6">
                        Inbotic keeps commitments from slipping through the inbox.
                    </h1>
                    <p className="relative mx-auto max-w-2xl text-lg leading-8 text-gray-300 mb-10">
                        Link your Gmail once, then let Inbotic read, extract and sync actionable tasks directly into Google Tasks.
                    </p>
                    <div className="relative flex flex-wrap items-center justify-center gap-4">
                        <a href="http://localhost:8000/auth/gmail" className="rounded-full bg-blue-600 px-6 py-3 text-sm font-semibold text-white shadow-sm hover:bg-blue-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 transition-colors">
                            Connect Gmail & launch
                        </a>
                        <Link to="/login" className="rounded-full bg-white/10 px-6 py-3 text-sm font-semibold text-white shadow-sm hover:bg-white/20 transition-colors">
                            I already have access
                        </Link>
                    </div>
                </section>

                <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
                    {onboardingHighlights.map((item) => (
                        <div key={item.title} className="rounded-2xl bg-white p-6 shadow-lg ring-1 ring-gray-900/5 dark:bg-gray-800 dark:ring-white/10">
                            <span className="inline-flex items-center rounded-full bg-blue-50 px-2 py-1 text-xs font-medium text-blue-700 ring-1 ring-inset ring-blue-700/10 dark:bg-blue-400/10 dark:text-blue-400 dark:ring-blue-400/30">
                                Step
                            </span>
                            <h3 className="mt-4 mb-2 text-lg font-semibold text-gray-900 dark:text-white">{item.title}</h3>
                            <p className="text-gray-600 dark:text-gray-400">{item.description}</p>
                        </div>
                    ))}
                </div>
            </div>
        );
    }

    return (
        <div className="flex flex-col gap-8 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
            <section className="relative overflow-hidden rounded-2xl bg-gray-900 px-6 py-12 text-center shadow-xl sm:px-12 sm:py-16">
                <div className="absolute inset-0 bg-gradient-to-br from-blue-600/20 to-purple-600/20" />
                <span className="relative inline-flex items-center rounded-full bg-gray-800/50 px-3 py-1 text-sm font-medium text-gray-300 ring-1 ring-inset ring-gray-700/50 mb-6">
                    Signed in as {user.username}
                </span>
                <h1 className="relative text-3xl font-bold tracking-tight text-white sm:text-5xl mb-6">
                    Focus on the work that matters - Inbotic owns the rest.
                </h1>
                <p className="relative mx-auto max-w-2xl text-lg leading-8 text-gray-300 mb-10">
                    Monitor extraction accuracy, trigger new runs and keep an eye on the health of your Gmail + Google Tasks bridge.
                </p>

                {data?.needs_reauth && (
                    <div className="mb-8 mx-auto max-w-lg bg-red-500/20 border border-red-500/50 rounded-lg p-4 backdrop-blur-sm">
                        <div className="flex flex-col items-center gap-3">
                            <p className="text-white font-medium flex items-center gap-2">
                                <span className="text-xl">⚠️</span>
                                {data.error || "Your Google connection has expired."}
                            </p>
                            <a
                                href="http://localhost:8000/auth/gmail"
                                className="rounded-full bg-red-600 px-6 py-2 text-sm font-semibold text-white shadow-sm hover:bg-red-500 transition-colors"
                            >
                                Reconnect Gmail
                            </a>
                        </div>
                    </div>
                )}

                <div className="relative flex flex-wrap items-center justify-center gap-4">

                    <button
                        onClick={() => document.querySelector('form[action$="/process-emails"]').requestSubmit()}
                        className="rounded-full bg-blue-600 px-6 py-3 text-sm font-semibold text-white shadow-sm hover:bg-blue-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 transition-colors"
                    >
                        Run extraction now
                    </button>
                    <Link to="/emails" className="rounded-full bg-white/10 px-6 py-3 text-sm font-semibold text-white shadow-sm hover:bg-white/20 transition-colors">
                        Review recent output
                    </Link>
                </div>
            </section>

            <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
                <div className="rounded-2xl bg-white p-6 shadow-lg ring-1 ring-gray-900/5 dark:bg-gray-800 dark:ring-white/10">
                    <h3 className="text-sm font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-2">Inbox agent tasks</h3>
                    <div className="text-4xl font-bold text-blue-600 dark:text-blue-400">{data?.ia_tasks_count || 0}</div>
                    <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">Tracked inside "Inbotic - {user.username}". Updated every sync.</p>
                </div>
                <div className="rounded-2xl bg-white p-6 shadow-lg ring-1 ring-gray-900/5 dark:bg-gray-800 dark:ring-white/10">
                    <h3 className="text-sm font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-2">Status</h3>
                    <div className="text-2xl font-bold text-green-600 dark:text-green-400">Connected</div>
                    <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">Gmail + Google Tasks credentials are active.</p>
                </div>
                <div className="rounded-2xl bg-white p-6 shadow-lg ring-1 ring-gray-900/5 dark:bg-gray-800 dark:ring-white/10">
                    <h3 className="text-sm font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-2">Account</h3>
                    <div className="text-2xl font-bold text-purple-600 dark:text-purple-400 truncate">{user.username}</div>
                    <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">Multi-user ready. Share access securely.</p>
                </div>
            </div>

            {message && (
                <div className={`rounded-md p-4 mb-6 flex items-center justify-between ${message.type === 'success' ? 'bg-green-50 text-green-700 border border-green-200 dark:bg-green-900/20 dark:border-green-800 dark:text-green-200' : 'bg-red-50 text-red-700 border border-red-200 dark:bg-red-900/20 dark:border-red-800 dark:text-red-200'}`}>
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

            <section className="rounded-2xl bg-white p-6 shadow-lg ring-1 ring-gray-900/5 dark:bg-gray-800 dark:ring-white/10">
                <div className="flex items-center justify-between mb-6">
                    <div>
                        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Process your inbox</h3>
                        <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                            Tune the extraction window and let Inbotic convert deadlines, commitments and tasks in one pass.
                        </p>
                    </div>
                    <span className="inline-flex items-center rounded-full bg-green-50 px-2 py-1 text-xs font-medium text-green-700 ring-1 ring-inset ring-green-600/20 dark:bg-green-400/10 dark:text-green-400 dark:ring-green-400/30">
                        Live
                    </span>
                </div>
                <form onSubmit={handleProcessEmails} className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-5 items-end">
                    <div>
                        <label className="block text-sm font-medium leading-6 text-gray-900 dark:text-white mb-2" htmlFor="days_back">Days back</label>
                        <input
                            className="block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-blue-600 sm:text-sm sm:leading-6 dark:bg-white/5 dark:text-white dark:ring-white/10 dark:focus:ring-blue-500"
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
                            className="block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-blue-600 sm:text-sm sm:leading-6 dark:bg-white/5 dark:text-white dark:ring-white/10 dark:focus:ring-blue-500"
                            id="max_emails"
                            type="number"
                            name="max_emails"
                            defaultValue="10"
                            min="1"
                            max="50"
                        />
                    </div>
                    <div>
                        <label className="block text-sm font-medium leading-6 text-gray-900 dark:text-white mb-2" htmlFor="pre_reminder_days">Pre-reminder days</label>
                        <input
                            className="block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-blue-600 sm:text-sm sm:leading-6 dark:bg-white/5 dark:text-white dark:ring-white/10 dark:focus:ring-blue-500"
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
                        <label className="block text-sm font-medium leading-6 text-gray-900 dark:text-white mb-2" htmlFor="max_days_ahead">Max days ahead</label>
                        <input
                            className="block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-blue-600 sm:text-sm sm:leading-6 dark:bg-white/5 dark:text-white dark:ring-white/10 dark:focus:ring-blue-500"
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
                        <button
                            type="submit"
                            disabled={processing}
                            className="w-full rounded-md bg-blue-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-blue-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 transition-colors disabled:opacity-50"
                        >
                            {processing ? 'Processing...' : 'Process emails'}
                        </button>
                    </div>
                </form>
            </section>

            {/* Chat Section - Full Width */}
            <section className="rounded-2xl bg-white p-6 shadow-lg ring-1 ring-gray-900/5 dark:bg-gray-800 dark:ring-white/10">
                <div className="flex items-center justify-between mb-4">
                    <div>
                        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Chat with Inbotic</h3>
                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                            Try: "mark task X as done" • "search emails about hackathon" • "what's due this week?"
                        </p>
                    </div>
                    <div className="flex items-center gap-2">
                        <button
                            onClick={() => {
                                setChatHistory([]);
                                sessionStorage.removeItem('inbotic_chat_history');
                            }}
                            className="text-xs text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
                        >
                            Clear
                        </button>
                        <span className="inline-flex items-center rounded-full bg-purple-50 px-2 py-1 text-xs font-medium text-purple-700 ring-1 ring-inset ring-purple-700/10 dark:bg-purple-400/10 dark:text-purple-400 dark:ring-purple-400/30">
                            AI Assistant
                        </span>
                    </div>
                </div>
                <div className="h-72 overflow-y-auto rounded-lg border border-gray-200 bg-gray-50 p-4 text-sm text-gray-600 dark:border-gray-700 dark:bg-gray-900/50 dark:text-gray-400 mb-4 space-y-3">
                    {chatHistory.length === 0 ? (
                        <div className="text-center py-8 text-gray-400">
                            <p className="text-2xl mb-2">💬</p>
                            <p>Ask anything about your emails and tasks!</p>
                        </div>
                    ) : (
                        chatHistory.map((msg, idx) => (
                            <div key={idx} className={`p-3 rounded-lg ${msg.role === 'user' ? 'bg-blue-100 dark:bg-blue-900/30 ml-auto max-w-[85%]' : 'bg-gray-200 dark:bg-gray-700 mr-auto max-w-[85%]'}`}>
                                <p className="text-xs font-semibold mb-1 opacity-70">{msg.role === 'user' ? 'You' : 'Inbotic'}</p>
                                <p className="whitespace-pre-wrap">{msg.content}</p>
                            </div>
                        ))
                    )}
                    {chatLoading && (
                        <div className="bg-gray-200 dark:bg-gray-700 mr-auto max-w-[85%] p-3 rounded-lg">
                            <p className="animate-pulse">Thinking...</p>
                        </div>
                    )}
                    <div ref={chatEndRef} />
                </div>
                <form onSubmit={handleChatSubmit} className="flex gap-2" autoComplete="off">
                    <input
                        name="chat_message_input_v1"
                        value={chatInput}
                        onChange={(e) => setChatInput(e.target.value)}
                        type="text"
                        autoComplete="off"
                        className="block w-full rounded-md border-0 py-2.5 px-4 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-blue-600 sm:text-sm dark:bg-white/5 dark:text-white dark:ring-white/10 dark:focus:ring-blue-500"
                        placeholder="Ask about tasks, search emails, or give commands..."
                        required
                        disabled={chatLoading}
                    />
                    <button
                        type="submit"
                        disabled={chatLoading}
                        className="rounded-md bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-blue-500 transition-colors disabled:opacity-50"
                    >
                        Send
                    </button>
                </form>
            </section>

            <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
                {quickActions.map((action) => {
                    // Determine badge count
                    let badgeCount = 0;
                    let badgeColor = 'bg-blue-500';
                    if (action.to === '/emails' && data?.emails_this_week) {
                        badgeCount = data.emails_this_week;
                        badgeColor = 'bg-green-500';
                    } else if (action.to === '/tasks' && data?.pending_tasks) {
                        badgeCount = data.pending_tasks;
                        badgeColor = 'bg-orange-500';
                    }

                    return (
                        <Link key={action.to} to={action.to} className="group relative flex flex-col gap-2 rounded-2xl bg-white p-6 shadow-lg ring-1 ring-gray-900/5 transition-all hover:-translate-y-1 hover:shadow-xl dark:bg-gray-800 dark:ring-white/10">
                            {badgeCount > 0 && (
                                <span className={`absolute -top-2 -right-2 flex h-6 w-6 items-center justify-center rounded-full ${badgeColor} text-xs font-bold text-white shadow-lg`}>
                                    {badgeCount > 99 ? '99+' : badgeCount}
                                </span>
                            )}
                            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-blue-50 text-2xl text-blue-600 dark:bg-blue-900/20 dark:text-blue-400" aria-hidden>{action.icon}</div>
                            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">{action.title}</h3>
                            <p className="text-sm text-gray-600 dark:text-gray-400">{action.copy}</p>
                        </Link>
                    );
                })}
            </div>
        </div >
    );
};

export default Home;
