import React, { useEffect, useMemo, useState } from 'react';
import api from '../lib/api';
import DOMPurify from 'dompurify';

const formatDate = (value) => {
    if (!value) return 'Unknown date';
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
        return value;
    }
    return parsed.toLocaleString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
};

const formatSender = (value) => {
    if (!value) return 'Unknown sender';
    if (!value.includes('<')) return value;
    try {
        const [name] = value.split('<');
        return name.trim();
    } catch {
        return value;
    }
};

const Emails = () => {
    const [emails, setEmails] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [selectedEmailId, setSelectedEmailId] = useState(null);
    const [daysBack, setDaysBack] = useState(7);

    const fetchEmails = async (options = {}) => {
        const { skipLoading = false, windowSize = daysBack } = options;
        if (!skipLoading) {
            setLoading(true);
        }
        try {
            const response = await api.get('/emails', {
                params: { days_back: windowSize }
            });
            const data = response.data.emails || [];
            setEmails(data);
            setError('');
            setSelectedEmailId(prev => {
                if (prev && data.some(email => email.id === prev)) {
                    return prev;
                }
                return data[0]?.id || null;
            });
        } catch (err) {
            console.error('Failed to load emails', err);
            setError(err.response?.data?.error || 'Failed to load emails');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchEmails();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const selectedEmail = useMemo(
        () => emails.find(email => email.id === selectedEmailId) || null,
        [emails, selectedEmailId]
    );

    const handleRefresh = () => {
        fetchEmails({ windowSize: daysBack });
    };

    const handleWindowChange = (event) => {
        const value = Number(event.target.value);
        setDaysBack(value);
        fetchEmails({ windowSize: value });
    };

    return (
        <div className="max-w-7xl mx-auto py-6 px-4 sm:px-6 lg:px-8">
            <div className="flex flex-wrap items-center justify-between gap-4 mb-8">
                <div>
                    <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">Recent Emails</h1>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                        Synced from Gmail with the latest AI extraction context.
                    </p>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                    <label className="text-sm text-gray-600 dark:text-gray-300 flex items-center gap-2">
                        Window
                        <select
                            className="rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-1 text-sm"
                            value={daysBack}
                            onChange={handleWindowChange}
                        >
                            {[2, 7, 14, 30].map(value => (
                                <option key={value} value={value}>{value} days</option>
                            ))}
                        </select>
                    </label>
                    <button
                        onClick={handleRefresh}
                        className="inline-flex items-center gap-2 rounded-full bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow hover:bg-blue-500 transition"
                        disabled={loading}
                    >
                        {loading ? (
                            <>
                                <span className="h-3 w-3 animate-spin rounded-full border-2 border-white border-t-transparent" />
                                Refreshing…
                            </>
                        ) : (
                            'Refresh'
                        )}
                    </button>
                </div>
            </div>

            {error && (
                <div className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-500/40 dark:bg-red-900/20 dark:text-red-200">
                    {error}
                </div>
            )}

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
                <div className="lg:col-span-1">
                    <div className="rounded-2xl bg-white dark:bg-gray-800 shadow divide-y divide-gray-100 dark:divide-gray-700">
                        {loading && emails.length === 0 ? (
                            <div className="p-6 space-y-4 animate-pulse">
                                <div className="h-4 w-3/4 rounded bg-gray-200 dark:bg-gray-700" />
                                <div className="h-4 w-1/2 rounded bg-gray-200 dark:bg-gray-700" />
                                <div className="h-4 w-2/3 rounded bg-gray-200 dark:bg-gray-700" />
                            </div>
                        ) : emails.length === 0 ? (
                            <div className="p-6 text-center text-gray-500 dark:text-gray-400">
                                No emails found for the selected window.
                            </div>
                        ) : (
                            emails.map(email => (
                                <button
                                    key={email.id}
                                    onClick={() => setSelectedEmailId(email.id)}
                                    className={`w-full text-left px-5 py-4 transition ${selectedEmailId === email.id
                                        ? 'bg-blue-50 dark:bg-blue-900/20'
                                        : 'hover:bg-gray-50 dark:hover:bg-gray-800/80'
                                        }`}
                                >
                                    <div className="flex items-start justify-between gap-3">
                                        <div>
                                            <p className="text-sm font-semibold text-gray-900 dark:text-gray-100 line-clamp-2">
                                                {email.subject || 'No subject'}
                                            </p>
                                            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                                                {formatSender(email.sender)}
                                            </p>
                                        </div>
                                        <span className="text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap">
                                            {formatDate(email.date)}
                                        </span>
                                    </div>
                                    {email.snippet && (
                                        <p className="mt-2 text-xs text-gray-500 dark:text-gray-400 line-clamp-2">
                                            {email.snippet}
                                        </p>
                                    )}
                                </button>
                            ))
                        )}
                    </div>
                </div>

                <div className="lg:col-span-2">
                    <div className="rounded-2xl bg-white dark:bg-gray-800 shadow min-h-[400px] p-6">
                        {selectedEmail ? (
                            <>
                                <div className="border-b border-gray-100 pb-4 dark:border-gray-700">
                                    <div className="flex flex-wrap items-center justify-between gap-3">
                                        <div>
                                            <p className="text-xs uppercase tracking-widest text-gray-400 dark:text-gray-500">
                                                Subject
                                            </p>
                                            <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
                                                {selectedEmail.subject || 'No subject'}
                                            </h2>
                                        </div>
                                        <span className="rounded-full bg-gray-100 px-3 py-1 text-xs font-medium text-gray-600 dark:bg-gray-700 dark:text-gray-200">
                                            {formatDate(selectedEmail.date)}
                                        </span>
                                    </div>
                                    <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
                                        From {selectedEmail.sender || 'Unknown sender'}
                                    </p>
                                </div>
                                <div className="mt-6 space-y-6">
                                    {selectedEmail.extracted_data && (
                                        <div className="rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800 dark:border-blue-500/40 dark:bg-blue-900/20 dark:text-blue-100">
                                            <pre className="whitespace-pre-wrap text-xs">
                                                {JSON.stringify(selectedEmail.extracted_data, null, 2)}
                                            </pre>
                                        </div>
                                    )}
                                    <div className="overflow-auto max-h-[600px]">
                                        {selectedEmail.body ? (
                                            <div
                                                className="email-content text-sm text-gray-800 dark:text-gray-200"
                                                dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(selectedEmail.body) }}
                                            />
                                        ) : (
                                            <p className="text-sm text-gray-600 dark:text-gray-300 whitespace-pre-wrap leading-relaxed">
                                                {selectedEmail.snippet || 'No content available.'}
                                            </p>
                                        )}
                                    </div>
                                </div>
                            </>
                        ) : (
                            <div className="flex h-full items-center justify-center text-gray-500 dark:text-gray-400">
                                Select an email to preview its details.
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};

export default Emails;
