import { useState, useEffect, useRef } from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { ToastContainer } from '../ui/Toast';
import ChatPanel from '../chat/ChatPanel';

export const Layout = () => {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const layoutRef = useRef(null);

  const toggleSidebar = () => {
    setSidebarOpen(!sidebarOpen);
  };

  const closeSidebar = () => {
    setSidebarOpen(false);
  };

  // Close sidebar on outside click (mobile)
  useEffect(() => {
    const handleOutsideClick = (e) => {
      const sidebar = document.getElementById('sidebar');
      const toggle = document.getElementById('menuToggle');
      
      if (
        window.innerWidth <= 768 &&
        sidebarOpen &&
        sidebar &&
        !sidebar.contains(e.target) &&
        toggle &&
        !toggle.contains(e.target)
      ) {
        setSidebarOpen(false);
      }
    };

    document.addEventListener('click', handleOutsideClick);
    return () => document.removeEventListener('click', handleOutsideClick);
  }, [sidebarOpen]);

  return (
    <div ref={layoutRef} style={{ display: 'flex', minHeight: '100vh', width: '100%' }}>
      <button className="menu-toggle" id="menuToggle" onClick={toggleSidebar}>
        ☰
      </button>

      <Sidebar isOpen={sidebarOpen} toggleSidebar={closeSidebar} />

      <main className="main">
        <div className="main-inner">
          <Outlet />
        </div>
      </main>

      <ChatPanel />
      <ToastContainer />
    </div>
  );
};
