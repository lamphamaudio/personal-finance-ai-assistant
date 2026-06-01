import { NavLink } from 'react-router-dom';

export const Sidebar = ({ isOpen, toggleSidebar }) => {
  return (
    <aside className={`sidebar ${isOpen ? 'open' : ''}`} id="sidebar">
      <div className="sidebar-brand">
        <svg className="brand-icon" width="28" height="24" viewBox="0 0 36 30" fill="none">
          {/* Prism body */}
          <polygon points="16 1 1 29 31 29" fill="#D8E8F0" stroke="#A8BCC8" strokeWidth="0.8" />
          {/* Incoming white beam */}
          <line x1="0" y1="17" x2="10" y2="14.5" stroke="#BCC8D4" strokeWidth="2" strokeLinecap="round" />
          {/* Outgoing spectrum — fanned out */}
          <line x1="22" y1="10" x2="36" y2="5" stroke="#E03E3E" strokeWidth="2" strokeLinecap="round" />
          <line x1="22" y1="12" x2="36" y2="9" stroke="#FF7F27" strokeWidth="2" strokeLinecap="round" />
          <line x1="22" y1="14" x2="36" y2="13" stroke="#F0C040" strokeWidth="2" strokeLinecap="round" />
          <line x1="22" y1="16" x2="36" y2="17" stroke="#0F7B6C" strokeWidth="2" strokeLinecap="round" />
          <line x1="22" y1="18" x2="36" y2="21" stroke="#2EAADC" strokeWidth="2" strokeLinecap="round" />
          <line x1="22" y1="20" x2="36" y2="25" stroke="#9B51E0" strokeWidth="2" strokeLinecap="round" />
        </svg>
        Spectra AI Assistant
      </div>
      <nav>
        <ul className="sidebar-nav">
          <li>
            <NavLink to="/" end className={({ isActive }) => isActive ? 'active' : ''} onClick={toggleSidebar}>
              <svg className="nav-icon" width="18" height="18" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="12" width="4" height="9" rx="1" />
                <rect x="10" y="7" width="4" height="14" rx="1" />
                <rect x="17" y="3" width="4" height="18" rx="1" />
              </svg>
              Tổng quan
            </NavLink>
          </li>
          <li>
            <NavLink to="/transactions" className={({ isActive }) => isActive ? 'active' : ''} onClick={toggleSidebar}>
              <svg className="nav-icon" width="18" height="18" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="8" y1="6" x2="21" y2="6" />
                <line x1="8" y1="12" x2="21" y2="12" />
                <line x1="8" y1="18" x2="21" y2="18" />
                <circle cx="4" cy="6" r="1" />
                <circle cx="4" cy="12" r="1" />
                <circle cx="4" cy="18" r="1" />
              </svg>
              Giao dịch
            </NavLink>
          </li>
          <li>
            <NavLink to="/budget" className={({ isActive }) => isActive ? 'active' : ''} onClick={toggleSidebar}>
              <svg className="nav-icon" width="18" height="18" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <rect x="2" y="4" width="20" height="16" rx="2" />
                <line x1="2" y1="10" x2="22" y2="10" />
                <circle cx="16" cy="15" r="2" />
              </svg>
              Ngân sách
            </NavLink>
          </li>
          <li>
            <NavLink to="/trends" className={({ isActive }) => isActive ? 'active' : ''} onClick={toggleSidebar}>
              <svg className="nav-icon" width="18" height="18" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
                <polyline points="16 7 22 7 22 13" />
              </svg>
              Xu hướng
            </NavLink>
          </li>
          <li>
            <NavLink to="/subscriptions" className={({ isActive }) => isActive ? 'active' : ''} onClick={toggleSidebar}>
              <svg className="nav-icon" width="18" height="18" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M17 1l4 4-4 4" />
                <path d="M3 11V9a4 4 0 0 1 4-4h14" />
                <path d="M7 23l-4-4 4-4" />
                <path d="M21 13v2a4 4 0 0 1-4 4H3" />
              </svg>
              Định kỳ
            </NavLink>
          </li>
          <li>
            <NavLink to="/upload" className={({ isActive }) => isActive ? 'active' : ''} onClick={toggleSidebar}>
              <svg className="nav-icon" width="18" height="18" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="16 16 12 12 8 16" />
                <line x1="12" y1="12" x2="12" y2="21" />
                <path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3" />
              </svg>
              Tải lên
            </NavLink>
          </li>
          <li>
            <NavLink to="/settings" className={({ isActive }) => isActive ? 'active' : ''} onClick={toggleSidebar}>
              <svg className="nav-icon" width="18" height="18" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="3" />
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
              </svg>
              Cài đặt
            </NavLink>
          </li>
        </ul>
      </nav>
      <div className="sidebar-footer">
        Tự lưu trữ · Dữ liệu nằm trên máy của bạn
      </div>
    </aside>
  );
};
