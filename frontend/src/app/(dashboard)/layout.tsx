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
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { LoadingState } from '@/components/ui/spinner';

const navItems = [
  { href: '/spreads', label: 'Spreads', icon: TrendingUp },
  { href: '/iron-condors', label: 'Iron Condors', icon: Layers },
  { href: '/married-puts', label: 'Married Puts', icon: Shield },
  { href: '/position-insurance', label: 'Position Insurance', icon: Shield },
  { href: '/analyst-prices', label: 'Analyst Prices', icon: Target },
  { href: '/sector-rotation', label: 'Sector Rotation', icon: PieChart },
  { href: '/expected-value', label: 'Expected Value', icon: Calculator },
  { href: '/symbols', label: 'Symbols', icon: Search },
  { href: '/data-logs', label: 'Data Logs', icon: Database },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { user, logout, isReady } = useAuth();
  const pathname = usePathname();

  if (!isReady) return <LoadingState message="Authenticating..." />;

  return (
    <div className="flex h-screen">
      {/* Sidebar */}
      <aside className="w-64 border-r bg-card flex flex-col">
        <div className="p-4 border-b">
          <h1 className="text-xl font-bold flex items-center gap-2">
            <BarChart3 className="h-6 w-6 text-primary" />
            SKULD
          </h1>
          <p className="text-xs text-muted-foreground mt-1">Options Trading Platform</p>
        </div>

        <nav className="flex-1 overflow-y-auto p-2 space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href || pathname.startsWith(item.href + '/');
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  'flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors',
                  isActive
                    ? 'bg-primary/10 text-primary font-medium'
                    : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                )}
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="p-4 border-t">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">{user?.username}</p>
              <p className="text-xs text-muted-foreground">{user?.role}</p>
            </div>
            <Button variant="ghost" size="icon" onClick={logout}>
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto p-6">{children}</main>
    </div>
  );
}
