import React from 'react';

const Footer = () => {
    return (
        <footer className="mt-auto transition-colors duration-300 border-t border-black/10 dark:border-white/10">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-7">
                <div className="text-center text-gray-600 dark:text-gray-300 text-sm">
                    <p className="font-semibold tracking-wide">&copy; {new Date().getFullYear()} Inbotic</p>
                    <p className="mt-1">Gmail-first productivity autopilot for focused execution.</p>
                </div>
            </div>
        </footer>
    );
};

export default Footer;
