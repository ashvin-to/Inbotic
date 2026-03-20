import React, { useEffect, useState } from 'react';
import Layout from '../components/Layout';
import api from '../lib/api';
import { Link } from 'react-router-dom';

const Tasks = () => {
    const [taskLists, setTaskLists] = useState([]);
    const [tasks, setTasks] = useState([]);
    const [loading, setLoading] = useState(true);
    const [editingTask, setEditingTask] = useState(null);

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

    const getTasksForList = (listTitle) => {
        return tasks.filter(task => task.list_name === listTitle);
    };

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
        <div className="max-w-7xl mx-auto py-6 px-4 sm:px-6 lg:px-8">
            <div className="mb-6 flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900 dark:text-white">My Tasks</h1>
                    <p className="text-gray-600 dark:text-gray-400">Tasks created from your emails</p>
                </div>
                <div className="flex space-x-2">
                    <button
                        onClick={() => fetchTasks(true)}
                        className="inline-flex items-center bg-gray-200 text-gray-700 dark:bg-gray-700 dark:text-gray-200 px-4 py-2 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
                        title="Sync with Google Tasks"
                    >
                        <svg className="w-5 h-5 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>
                        Refresh
                    </button>
                    <Link to="/tasks/review" className="inline-flex items-center bg-purple-600 text-white px-4 py-2 rounded-lg hover:bg-purple-700 transition-colors">
                        AI Review
                    </Link>
                </div>
            </div>

            {loading ? (
                <div className="text-center py-8 text-gray-600 dark:text-gray-400">Loading...</div>
            ) : taskLists.length > 0 ? (
                <div className="space-y-6">
                    {taskLists.map((taskList) => (
                        <div key={taskList.id} className="bg-white dark:bg-gray-800 rounded-lg shadow-lg transition-colors duration-300">
                            <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
                                <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-200">{taskList.title}</h3>
                            </div>
                            <div className="p-6">
                                {getTasksForList(taskList.title).length > 0 ? (
                                    <div className="space-y-3">
                                        {getTasksForList(taskList.title).map((task) => (
                                            <div key={task.id} className="flex items-start justify-between p-4 border border-gray-200 dark:border-gray-700 rounded-lg bg-gray-50 dark:bg-gray-700/50 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors">
                                                <div className="flex-1 pr-4">
                                                    <div className="flex items-center mb-1">
                                                        <input
                                                            type="checkbox"
                                                            checked={task.status === 'completed'}
                                                            readOnly
                                                            className="h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-gray-300 rounded mr-3"
                                                        />
                                                        <h4 className={`font-medium text-gray-900 dark:text-white ${task.status === 'completed' ? 'line-through text-gray-500 dark:text-gray-500' : ''}`}>
                                                            {task.title}
                                                        </h4>
                                                    </div>
                                                    {task.notes && (
                                                        <p className="text-sm text-gray-600 dark:text-gray-400 ml-7 mb-1 whitespace-pre-wrap">
                                                            {task.notes.length > 150 ? `${task.notes.substring(0, 150)}...` : task.notes}
                                                        </p>
                                                    )}
                                                    <div className="ml-7 flex items-center space-x-4 text-xs text-gray-500 dark:text-gray-500">
                                                        {task.due && (
                                                            <span className="flex items-center text-red-600 dark:text-red-400">
                                                                <svg className="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"></path></svg>
                                                                {task.due.substring(0, 10)}
                                                            </span>
                                                        )}
                                                        <span>Updated: {task.updated ? task.updated.substring(0, 10) : 'Unknown'}</span>
                                                    </div>
                                                </div>
                                                <div className="flex items-center space-x-2">
                                                    <button
                                                        onClick={() => handleEditClick(task)}
                                                        className="p-1 text-gray-400 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors"
                                                        title="Edit"
                                                    >
                                                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path></svg>
                                                    </button>
                                                    <button
                                                        onClick={() => handleDelete(task.id, task.list_id)}
                                                        className="p-1 text-gray-400 hover:text-red-600 dark:hover:text-red-400 transition-colors"
                                                        title="Delete"
                                                    >
                                                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                                                    </button>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                ) : (
                                    <p className="text-gray-500 dark:text-gray-400 text-center py-4">No tasks in this list</p>
                                )}
                            </div>
                        </div>
                    ))}
                </div>
            ) : (
                <div className="bg-white dark:bg-gray-800 p-8 rounded-lg shadow-lg text-center transition-colors duration-300">
                    <div className="text-6xl mb-4"></div>
                    <h3 className="text-xl font-semibold text-gray-800 dark:text-gray-200 mb-2">No Task Lists Found</h3>
                    <p className="text-gray-600 dark:text-gray-400 mb-4">Process some emails to create task lists</p>
                    <Link to="/" className="inline-block bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 transition-colors">
                        Process Emails
                    </Link>
                </div>
            )}

            {/* Edit Modal */}
            {editingTask && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
                    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full p-6 transition-colors duration-300">
                        <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-4">Edit Task</h3>
                        <form onSubmit={handleSaveEdit}>
                            <div className="mb-4">
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Title</label>
                                <input
                                    type="text"
                                    value={editingTask.title}
                                    onChange={(e) => setEditingTask({ ...editingTask, title: e.target.value })}
                                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white"
                                    required
                                />
                            </div>
                            <div className="mb-4">
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Notes</label>
                                <textarea
                                    value={editingTask.notes || ''}
                                    onChange={(e) => setEditingTask({ ...editingTask, notes: e.target.value })}
                                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white"
                                    rows="4"
                                />
                            </div>
                            <div className="mb-4">
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Due Date</label>
                                <input
                                    type="date"
                                    value={editingTask.due ? editingTask.due.substring(0, 10) : ''}
                                    onChange={(e) => setEditingTask({ ...editingTask, due: e.target.value })}
                                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white"
                                />
                            </div>
                            <div className="mb-6">
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Status</label>
                                <select
                                    value={editingTask.status}
                                    onChange={(e) => setEditingTask({ ...editingTask, status: e.target.value })}
                                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white"
                                >
                                    <option value="needsAction">Needs Action</option>
                                    <option value="completed">Completed</option>
                                </select>
                            </div>
                            <div className="flex justify-end space-x-3">
                                <button
                                    type="button"
                                    onClick={() => setEditingTask(null)}
                                    className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-md text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    className="px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
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
