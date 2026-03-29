import React, { useEffect, useState } from 'react';
import api from '../lib/api';
import { Link } from 'react-router-dom';

const Tasks = () => {
    const [taskLists, setTaskLists] = useState([]);
    const [tasks, setTasks] = useState([]);
    const [loading, setLoading] = useState(true);
    const [editingTask, setEditingTask] = useState(null);
    const [query, setQuery] = useState('');
    const [statusFilter, setStatusFilter] = useState('all');
    const [listFilter, setListFilter] = useState('all');

    const fetchTasks = async (refresh = false) => {
        try {
            setLoading(true);
            const response = await api.get(`/tasks${refresh ? '?refresh=true' : ''}`);
            setTaskLists(response.data.task_lists || []);
            setTasks(response.data.tasks || []);
        } catch (error) {
            console.error("Error fetching tasks", error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchTasks();
    }, []);

    const parseDate = (raw) => {
        if (!raw) return null;
        const value = String(raw).substring(0, 10);
        const date = new Date(`${value}T00:00:00`);
        return Number.isNaN(date.getTime()) ? null : date;
    };

    const parseDateTime = (raw) => {
        if (!raw) return null;
        const value = String(raw);
        const normalized = value.endsWith('Z') ? value : `${value}Z`;
        const dt = new Date(normalized);
        return Number.isNaN(dt.getTime()) ? null : dt;
    };

    const formatDate = (raw) => {
        const date = parseDate(raw);
        if (!date) return 'No due date';
        return date.toLocaleDateString(undefined, {
            month: 'short',
            day: 'numeric',
            year: 'numeric',
        });
    };

    const formatDue = (raw) => {
        const date = parseDate(raw);
        if (!date) return 'No due date';
        const dt = parseDateTime(raw);
        const dateText = date.toLocaleDateString(undefined, {
            month: 'short',
            day: 'numeric',
            year: 'numeric',
        });
        if (!dt) return dateText;
        const hh = dt.getUTCHours();
        const mm = dt.getUTCMinutes();
        if (hh === 0 && mm === 0) return dateText;
        const timeText = `${String(hh).padStart(2, '0')}:${String(mm).padStart(2, '0')} UTC`;
        return `${dateText}, ${timeText}`;
    };

    const getTasksForList = (listTitle, source = tasks) => {
        return source.filter(task => task.list_name === listTitle);
    };

    const normalizedQuery = query.trim().toLowerCase();

    const visibleTasks = tasks.filter((task) => {
        if (listFilter !== 'all' && task.list_name !== listFilter) {
            return false;
        }

        if (statusFilter !== 'all' && task.status !== statusFilter) {
            return false;
        }

        if (!normalizedQuery) {
            return true;
        }

        const haystack = `${task.title || ''} ${task.notes || ''} ${task.list_name || ''}`.toLowerCase();
        return haystack.includes(normalizedQuery);
    });

    const activeTasks = visibleTasks.filter((task) => task.status !== 'completed');
    const completedTasks = visibleTasks.filter((task) => task.status === 'completed');
    const dueSoonCount = visibleTasks.filter((task) => {
        if (task.status === 'completed') return false;
        const due = parseDate(task.due);
        if (!due) return false;
        const now = new Date();
        now.setHours(0, 0, 0, 0);
        const diffDays = Math.floor((due - now) / (1000 * 60 * 60 * 24));
        return diffDays >= 0 && diffDays <= 3;
    }).length;

    const listOptions = taskLists.map((list) => list.title);

    const metricCards = [
        {
            label: 'Visible Tasks',
            value: visibleTasks.length,
            tone: 'from-emerald-500 to-teal-500',
        },
        {
            label: 'Needs Action',
            value: activeTasks.length,
            tone: 'from-orange-500 to-amber-500',
        },
        {
            label: 'Due Soon (3d)',
            value: dueSoonCount,
            tone: 'from-sky-500 to-cyan-500',
        },
        {
            label: 'Completed',
            value: completedTasks.length,
            tone: 'from-slate-500 to-gray-500',
        },
    ];

    const handleDelete = async (taskId, listId) => {
        if (!window.confirm("Are you sure you want to delete this task?")) return;
        try {
            await api.delete(`/tasks/${taskId}?list_id=${listId}`);
            setTasks(tasks.filter(t => t.id !== taskId));
        } catch (error) {
            console.error("Failed to delete task", error);
            alert("Failed to delete task");
        }
    };

    const handleEditClick = (task) => {
        setEditingTask({ ...task });
    };

    const handleSaveEdit = async (e) => {
        e.preventDefault();
        try {
            const { id, list_id, title, notes, due, status } = editingTask;
            const response = await api.put(`/tasks/${id}`, {
                list_id, title, notes, due, status
            });
            // Update local state with returned task data
            const updatedTask = response.data.task;
            // Ensure we keep the list_name and list_id which might not be in the response
            updatedTask.list_name = editingTask.list_name;
            updatedTask.list_id = editingTask.list_id;

            setTasks(tasks.map(t => t.id === id ? updatedTask : t));
            setEditingTask(null);
        } catch (error) {
            console.error("Failed to update task", error);
            alert("Failed to update task");
        }
    };

    return (
        <div className="max-w-7xl mx-auto py-7 px-4 sm:px-6 lg:px-8 space-y-6">
            <section className="glass-panel rounded-2xl p-5 sm:p-6">
                <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                        <h1 className="display-title text-3xl font-bold text-gray-900 dark:text-white">Task Manager</h1>
                        <p className="mt-1 text-gray-700 dark:text-gray-300">Monitor deadlines, triage workload, and keep execution clean.</p>
                    </div>
                    <div className="flex items-center gap-2">
                        <button
                            onClick={() => fetchTasks(true)}
                            className="btn-primary !text-sm flex items-center gap-2"
                            title="Sync with Google Tasks"
                        >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>
                            Sync
                        </button>
                    </div>
                </div>

                <div className="mt-5 grid grid-cols-2 lg:grid-cols-4 gap-3">
                    {metricCards.map((card) => (
                        <div key={card.label} className="rounded-xl border border-black/10 dark:border-white/10 bg-white/70 dark:bg-gray-900/45 px-4 py-3">
                            <p className="text-xs font-semibold tracking-wide uppercase text-gray-600 dark:text-gray-400">{card.label}</p>
                            <p className={`mt-2 text-2xl font-bold bg-gradient-to-r ${card.tone} bg-clip-text text-transparent`}>{card.value}</p>
                        </div>
                    ))}
                </div>

                <div className="mt-5 grid md:grid-cols-3 gap-3">
                    <input
                        type="text"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        placeholder="Search by title, notes or list..."
                        className="form-input"
                    />
                    <select
                        value={statusFilter}
                        onChange={(e) => setStatusFilter(e.target.value)}
                        className="form-input"
                    >
                        <option value="all">All statuses</option>
                        <option value="needsAction">Needs action</option>
                        <option value="completed">Completed</option>
                    </select>
                    <select
                        value={listFilter}
                        onChange={(e) => setListFilter(e.target.value)}
                        className="form-input"
                    >
                        <option value="all">All lists</option>
                        {listOptions.map((title) => (
                            <option key={title} value={title}>{title}</option>
                        ))}
                    </select>
                </div>
            </section>

            {loading ? (
                <div className="glass-panel text-center py-10 rounded-2xl text-gray-700 dark:text-gray-300">Loading manager workspace...</div>
            ) : taskLists.length > 0 ? (
                <div className="space-y-6">
                    {taskLists.map((taskList) => (
                        <div key={taskList.id} className="glass-panel rounded-2xl overflow-hidden">
                            <div className="px-6 py-4 border-b border-black/10 dark:border-white/10 flex items-center justify-between">
                                <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">{taskList.title}</h3>
                                <span className="text-xs font-medium px-2 py-1 rounded-full bg-emerald-100 text-emerald-800 dark:bg-emerald-900/45 dark:text-emerald-200">
                                    {getTasksForList(taskList.title, visibleTasks).length} visible
                                </span>
                            </div>
                            <div className="p-6">
                                {getTasksForList(taskList.title, visibleTasks).length > 0 ? (
                                    <div className="space-y-3">
                                        {getTasksForList(taskList.title, visibleTasks).map((task) => (
                                            <div key={task.id} className="flex flex-col md:flex-row md:items-start md:justify-between gap-3 p-4 border border-black/10 dark:border-white/10 rounded-xl bg-white/70 dark:bg-gray-900/40 hover:bg-white/90 dark:hover:bg-gray-900/60 transition-colors">
                                                <div className="flex-1 pr-4">
                                                    <div className="flex items-center mb-1">
                                                        <input
                                                            type="checkbox"
                                                            checked={task.status === 'completed'}
                                                            readOnly
                                                            className="h-4 w-4 text-emerald-600 focus:ring-emerald-500 border-gray-300 rounded mr-3"
                                                        />
                                                        <h4 className={`font-semibold text-gray-900 dark:text-white ${task.status === 'completed' ? 'line-through text-gray-500 dark:text-gray-500' : ''}`}>
                                                            {task.title}
                                                        </h4>
                                                    </div>
                                                    {task.notes && (
                                                        <p className="text-sm text-gray-700 dark:text-gray-300 ml-7 mb-1 whitespace-pre-wrap">
                                                            {task.notes.length > 150 ? `${task.notes.substring(0, 150)}...` : task.notes}
                                                        </p>
                                                    )}
                                                    <div className="ml-7 flex flex-wrap items-center gap-2 text-xs">
                                                        <span className="flex items-center text-orange-700 dark:text-orange-300 bg-orange-100/80 dark:bg-orange-900/30 px-2 py-1 rounded-full">
                                                            <svg className="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"></path></svg>
                                                            {formatDue(task.due)}
                                                        </span>
                                                        <span className="text-gray-500 dark:text-gray-400">Updated: {task.updated ? formatDate(task.updated) : 'Unknown'}</span>
                                                    </div>
                                                </div>
                                                <div className="flex items-center space-x-2">
                                                    <button
                                                        onClick={() => handleEditClick(task)}
                                                        className="p-2 text-gray-500 hover:text-emerald-700 hover:bg-emerald-100 dark:hover:text-emerald-300 dark:hover:bg-emerald-900/40 rounded-lg transition-colors"
                                                        title="Edit"
                                                    >
                                                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path></svg>
                                                    </button>
                                                    <button
                                                        onClick={() => handleDelete(task.id, task.list_id)}
                                                        className="p-2 text-gray-500 hover:text-rose-700 hover:bg-rose-100 dark:hover:text-rose-300 dark:hover:bg-rose-900/40 rounded-lg transition-colors"
                                                        title="Delete"
                                                    >
                                                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                                                    </button>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                ) : (
                                    <p className="text-gray-500 dark:text-gray-400 text-center py-5">No tasks match current filters in this list</p>
                                )}
                            </div>
                        </div>
                    ))}
                </div>
            ) : (
                <div className="glass-panel p-8 rounded-2xl text-center transition-colors duration-300">
                    <div className="text-6xl mb-4"></div>
                    <h3 className="text-xl font-semibold text-gray-800 dark:text-gray-200 mb-2">No Task Lists Found</h3>
                    <p className="text-gray-600 dark:text-gray-400 mb-4">Process some emails to create task lists</p>
                    <Link to="/" className="btn-primary">
                        Process Emails
                    </Link>
                </div>
            )}

            {/* Edit Modal */}
            {editingTask && (
                <div className="fixed inset-0 bg-black/45 flex items-center justify-center p-4 z-50">
                    <div className="glass-panel rounded-2xl shadow-xl max-w-md w-full p-6 transition-colors duration-300">
                        <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-4">Edit Task</h3>
                        <form onSubmit={handleSaveEdit}>
                            <div className="mb-4">
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Title</label>
                                <input
                                    type="text"
                                    value={editingTask.title}
                                    onChange={(e) => setEditingTask({ ...editingTask, title: e.target.value })}
                                    className="form-input"
                                    required
                                />
                            </div>
                            <div className="mb-4">
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Notes</label>
                                <textarea
                                    value={editingTask.notes || ''}
                                    onChange={(e) => setEditingTask({ ...editingTask, notes: e.target.value })}
                                    className="form-input"
                                    rows="4"
                                />
                            </div>
                            <div className="mb-4">
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Due Date</label>
                                <input
                                    type="date"
                                    value={editingTask.due ? editingTask.due.substring(0, 10) : ''}
                                    onChange={(e) => setEditingTask({ ...editingTask, due: e.target.value })}
                                    className="form-input"
                                />
                            </div>
                            <div className="mb-6">
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Status</label>
                                <select
                                    value={editingTask.status}
                                    onChange={(e) => setEditingTask({ ...editingTask, status: e.target.value })}
                                    className="form-input"
                                >
                                    <option value="needsAction">Needs Action</option>
                                    <option value="completed">Completed</option>
                                </select>
                            </div>
                            <div className="flex justify-end space-x-3">
                                <button
                                    type="button"
                                    onClick={() => setEditingTask(null)}
                                    className="btn-secondary !px-4 !py-2 !text-sm"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    className="btn-primary !px-4 !py-2 !text-sm"
                                >
                                    Save Changes
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
};

export default Tasks;
