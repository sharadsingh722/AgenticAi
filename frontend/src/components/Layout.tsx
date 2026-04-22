import { useState, useEffect } from 'react';
import type { CSSProperties } from 'react';
import { NavLink, Outlet, useLocation, useNavigate, useParams } from 'react-router-dom';
import { 
  Users, 
  FileText, 
  Crosshair, 
  Plus, 
  Menu, 
  MessageSquareQuote,
  Circle,
  Trash2,
  Moon,
  Sun
} from 'lucide-react';
import { cn } from '../utils/utils';
import { listSessions, deleteSession } from '../api/client';
import type { ChatSession } from '../api/client';

const navItems = [
  { to: '/resumes', label: 'Resumes', icon: Users },
  { to: '/tenders', label: 'Tenders', icon: FileText },
  { to: '/matching', label: 'Matching', icon: Crosshair },
];

export default function Layout() {
  const location = useLocation();
  const navigate = useNavigate();
  const { sessionId: currentSessionId } = useParams();
  const isChat = location.pathname.startsWith('/chat');
  
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [theme, setTheme] = useState<'day' | 'night'>('day');

  const closeSidebar = () => setIsSidebarOpen(false);
  const toggleSidebar = () => setIsSidebarOpen(!isSidebarOpen);
  const toggleDesktopSidebar = () => setIsSidebarCollapsed((prev) => !prev);
  const toggleTheme = () => {
    setTheme((prev) => (prev === 'day' ? 'night' : 'day'));
  };

  useEffect(() => {
    const storedTheme = window.localStorage.getItem('matcher-theme');
    if (storedTheme === 'day' || storedTheme === 'night') {
      setTheme(storedTheme);
    }
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem('matcher-theme', theme);
  }, [theme]);

  useEffect(() => {
    fetchSessions();
  }, [location.pathname]); // Refresh when navigating to/from chat

  const fetchSessions = async () => {
    try {
      const data = await listSessions();
      setSessions(data);
    } catch (error) {
      console.error('Failed to fetch sessions:', error);
    }
  };

  const handleDeleteSession = async (e: React.MouseEvent, id: string) => {
    e.preventDefault();
    e.stopPropagation();
    if (confirm('Are you sure you want to delete this chat session?')) {
      try {
        await deleteSession(id);
        setSessions(prev => prev.filter(s => s.id !== id));
        if (currentSessionId === id) {
          navigate('/chat');
        }
      } catch (error) {
        console.error('Failed to delete session:', error);
      }
    }
  };

  const startNewChat = () => {
    const newId = crypto.randomUUID();
    navigate(`/chat/${newId}`);
    closeSidebar();
  };

  const groupSessions = () => {
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    const sevenDaysAgo = new Date(today);
    sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);

    const grouped: { group: string; items: ChatSession[] }[] = [
      { group: 'Today', items: [] },
      { group: 'Yesterday', items: [] },
      { group: 'Previous 7 Days', items: [] },
    ];

    sessions.forEach(session => {
      const date = new Date(session.updated_at);
      if (date >= today) {
        grouped[0].items.push(session);
      } else if (date >= yesterday) {
        grouped[1].items.push(session);
      } else if (date >= sevenDaysAgo) {
        grouped[2].items.push(session);
      }
    });

    return grouped.filter(g => g.items.length > 0);
  };

  return (
    <div
      className="app-shell min-h-screen bg-white text-slate-900 flex font-sans"
      style={
        {
          '--sidebar-offset': isSidebarCollapsed ? '5.75rem' : '17.5rem',
        } as CSSProperties
      }
    >
      {/* Mobile Backdrop */}
      {isSidebarOpen && (
        <div
          className="fixed inset-0 bg-slate-900/20 z-40 lg:hidden backdrop-blur-sm transition-opacity"
          onClick={closeSidebar}
        />
      )}

      {/* Sidebar */}
      <aside className={cn(
        "app-sidebar",
        "fixed inset-y-0 left-0 z-50 w-[280px] bg-slate-50 border-r border-slate-200 flex flex-col transform transition-all duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] lg:translate-x-0 lg:static lg:flex lg:shrink-0",
        isSidebarCollapsed ? "lg:w-[92px]" : "lg:w-[280px]",
        isSidebarOpen ? "translate-x-0" : "-translate-x-full"
      )}>
        {/* Sidebar Logo */}
        <div className={cn("p-6 flex items-center gap-3", isSidebarCollapsed && "lg:px-5 lg:justify-center")}>
          <div className="sidebar-logo-badge w-10 h-10 rounded-xl bg-violet-600 flex items-center justify-center shadow-lg shadow-violet-100 message-float">
            <Crosshair className="w-5 h-5 text-white" />
          </div>
          <div className={cn("sidebar-copy", isSidebarCollapsed && "lg:sidebar-copy-collapsed")}>
            <h2 className="text-[17px] font-black text-slate-900 tracking-tight leading-none">MatchOps AI</h2>
            <p className="text-[9px] text-slate-400 font-bold uppercase tracking-[0.15em] mt-1 text-blue-600">Tender Intelligence Suite</p>
          </div>
        </div>

        {/* Global Navigation */}
        <nav className="px-3 space-y-1 mb-8">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              onClick={closeSidebar}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 px-4 py-2.5 rounded-xl text-xs font-bold transition-all group",
                  isSidebarCollapsed && "lg:justify-center lg:px-0",
                  isActive
                    ? "bg-slate-100 text-slate-900 shadow-sm"
                    : "text-slate-500 hover:bg-slate-100/50 hover:text-slate-900"
                )
              }
            >
              <item.icon className="w-4 h-4 transition-colors" />
              <span className={cn("sidebar-copy", isSidebarCollapsed && "lg:sidebar-copy-collapsed")}>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        {/* Action Section */}
        <div className="px-4 mb-8">
          <div className={cn("flex gap-2", isSidebarCollapsed && "lg:flex-col")}>
            <button 
              onClick={startNewChat}
              className={cn(
                "flex-1 flex items-center gap-3 px-5 py-3.5 rounded-xl text-sm font-black transition-all shadow-lg active:scale-95 group",
                isSidebarCollapsed && "lg:justify-center lg:px-0",
                !currentSessionId && isChat
                  ? "bg-violet-600 text-white shadow-violet-200" 
                  : "bg-white text-slate-900 shadow-sm border border-slate-200 hover:bg-slate-50"
              )}
            >
              <Plus className="w-5 h-5" />
              <span className={cn("sidebar-copy", isSidebarCollapsed && "lg:sidebar-copy-collapsed")}>New Session</span>
            </button>
            <button
              onClick={toggleTheme}
              aria-label={`Switch to ${theme === 'day' ? 'night' : 'day'} mode`}
              className={cn(
                "theme-toggle group px-4 rounded-xl border border-slate-200 bg-white text-slate-600 hover:text-slate-900 hover:bg-slate-50 transition-all shadow-sm active:scale-95",
                isSidebarCollapsed && "lg:h-[54px]"
              )}
            >
              <span className="relative z-[1] block transition-transform duration-500 group-hover:rotate-12">
                {theme === 'day' ? <Moon className="w-4 h-4" /> : <Sun className="w-4 h-4" />}
              </span>
            </button>
          </div>
        </div>

        {/* History Sections */}
        <div className="flex-1 overflow-y-auto px-3 custom-scrollbar space-y-6 pb-6">
          {groupSessions().map((group) => (
            <div key={group.group}>
              <h3 className={cn("px-4 text-[10px] font-black text-slate-400 uppercase tracking-widest mb-3 sidebar-copy", isSidebarCollapsed && "lg:sidebar-copy-collapsed")}>{group.group}</h3>
              <div className="space-y-0.5">
                {group.items.map((session) => (
                  <NavLink
                    key={session.id}
                    to={`/chat/${session.id}`}
                    onClick={closeSidebar}
                    className={({ isActive }) => cn(
                      "w-full flex items-center gap-3 px-4 py-2.5 rounded-xl text-[12px] font-medium transition-all group relative overflow-hidden",
                      isSidebarCollapsed && "lg:justify-center lg:px-0",
                      isActive
                        ? "bg-slate-200 text-slate-900"
                        : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                    )}
                  >
                    <MessageSquareQuote className="w-3.5 h-3.5 text-slate-300 group-hover:text-slate-500 shrink-0" />
                    <span className={cn("truncate flex-1 sidebar-copy", isSidebarCollapsed && "lg:sidebar-copy-collapsed")}>{session.title}</span>
                    <button
                      onClick={(e) => handleDeleteSession(e, session.id)}
                      className={cn(
                        "opacity-0 group-hover:opacity-100 p-1 text-slate-400 hover:text-rose-500 transition-opacity sidebar-fade",
                        isSidebarCollapsed && "lg:sidebar-fade-collapsed"
                      )}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </NavLink>
                ))}
              </div>
            </div>
          ))}
        </div>

      </aside>

      {/* Main Content Area */}
      <div className="app-main flex-1 flex flex-col min-w-0 relative">
        {/* Mobile/Floating Header */}
        <header className="ai-topbar lg:hidden p-4 sticky top-0 z-30 flex items-center justify-between border-b border-slate-200 bg-white/80 backdrop-blur-xl">
          <button onClick={toggleSidebar} className="p-2 text-slate-500 hover:text-slate-900">
            <Menu className="w-6 h-6" />
          </button>
          <div className="flex items-center gap-2">
            <Circle className="w-2 h-2 text-violet-500 fill-violet-500" />
            <h2 className="text-[13px] font-black text-slate-900 uppercase tracking-tighter">
              MatchOps Command
            </h2>
          </div>
          <button
            onClick={toggleTheme}
            aria-label={`Switch to ${theme === 'day' ? 'night' : 'day'} mode`}
            className="theme-toggle group w-10 h-10 rounded-xl border border-slate-200 bg-white text-slate-600 flex items-center justify-center shadow-sm"
          >
            <span className="relative z-[1] block transition-transform duration-500">
              {theme === 'day' ? <Moon className="w-4 h-4" /> : <Sun className="w-4 h-4" />}
            </span>
          </button>
        </header>

        <button
          onClick={toggleDesktopSidebar}
          aria-label={isSidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          className="hidden lg:flex absolute left-4 top-4 z-40 h-10 w-10 items-center justify-center rounded-xl border border-slate-200 bg-white/90 text-slate-500 shadow-sm backdrop-blur-md transition-all hover:text-slate-900 hover:shadow-md"
        >
          <Menu className={cn("w-4 h-4 transition-transform duration-300", isSidebarCollapsed && "rotate-180")} />
        </button>

        <main className={cn(
          "flex-1 bg-white min-h-0",
          isChat ? "p-0 overflow-hidden" : "p-4 md:p-10 overflow-auto"
        )}>
          <div className={cn(
            isChat ? "h-full min-h-0" : "max-w-7xl mx-auto"
          )}>
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
