import React from 'react';

const Footer = () => {
    return (
        <footer className="mt-auto transition-colors duration-300">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
                <div className="text-center text-gray-500 dark:text-gray-400">
                    <p>&copy; {new Date().getFullYear()} Inbotic. Gmail-first productivity autopilot</p>
                </div>
            </div>
        </footer>
    );
};

export default Footer;
