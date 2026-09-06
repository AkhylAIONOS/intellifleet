import React from 'react';
import { useNavigate } from 'react-router-dom';
import "../pages/Auth.css";

interface AuthLayoutProps {
    children: React.ReactNode;
    type: 'signin' | 'signup' | 'demo';
}

export const AuthLayout: React.FC<AuthLayoutProps> = ({ type, children }) => {
    const navigate = useNavigate();

    return (
        <div className="auth-container">
            {/* Left Panel — Branding & Features */}
            <div className="auth-left-panel">
                <div className="auth-left-inner">
                    {/* Logo */}
                    <div className="brand-logo">
                        <div className="brand-logo-icon">
                            <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
                                <rect width="28" height="28" rx="8" fill="white" fillOpacity="0.15" />
                                <path d="M4 18L8 10L13 16L17 12L24 18" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                                <circle cx="21" cy="10" r="3" fill="#60efb0" />
                            </svg>
                        </div>
                        <span className="brand-logo-text">UniFleet</span>
                    </div>

                    {/* Hero copy */}
                    <div className="brand-hero">
                        <h1 className="brand-title">
                            AI-Powered Fleet<br />
                            <span className="brand-title-accent">Intelligence</span>
                        </h1>
                        <p className="brand-subtitle">
                            The autonomous logistics platform that thinks ahead — optimizing routes, predicting disruptions, and manages your entire fleet.
                        </p>
                    </div>

                    {/* Stats row */}
                    <div className="brand-stats">
                        <div className="stat-item">
                            <span className="stat-number">40%</span>
                            <span className="stat-label">Cost Reduction</span>
                        </div>
                        <div className="stat-divider" />
                        <div className="stat-item">
                            <span className="stat-number">2×</span>
                            <span className="stat-label">Improved Planning</span>
                        </div>
                        <div className="stat-divider" />
                        <div className="stat-item">
                            <span className="stat-number">35%</span>
                            <span className="stat-label">Delay Improvements</span>
                        </div>
                    </div>

                    {/* Feature cards */}
                    <div className="feature-list">
                        <div className="feature-item">
                            <div className="feature-icon">
                                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                    <circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" />
                                </svg>
                            </div>
                            <div className="feature-text">
                                <span className="feature-title">Network Creation</span>
                                <span className="feature-desc">Create your network and update it anytime</span>
                            </div>
                        </div>
                        <div className="feature-item">
                            <div className="feature-icon">
                                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                    <path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96-.44L4.5 7.5A2.5 2.5 0 0 1 7 5h.5" /><path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96-.44l2.54-11.56A2.5 2.5 0 0 0 17 5h-.5" />
                                </svg>
                            </div>
                            <div className="feature-text">
                                <span className="feature-title">Autonomous AI Route Agent</span>
                                <span className="feature-desc">Chat-driven AI agent that performs warehouse rebalancing, Vehicle Assignment and much more</span>
                            </div>
                        </div>
                        <div className="feature-item">
                            <div className="feature-icon">
                                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
                                </svg>
                            </div>
                            <div className="feature-text">
                                <span className="feature-title">Visibility Twin</span>
                                <span className="feature-desc">Watch every action being performed on map</span>
                            </div>
                        </div>
                        <div className="feature-item">
                            <div className="feature-icon">
                                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                    <rect x="3" y="3" width="18" height="18" rx="2" /><path d="M3 9h18M9 21V9" />
                                </svg>
                            </div>
                            <div className="feature-text">
                                <span className="feature-title">Advanced Analytics Dashboard</span>
                                <span className="feature-desc">Cost, performance & warehouse metrics at a glance</span>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Decorative background elements */}
                <div className="bg-orb bg-orb-1" />
                <div className="bg-orb bg-orb-2" />
                <div className="bg-grid" />
            </div>

            {/* Right Panel — Auth Form */}
            <div className="auth-right-panel">
                <div className={`auth-right-inner ${type === 'demo' ? 'demo-welcome' : ''}`}>
                    {/* Mobile logo (hidden on desktop) */}
                    <div className="mobile-logo">
                        <div className="brand-logo-icon small">
                            <svg width="20" height="20" viewBox="0 0 28 28" fill="none">
                                <rect width="28" height="28" rx="8" fill="#6366f1" fillOpacity="0.15" />
                                <path d="M4 18L8 10L13 16L17 12L24 18" stroke="#6366f1" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                                <circle cx="21" cy="10" r="3" fill="#60efb0" />
                            </svg>
                        </div>
                        <span style={{ fontWeight: 700, fontSize: 18, color: '#1e1b4b' }}>UniFleet</span>
                    </div>

                    {/* Heading */}
                    <div className="form-heading">
                        <h2 className="form-title">
                            {type === 'demo' ? 'Welcome to UniFleet' : type === 'signin' ? 'Welcome back' : 'Get started free'}
                        </h2>
                        <p className="form-subtitle">
                            {type === 'demo' ? 'AI-Powered Supply-Chain Planning' : type === 'signin'
                                ? 'Sign in to your fleet management dashboard'
                                : 'Create your account and start managing smarter'}
                        </p>
                    </div>

                    {/* Tab switcher */}
                    {type !== 'demo' && <div className="auth-tabs">
                        <button
                            className={`auth-tab ${type === 'signin' ? 'active' : ''}`}
                            onClick={() => navigate('/login')}
                        >
                            Sign In
                        </button>
                        <button
                            className={`auth-tab ${type === 'signup' ? 'active' : ''}`}
                            onClick={() => navigate('/signup')}
                        >
                            Sign Up
                        </button>
                        <div className={`auth-tab-indicator ${type === 'signup' ? 'right' : ''}`} />
                    </div>}

                    {/* Form content */}
                    <div className="auth-form-wrapper">
                        {children}
                    </div>

                    {/* Footer */}
                    {type !== 'demo' && <div className="auth-footer">
                        {/* <div className="trust-badges">
                            <span className="trust-badge">🔒 SSL Encrypted</span>
                            <span className="trust-badge">🛡️ SOC 2 Compliant</span>
                            <span className="trust-badge">✦ GDPR Ready</span>
                        </div> */}
                        <p className="auth-footer-text">
                            {type === 'signin' ? (
                                <>Don't have an account? <button className="auth-link" onClick={() => navigate('/signup')}>Sign up free</button></>
                            ) : (
                                <>Already have an account? <button className="auth-link" onClick={() => navigate('/login')}>Sign in</button></>
                            )}
                        </p>
                    </div>}
                </div>
            </div>
        </div>
    );
};
