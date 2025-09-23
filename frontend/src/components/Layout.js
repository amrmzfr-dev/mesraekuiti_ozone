import React, { useState } from 'react';
import Sidebar from './Sidebar';

const Layout = ({ children, user, onLogout }) => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true); // Default to open

  const toggleSidebar = () => {
    setIsSidebarOpen(!isSidebarOpen);
  };

  return (
    <div className="app-layout">
      <Sidebar 
        isOpen={isSidebarOpen}
        onToggle={toggleSidebar}
        onLogout={onLogout}
      />
      <main className={`main-content ${isSidebarOpen ? 'sidebar-open' : ''}`}>
        {children}
      </main>
    </div>
  );
};

export default Layout;
