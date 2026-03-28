import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
import Emails from './pages/Emails';
import Tasks from './pages/Tasks';
import Profile from './pages/Profile';
import Home from './pages/Home';
import Layout from './components/Layout';
import ThemeToggle from './components/ThemeToggle';

function App() {
  return (
    <Router>
      <ThemeProvider>
        <AuthProvider>
          <Layout>
            <ThemeToggle />
            <Routes>
              <Route path="/login" element={<Home />} />
              <Route path="/register" element={<Home />} />
              <Route path="/forgot-password" element={<Home />} />
              <Route path="/emails" element={<Emails />} />
              <Route path="/tasks" element={<Tasks />} />

              <Route path="/" element={<Home />} />
              <Route path="/profile" element={<Profile />} />
            </Routes>
          </Layout>
        </AuthProvider>
      </ThemeProvider>
    </Router>
  );
}

export default App;
