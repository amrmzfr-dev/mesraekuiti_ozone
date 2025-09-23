import React from 'react';

const Topbar = ({ user, onLogout }) => {
  return (
    <header className="topbar">
      <div className="topbar-left">
        <div className="logo">
          <span className="logo-icon">🌊</span>
        </div>
      </div>
      
      <div className="topbar-right">
        <div className="user-info">
          {user && (
            <>
              <span className="user-name">Welcome, {user.username}</span>
              <div className="user-menu">
                <button className="user-avatar" title={user.email}>
                  {user.first_name ? user.first_name[0].toUpperCase() : user.username[0].toUpperCase()}
                </button>
                <div className="user-dropdown">
                  <div className="user-details">
                    <div className="user-name-full">{user.first_name} {user.last_name}</div>
                    <div className="user-email">{user.email}</div>
                    <div className="user-access">Access: {user.access_level}</div>
                  </div>
                  <div className="user-actions">
                    <button className="dropdown-item" onClick={onLogout}>
                      <span className="dropdown-icon">🚪</span>
                      Logout
                    </button>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  );
};

export default Topbar;
