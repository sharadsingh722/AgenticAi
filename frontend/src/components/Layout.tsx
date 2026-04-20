import { useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';

const navItems = [
  { to: '/resumes', label: 'Resumes', icon: '👤' },
  { to: '/tenders', label: 'Tenders', icon: '📄' },
  { to: '/matching', label: 'Matching', icon: '🎯' },
  { to: '/chat', label: 'Chat', icon: '💬' },
];

export default function Layout() {
  const location = useLocation();
  const isChat = location.pathname === '/chat';
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  const closeSidebar = () => setIsSidebarOpen(false);
  const toggleSidebar = () => setIsSidebarOpen(!isSidebarOpen);

  return (
    <div className="min-h-screen bg-gray-50 flex">
      {/* Mobile Backdrop */}
      {isSidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden backdrop-blur-sm transition-opacity"
          onClick={closeSidebar}
        />
      )}

      {/* Sidebar */}
      <aside className={`
        fixed inset-y-0 left-0 z-50 w-64 bg-white border-r border-gray-200 flex flex-col transform transition-transform duration-300 ease-in-out
        ${isSidebarOpen ? 'translate-x-0' : '-translate-x-full'}
        ${!isChat ? 'lg:translate-x-0 lg:static' : (isSidebarOpen ? 'lg:translate-x-0 lg:static' : 'lg:fixed lg:-translate-x-full')}
      `}>
        <div className="p-6 border-b border-gray-200 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-black text-gray-900 tracking-tight">Matcher V2</h1>
            <p className="text-[10px] text-gray-400 font-bold uppercase tracking-widest mt-1">Agentic AI Engine</p>
          </div>
          <button onClick={closeSidebar} className="lg:hidden p-2 text-gray-400 hover:text-gray-900 transition-colors">
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <nav className="flex-1 p-4 space-y-1">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              onClick={closeSidebar}
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-bold transition-all ${isActive
                  ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/20'
                  : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                }`
              }
            >
              <span className="text-lg">{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>

        {isChat && (
          <div className="p-4 mt-auto border-t border-gray-100">
            <button
              onClick={() => {
                window.dispatchEvent(new CustomEvent('clear-chat-history'));
                closeSidebar();
              }}
              className="w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-bold text-red-600 hover:bg-red-50 transition-all border border-transparent hover:border-red-100"
            >
              <span className="text-lg">🗑️</span>
              Clear History
            </button>
          </div>
        )}
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Mobile/Toggle Header */}
        <header className={`${!isChat ? 'lg:hidden' : ''} bg-white border-b border-gray-100 p-4 sticky top-0 z-30 flex items-center justify-between`}>
          <button
            onClick={toggleSidebar}
            className="p-2 -ml-2 text-gray-500 hover:text-gray-900 transition-colors"
          >
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <h2 className="text-sm font-black text-gray-900 uppercase tracking-tighter">
            {navItems.find(i => location.pathname.startsWith(i.to))?.label || 'Dashboard'}
          </h2>
          <div className="w-10"></div> {/* Spacer */}
        </header>

        <main className={`flex-1 overflow-x-hidden ${isChat ? 'p-0' : 'p-4 md:p-8'}`}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
