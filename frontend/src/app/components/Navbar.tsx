import { Search, Bell, Menu } from 'lucide-react';
import { User } from '../types';

interface NavbarProps {
  onMenuClick: () => void;
  user: User;
}

export function Navbar({ onMenuClick, user }: NavbarProps) {
  return (
    <nav
      className="sticky top-0 z-30 h-16 border-b"
      style={{
        background: 'rgba(15, 23, 42, 0.8)',
        backdropFilter: 'blur(20px)',
        borderColor: 'rgba(255, 255, 255, 0.1)',
      }}
    >
      <div className="h-full px-4 lg:px-6 flex items-center justify-between gap-4">
        {/* Left Section */}
        <div className="flex items-center gap-4 flex-1">
          <button
            onClick={onMenuClick}
            className="lg:hidden text-gray-400 hover:text-white transition-colors"
          >
            <Menu className="w-6 h-6" />
          </button>

          {/* Search Bar */}
          <div className="hidden md:flex items-center flex-1 max-w-md">
            <div
              className="flex items-center gap-3 px-4 py-2 rounded-xl w-full"
              style={{
                background: 'rgba(255, 255, 255, 0.05)',
                border: '1px solid rgba(255, 255, 255, 0.1)',
              }}
            >
              <Search className="w-4 h-4 text-gray-400" />
              <input
                type="text"
                placeholder="Search files..."
                className="bg-transparent text-white text-sm outline-none w-full placeholder:text-gray-500"
              />
            </div>
          </div>
        </div>

        {/* Right Section */}
        <div className="flex items-center gap-3">
          {/* Notifications */}
          <button
            className="relative p-2 rounded-xl hover:bg-white/5 transition-colors"
          >
            <Bell className="w-5 h-5 text-gray-400" />
            <span
              className="absolute top-1 right-1 w-2 h-2 rounded-full"
              style={{
                background: '#ef4444',
                boxShadow: '0 0 8px rgba(239, 68, 68, 0.6)',
              }}
            />
          </button>

          {/* User Profile */}
          <div className="flex items-center gap-3 pl-3 border-l border-white/10">
            <div className="hidden sm:block text-right">
              <p className="text-sm text-white font-medium">{user.name}</p>
              <p className="text-xs text-gray-400">{user.email}</p>
            </div>
            <div
              className="w-10 h-10 rounded-full overflow-hidden ring-2 ring-[#38bdf8]/30"
              style={{
                background: 'linear-gradient(135deg, #38bdf8 0%, #0ea5e9 100%)',
              }}
            >
              <img
                src={user.avatar}
                alt={user.name}
                className="w-full h-full object-cover"
              />
            </div>
          </div>
        </div>
      </div>
    </nav>
  );
}
