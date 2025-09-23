import React, { useState, useEffect } from 'react';
import { apiService } from '../services/api';
import Layout from './layout/Layout';
import Loader from './Loader';
import Dashboard from '../pages/Dashboard';

const Auth = () => {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loginForm, setLoginForm] = useState({ username: '', password: '' });
  const [registerForm, setRegisterForm] = useState({ 
    username: '', 
    password: '', 
    email: '', 
    first_name: '', 
    last_name: '' 
  });
  const [showRegister, setShowRegister] = useState(false);
  const [message, setMessage] = useState('');

  // Check authentication status on component mount
  useEffect(() => {
    checkAuth();
  }, []);

  const checkAuth = async () => {
    try {
      const response = await apiService.checkAuth();
      if (response && (response.success === true || response.authenticated === true)) {
        setIsAuthenticated(true);
        setUser(response.user);
      } else {
        setIsAuthenticated(false);
        setUser(null);
      }
    } catch (error) {
      console.error('Auth check failed:', error);
      setIsAuthenticated(false);
      setUser(null);
    } finally {
      setLoading(false);
    }
  };


  const handleLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    setMessage('');

    try {
      const response = await apiService.login(loginForm);
      if (response.success) {
        setIsAuthenticated(true);
        setUser(response.user);
        setMessage('');
        setLoginForm({ username: '', password: '' });
        // No forced redirect - let React Router handle navigation naturally
      } else {
        setMessage(`Login failed: ${response.error}`);
      }
    } catch (error) {
      setMessage('Login failed: Network error');
      console.error('Login error:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async (e) => {
    e.preventDefault();
    setLoading(true);
    setMessage('');

    try {
      const response = await apiService.register(registerForm);
      if (response.success) {
        setMessage('Registration successful! Please login.');
        setRegisterForm({ username: '', password: '', email: '', first_name: '', last_name: '' });
        setShowRegister(false);
      } else {
        setMessage(`Registration failed: ${response.error}`);
      }
    } catch (error) {
      setMessage('Registration failed: Network error');
      console.error('Registration error:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = async () => {
    // Immediately flip UI to login regardless of network
    setIsAuthenticated(false);
    setUser(null);
    setLoading(true);
    // Hard redirect fallback to ensure we leave any protected URL
    try { window.history.pushState({}, '', '/'); } catch (_) {}
    try {
      await apiService.logout();
    } catch (error) {
      console.error('Logout error:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) { return <Loader />; }

  if (isAuthenticated) {
    const path = window.location.pathname;
    let Page = Dashboard;
    if (path.startsWith('/outlets')) {
      try { Page = require('../pages/OutletsPage').default; } catch (_) {}
    } else if (path.startsWith('/machines')) {
      try { Page = require('../pages/MachinesPage').default; } catch (_) {}
    } else if (path.startsWith('/devices')) {
      try { Page = require('../pages/DevicesPage').default; } catch (_) {}
    }
    return (
      <Layout user={user} onLogout={handleLogout}>
        <Page />
      </Layout>
    );
  }

  return (
    <div className="login-container">
      {/* Left Column (Form) */}
      <div className="login-left-column">
        

        {/* Main Content */}
        <main style={{ 
          flexGrow: 1, 
          display: 'flex', 
          flexDirection: 'column', 
          justifyContent: 'center' 
        }}>
          <div style={{ width: '100%', maxWidth: '400px', margin: '0 auto' }}>
            <h1 style={{ fontSize: '24px', fontWeight: '600', marginBottom: '4px', color: '#1e293b' }}>
              {showRegister ? 'Create Account' : 'Welcome back'}
            </h1>
            <p style={{ color: '#64748b', marginBottom: '24px' }}>
              {showRegister ? 'Sign up for a new account' : 'Sign in to your account'}
            </p>

            {message && <div className="alert alert-info" style={{ marginBottom: '16px' }}>{message}</div>}

            {/* Form */}
            {!showRegister ? (
              <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div>
                  <label htmlFor="username" style={{ 
                    display: 'block', 
                    fontSize: '14px', 
                    fontWeight: '500', 
                    color: '#374151', 
                    marginBottom: '6px' 
                  }}>
                    Username
                  </label>
                  <input
                    type="text"
                    id="username"
                    value={loginForm.username}
                    onChange={(e) => setLoginForm({ ...loginForm, username: e.target.value })}
                    required
                    style={{
                      width: '100%',
                      backgroundColor: '#ffffff',
                      color: '#1e293b',
                      borderRadius: '8px',
                      padding: '12px',
                      border: '1px solid #d1d5db',
                      outline: 'none',
                      transition: 'border-color 0.2s ease'
                    }}
                    onFocus={(e) => e.target.style.borderColor = '#667eea'}
                    onBlur={(e) => e.target.style.borderColor = '#d1d5db'}
                  />
                </div>

                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                    <label htmlFor="password" style={{ 
                      display: 'block', 
                      fontSize: '14px', 
                      fontWeight: '500', 
                      color: '#374151', 
                      marginBottom: '6px' 
                    }}>
                      Password
                    </label>
                    <button type="button" style={{ 
                      fontSize: '14px', 
                      color: '#667eea', 
                      textDecoration: 'none',
                      fontWeight: '500',
                      background: 'transparent',
                      border: 'none',
                      cursor: 'pointer'
                    }}>
                      Forgot Password?
                    </button>
                  </div>
                  <input
                    type="password"
                    id="password"
                    value={loginForm.password}
                    onChange={(e) => setLoginForm({ ...loginForm, password: e.target.value })}
                    required
                    style={{
                      width: '100%',
                      backgroundColor: '#ffffff',
                      color: '#1e293b',
                      borderRadius: '8px',
                      padding: '12px',
                      border: '1px solid #d1d5db',
                      outline: 'none',
                      transition: 'border-color 0.2s ease'
                    }}
                    onFocus={(e) => e.target.style.borderColor = '#667eea'}
                    onBlur={(e) => e.target.style.borderColor = '#d1d5db'}
                  />
                </div>

                <button 
                  type="submit" 
                  disabled={loading}
                  style={{
                    width: '100%',
                    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                    color: '#ffffff',
                    fontWeight: '600',
                    border: 'none',
                    padding: '12px',
                    borderRadius: '8px',
                    cursor: 'pointer',
                    opacity: loading ? 0.6 : 1,
                    transition: 'transform 0.2s ease, box-shadow 0.2s ease'
                  }}
                  onMouseEnter={(e) => {
                    if (!loading) {
                      e.target.style.transform = 'translateY(-1px)';
                      e.target.style.boxShadow = '0 4px 12px rgba(102, 126, 234, 0.4)';
                    }
                  }}
                  onMouseLeave={(e) => {
                    e.target.style.transform = 'translateY(0)';
                    e.target.style.boxShadow = 'none';
                  }}
                >
                  {loading ? 'Signing In...' : 'Sign In'}
                </button>
              </form>
            ) : (
              <form onSubmit={handleRegister} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div>
                  <label htmlFor="reg_username" style={{ 
                    display: 'block', 
                    fontSize: '14px', 
                    fontWeight: '500', 
                    color: '#d1d5db', 
                    marginBottom: '6px' 
                  }}>
                    Username
                  </label>
                  <input
                    type="text"
                    id="reg_username"
                    value={registerForm.username}
                    onChange={(e) => setRegisterForm({ ...registerForm, username: e.target.value })}
                    required
                    style={{
                      width: '100%',
                      backgroundColor: '#1c1c1c',
                      color: '#fff',
                      borderRadius: '6px',
                      padding: '12px',
                      border: '1px solid #2b2b2b',
                      outline: 'none'
                    }}
                  />
                </div>

                <div>
                  <label htmlFor="reg_password" style={{ 
                    display: 'block', 
                    fontSize: '14px', 
                    fontWeight: '500', 
                    color: '#d1d5db', 
                    marginBottom: '6px' 
                  }}>
                    Password
                  </label>
                  <input
                    type="password"
                    id="reg_password"
                    value={registerForm.password}
                    onChange={(e) => setRegisterForm({ ...registerForm, password: e.target.value })}
                    required
                    style={{
                      width: '100%',
                      backgroundColor: '#1c1c1c',
                      color: '#fff',
                      borderRadius: '6px',
                      padding: '12px',
                      border: '1px solid #2b2b2b',
                      outline: 'none'
                    }}
                  />
                </div>

                <div>
                  <label htmlFor="reg_email" style={{ 
                    display: 'block', 
                    fontSize: '14px', 
                    fontWeight: '500', 
                    color: '#d1d5db', 
                    marginBottom: '6px' 
                  }}>
                    Email
                  </label>
                  <input
                    type="email"
                    id="reg_email"
                    value={registerForm.email}
                    onChange={(e) => setRegisterForm({ ...registerForm, email: e.target.value })}
                    style={{
                      width: '100%',
                      backgroundColor: '#1c1c1c',
                      color: '#fff',
                      borderRadius: '6px',
                      padding: '12px',
                      border: '1px solid #2b2b2b',
                      outline: 'none'
                    }}
                  />
                </div>

                <div>
                  <label htmlFor="reg_first_name" style={{ 
                    display: 'block', 
                    fontSize: '14px', 
                    fontWeight: '500', 
                    color: '#d1d5db', 
                    marginBottom: '6px' 
                  }}>
                    First Name
                  </label>
                  <input
                    type="text"
                    id="reg_first_name"
                    value={registerForm.first_name}
                    onChange={(e) => setRegisterForm({ ...registerForm, first_name: e.target.value })}
                    style={{
                      width: '100%',
                      backgroundColor: '#1c1c1c',
                      color: '#fff',
                      borderRadius: '6px',
                      padding: '12px',
                      border: '1px solid #2b2b2b',
                      outline: 'none'
                    }}
                  />
                </div>

                <div>
                  <label htmlFor="reg_last_name" style={{ 
                    display: 'block', 
                    fontSize: '14px', 
                    fontWeight: '500', 
                    color: '#d1d5db', 
                    marginBottom: '6px' 
                  }}>
                    Last Name
                  </label>
                  <input
                    type="text"
                    id="reg_last_name"
                    value={registerForm.last_name}
                    onChange={(e) => setRegisterForm({ ...registerForm, last_name: e.target.value })}
                    style={{
                      width: '100%',
                      backgroundColor: '#1c1c1c',
                      color: '#fff',
                      borderRadius: '6px',
                      padding: '12px',
                      border: '1px solid #2b2b2b',
                      outline: 'none'
                    }}
                  />
                </div>

                <button 
                  type="submit" 
                  disabled={loading}
                  style={{
                    width: '100%',
                    backgroundColor: 'var(--yellow)',
                    color: '#000',
                    fontWeight: '600',
                    border: 'none',
                    padding: '12px',
                    borderRadius: '6px',
                    cursor: 'pointer',
                    opacity: loading ? 0.6 : 1
                  }}
                >
                  {loading ? 'Creating Account...' : 'Sign Up'}
                </button>
              </form>
            )}

            <div style={{ 
              textAlign: 'center', 
              color: '#64748b', 
              marginTop: '24px', 
              fontSize: '14px' 
            }}>
              {showRegister ? "Already have an account?" : "Don't have an account?"}
              <button 
                type="button" 
                onClick={() => setShowRegister(!showRegister)}
                style={{ 
                  background: 'transparent', 
                  border: 'none', 
                  color: '#667eea', 
                  textDecoration: 'underline', 
                  cursor: 'pointer',
                  marginLeft: '4px',
                  fontSize: '14px',
                  fontWeight: '500'
                }}
              >
                {showRegister ? 'Sign In' : 'Sign Up Now'}
              </button>
            </div>
          </div>
        </main>

        {/* Footer */}
        <footer style={{ 
          fontSize: '12px', 
          color: '#94a3b8', 
          marginTop: '3rem', 
          textAlign: 'center' 
        }}>
          By continuing, you agree to Ozone Telemetry's <button type="button" style={{ textDecoration: 'underline', color: '#667eea', background: 'transparent', border: 'none', cursor: 'pointer', padding: 0 }}>Terms of Service</button> and <button type="button" style={{ textDecoration: 'underline', color: '#667eea', background: 'transparent', border: 'none', cursor: 'pointer', padding: 0 }}>Privacy Policy</button>.
        </footer>
      </div>

      {/* Right Column (Quote) - Hidden on mobile, visible on desktop */}
      <div className="login-right-column">
        <div style={{ maxWidth: '400px' }}>
          <span style={{ 
            fontSize: '64px', 
            color: 'rgba(255, 255, 255, 0.3)', 
            lineHeight: '1', 
            display: 'block', 
            marginBottom: '-40px',
            marginLeft: '-12px'
          }}>"</span>
          <p style={{ 
            fontSize: '24px', 
            fontWeight: '500', 
            color: '#ffffff', 
            lineHeight: '1.4',
            position: 'relative',
            zIndex: '10'
          }}>
            <span style={{ color: '#fbbf24' }}>Ozone Telemetry</span> — monitoring tomorrow's technology, today.
          </p>
          <div style={{ display: 'flex', alignItems: 'center', marginTop: '32px' }}>
            <div style={{ textAlign: 'left' }}>
              <p style={{ fontWeight: '500', color: '#ffffff' }}>Ozone Telemetry</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Auth;
