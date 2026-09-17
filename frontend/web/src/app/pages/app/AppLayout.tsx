import { Outlet, NavLink, Link, useLocation, useNavigate } from "react-router";
import { Home, Wand2, CreditCard, PanelLeftClose, PanelLeft, Sun, Moon, Sparkles, Image, Search, LogOut, User } from "lucide-react";
import { useState } from "react";
import { useTheme } from "@/app/contexts/ThemeContext";
import { useAuth } from "@/app/contexts/AuthContext";
import { LogoApp } from "@/app/components/LogoApp";
import { useLocale } from "@/app/i18n";
import { formatRequestLabel } from "@/app/lib/requestLabel";
import { trackAppClick } from "@/app/lib/analytics/client";

export function AppLayout() {
  const [isSidebarOpen, setIsSidebarOpen] = useState(() => (
    typeof window !== "undefined" ? window.innerWidth >= 768 : true
  ));
  const { isDarkMode, toggleTheme } = useTheme();
  const { logout, user, balance } = useAuth();
  const { isEnglish, locale } = useLocale();
  const location = useLocation();
  const navigate = useNavigate();

  const navigation = [
    { name: isEnglish ? "Home" : "Главная", href: "/app", icon: Home, end: true },
    {
      name: isEnglish ? "Studio" : "Студия",
      href: "/app/workspace",
      icon: Wand2,
      subItems: [
        { name: isEnglish ? "Interior design" : "Дизайн интерьера", href: "/app/workspace?mode=design", icon: Sparkles },
        { name: isEnglish ? "Design by reference" : "Дизайн по референсу", href: "/app/workspace?mode=reference", icon: Image },
        { name: isEnglish ? "Furniture search" : "Поиск мебели", href: "/app/workspace?mode=furniture", icon: Search },
      ]
    },
    { name: isEnglish ? "Billing" : "Оплата", href: "/app/billing", icon: CreditCard },
    { name: isEnglish ? "Profile" : "Профиль", href: "/app/profile", icon: User },
  ];

  return (
    <div className={`flex flex-col h-screen ${isDarkMode ? 'bg-[#1A1A1A] text-gray-100' : 'bg-gray-50 text-gray-900'}`}>
      {/* Header */}
      <header className={`h-16 flex items-center justify-between flex-shrink-0 border-b px-5 ${isDarkMode ? 'bg-[#0F0F0F] border-gray-800' : 'bg-white border-gray-200'}`}>
        <Link
          to="/app/workspace"
          className="flex items-center"
          onClick={() => {
            void trackAppClick("navigation", "logo_workspace_click");
          }}
        >
          <LogoApp height={32} />
        </Link>
        
        {/* User Card - Desktop */}
        <div className="hidden md:flex items-center gap-4">
          {/* Balance Badge */}
          <div className={`px-4 py-2 rounded-lg ${isDarkMode ? 'bg-gray-800' : 'bg-gray-100'}`}>
            <span className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>{isEnglish ? "Balance:" : "Баланс:"}</span>
            <span className="text-sm font-bold text-[#7A8B4A] ml-2">{formatRequestLabel(balance, locale)}</span>
          </div>
          
          {/* User Info */}
          <Link 
            to="/app/profile"
            className={`flex items-center gap-3 px-3 py-2 rounded-lg transition-colors ${isDarkMode ? 'hover:bg-gray-800' : 'hover:bg-gray-100'}`}
          >
            <div className="w-9 h-9 rounded-full bg-gradient-to-br from-[#7A8B4A] to-[#6B7B3F] flex items-center justify-center text-white text-sm font-semibold">
              {user?.email?.charAt(0).toUpperCase() || 'U'}
            </div>
            <p className={`text-sm ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>{user?.email || (isEnglish ? "Profile" : "Профиль")}</p>
          </Link>
        </div>
        
        {/* Mobile menu button */}
        <button
          onClick={() => {
            void trackAppClick("navigation", "mobile_sidebar_toggle", { open: !isSidebarOpen });
            setIsSidebarOpen(!isSidebarOpen);
          }}
          className={`md:hidden p-2 rounded-lg ${isDarkMode ? 'hover:bg-gray-800' : 'hover:bg-gray-100'}`}
        >
          {isSidebarOpen ? <PanelLeftClose className="w-6 h-6" /> : <PanelLeft className="w-6 h-6" />}
        </button>
      </header>

      <div className="flex flex-1 overflow-hidden">
      {/* Mobile Overlay */}
      {isSidebarOpen && (
        <div 
          className="md:hidden fixed inset-0 bg-black/50 z-30 top-16"
          onClick={() => setIsSidebarOpen(false)}
        />
      )}
      
      {/* Sidebar */}
      <aside 
        className={`${
          isSidebarOpen ? 'w-64' : 'w-16'
        } transition-all duration-300 ${isDarkMode ? 'bg-[#0F0F0F] border-gray-800' : 'bg-white border-gray-200'} border-r flex flex-col flex-shrink-0
        fixed md:relative inset-y-0 left-0 top-16 md:top-0 z-40 ${
          !isSidebarOpen ? '-translate-x-full md:translate-x-0' : 'translate-x-0'
        }`}
      >
        {/* Navigation - Scrollable */}
        <div className="flex-1 overflow-y-auto overflow-x-hidden">
          <nav className="p-3 space-y-1">
            {navigation.map((item) => (
              <div key={item.name}>
                <NavLink
                  to={item.href}
                  end={item.end}
                  onClick={(e) => {
                    void trackAppClick("navigation", "primary_nav_click", { target: item.href });
                    if (item.subItems && !isSidebarOpen) {
                      e.preventDefault();
                      navigate(item.href);
                    }
                  }}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors group relative ${
                      isActive && !item.subItems
                        ? 'bg-[#7A8B4A] text-white'
                        : `${isDarkMode ? 'text-gray-400 hover:bg-gray-800 hover:text-gray-100' : 'text-gray-700 hover:bg-gray-100 hover:text-gray-900'}`
                    }`
                  }
                >
                  <item.icon className="w-5 h-5 flex-shrink-0" />
                  {isSidebarOpen && <span>{item.name}</span>}
                  {!isSidebarOpen && (
                    <div className="absolute left-full ml-2 px-2 py-1 bg-gray-900 text-white text-sm rounded opacity-0 group-hover:opacity-100 pointer-events-none whitespace-nowrap z-50">
                      {item.name}
                    </div>
                  )}
                </NavLink>
                
                {/* Sub Items */}
                {item.subItems && isSidebarOpen && (
                  <div className="ml-8 mt-1 space-y-1">
                    {item.subItems.map((subItem) => {
                      // Extract query params from subItem.href
                      const url = new URL(subItem.href, window.location.origin);
                      const subItemMode = url.searchParams.get('mode');
                      const currentMode = new URLSearchParams(location.search).get('mode');
                      const isSubItemActive = location.pathname === '/app/workspace' && subItemMode === currentMode;
                      
                      return (
                        <Link
                          key={subItem.name}
                          to={subItem.href}
                          onClick={() => {
                            void trackAppClick("navigation", "workspace_nav_click", { target: subItem.href });
                          }}
                          className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${
                            isSubItemActive
                              ? 'bg-[#7A8B4A]/20 text-[#7A8B4A] font-medium'
                              : `${isDarkMode ? 'text-gray-500 hover:bg-gray-800 hover:text-gray-300' : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'}`
                          }`}
                        >
                          <subItem.icon className="w-4 h-4" />
                          <span>{subItem.name}</span>
                        </Link>
                      );
                    })}
                  </div>
                )}
              </div>
            ))}
          </nav>
        </div>

        {/* Toggle Button */}
        <div className={`px-3 py-3 border-t flex-shrink-0 ${isDarkMode ? 'border-gray-800' : 'border-gray-200'}`}>
          <button
            onClick={() => {
              void trackAppClick("navigation", "desktop_sidebar_toggle", { open: !isSidebarOpen });
              setIsSidebarOpen(!isSidebarOpen);
            }}
            className={`w-full h-10 flex items-center ${isSidebarOpen ? 'gap-3' : 'justify-center'} px-3 rounded-lg transition-colors group relative ${isDarkMode ? 'hover:bg-gray-800' : 'hover:bg-gray-100'}`}
          >
            {isSidebarOpen ? <PanelLeftClose className={`w-5 h-5 flex-shrink-0 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`} /> : <PanelLeft className={`w-5 h-5 flex-shrink-0 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`} />}
            {isSidebarOpen && (
              <span className={isDarkMode ? 'text-gray-400' : 'text-gray-600'}>
                {isEnglish ? "Collapse menu" : "Свернуть меню"}
              </span>
            )}
            {!isSidebarOpen && (
              <div className="absolute left-full ml-2 px-2 py-1 bg-gray-900 text-white text-sm rounded opacity-0 group-hover:opacity-100 pointer-events-none whitespace-nowrap z-50">
                {isEnglish ? "Expand menu" : "Развернуть меню"}
              </div>
            )}
          </button>
        </div>

        {/* Theme Toggle */}
        <div className={`px-3 py-3 border-t flex-shrink-0 ${isDarkMode ? 'border-gray-800' : 'border-gray-200'}`}>
          <button
            onClick={() => {
              void trackAppClick("navigation", "theme_toggle", { next_theme: isDarkMode ? "light" : "dark" });
              toggleTheme();
            }}
            className={`w-full h-10 flex items-center ${isSidebarOpen ? 'gap-3' : 'justify-center'} px-3 rounded-lg transition-colors group relative ${isDarkMode ? 'hover:bg-gray-800' : 'hover:bg-gray-100'}`}
          >
            {isDarkMode ? <Sun className={`w-5 h-5 flex-shrink-0 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`} /> : <Moon className="w-5 h-5 text-gray-600 flex-shrink-0" />}
            {isSidebarOpen && (
              <span className={isDarkMode ? 'text-gray-400' : 'text-gray-600'}>
                {isDarkMode ? (isEnglish ? 'Light theme' : 'Светлая тема') : isEnglish ? 'Dark theme' : 'Темная тема'}
              </span>
            )}
            {!isSidebarOpen && (
              <div className="absolute left-full ml-2 px-2 py-1 bg-gray-900 text-white text-sm rounded opacity-0 group-hover:opacity-100 pointer-events-none whitespace-nowrap z-50">
                {isDarkMode ? (isEnglish ? 'Light theme' : 'Светлая тема') : isEnglish ? 'Dark theme' : 'Темная тема'}
              </div>
            )}
          </button>
        </div>

        {/* Logout */}
        <div className={`px-3 py-3 border-t flex-shrink-0 ${isDarkMode ? 'border-gray-800' : 'border-gray-200'}`}>
          <button
            onClick={() => {
              void trackAppClick("navigation", "logout_click");
              void logout();
            }}
            className={`w-full h-10 flex items-center ${isSidebarOpen ? 'gap-3' : 'justify-center'} px-3 rounded-lg transition-colors group relative ${isDarkMode ? 'hover:bg-gray-800' : 'hover:bg-gray-100'}`}
          >
            <LogOut className={`w-5 h-5 flex-shrink-0 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`} />
            {isSidebarOpen && (
              <span className={isDarkMode ? 'text-gray-400' : 'text-gray-600'}>
                {isEnglish ? "Sign out" : "Выйти"}
              </span>
            )}
            {!isSidebarOpen && (
              <div className="absolute left-full ml-2 px-2 py-1 bg-gray-900 text-white text-sm rounded opacity-0 group-hover:opacity-100 pointer-events-none whitespace-nowrap z-50">
                {isEnglish ? "Sign out" : "Выйти"}
              </div>
            )}
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Page Content */}
        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
      </div>
    </div>
  );
}
