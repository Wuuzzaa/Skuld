'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuth } from '@/hooks/useAuth';
import { cn } from '@/lib/utils';
import {
  BarChart3,
  TrendingUp,
  Shield,
  Layers,
  Target,
  PieChart,
  Calculator,
  Database,
  Search,
  LogOut,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { LoadingState } from '@/components/ui/spinner';
import { useState } from 'react';

const navItems = [
  { href: '/spreads', label: 'Spreads', icon: TrendingUp, color: 'text-emerald-400' },
  { href: '/iron-condors', label: 'Iron Condors', icon: Layers, color: 'text-blue-400' },
  { href: '/married-puts', label: 'Married Puts', icon: Shield, color: 'text-purple-400' },
  { href: '/position-insurance', label: 'Insurance', icon: Shield, color: 'text-orange-400' },
  { href: '/analyst-prices', label: 'Analyst Prices', icon: Target, color: 'text-cyan-400' },
  { href: '/sector-rotation', label: 'Sector Rotation', icon: PieChart, color: 'text-pink-400' },
  { href: '/expected-value', label: 'Expected Value', icon: Calculator, color: 'text-yellow-400' },
  { href: '/symbols', label: 'Symbols', icon: Search, color: 'text-indigo-400' },
  { href: '/data-logs', label: 'Data Logs', icon: Database, color: 'text-gray-400' },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { user, logout, isReady } = useAuth();
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  if (!isReady) return <LoadingState message="Authenticating..." />;

  return (
    <div className="flex h-screen">
      {/* Sidebar */}
      <aside className={cn(
        'border-r border-border/50 bg-card/80 backdrop-blur-sm flex flex-col transition-all duration-200',
        collapsed ? 'w-16' : 'w-60'
      )}>
        {/* Logo */}
        <div className="p-3 border-b border-border/50 flex items-center gap-2">
          <div className="w-9 h-9 rounded-lg bg-primary/20 flex items-center justify-center flex-shrink-0">
            <BarChart3 className="h-5 w-5 text-primary" />
          </div>
          {!collapsed && (
            <div className="overflow-hidden">
              <h1 className="text-base font-bold tracking-tight">SKULD</h1>
              <p className="text-[10px] text-muted-foreground truncate">Options Platform</p>
            </div>
          )}
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto py-2 px-2 space-y-0.5">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href || pathname.startsWith(item.href + '/');
            return (
              <Link
                key={item.href}
                href={item.href}
                title={collapsed ? item.label : undefined}
                className={cn(
                  'flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-sm transition-all duration-150 group relative',
                  isActive
                    ? 'bg-primary/10 text-foreground font-medium shadow-sm shadow-primary/5'
                    : 'text-muted-foreground hover:bg-accent/50 hover:text-foreground'
                )}
              >
                {isActive && (
                  <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 bg-primary rounded-full" />
                )}
                <Icon className={cn('h-4 w-4 flex-shrink-0', isActive ? item.color : 'group-hover:' + item.color)} />
                {!collapsed && <span className="truncate">{item.label}</span>}
              </Link>
            );
          })}
        </nav>

        {/* Collapse toggle */}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="p-2 mx-2 mb-2 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent/50 transition-colors"
        >
          {collapsed ? <ChevronRight className="h-4 w-4 mx-auto" /> : <ChevronLeft className="h-4 w-4" />}
        </button>

        {/* User section */}
        <div className="p-3 border-t border-border/50">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center flex-shrink-0">
              <span className="text-xs font-bold text-primary">{user?.username?.[0]?.toUpperCase()}</span>
            </div>
            {!collapsed && (
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium truncate">{user?.username}</p>
                <p className="text-[10px] text-muted-foreground">{user?.role}</p>
              </div>
            )}
            <Button variant="ghost" size="icon" onClick={logout} className="h-7 w-7 flex-shrink-0">
              <LogOut className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto p-6 bg-background">{children}</main>
    </div>
  );
}
