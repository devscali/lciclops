/**
 * Sidebar Component
 * Elena: "Navegacion lateral limpia y funcional"
 */
'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { clsx } from 'clsx';
import {
  LayoutDashboard,
  Upload,
  FileText,
  BarChart3,
  Settings,
  LogOut,
  Pizza,
} from 'lucide-react';

interface NavItem {
  href: string;
  label: string;
  icon: React.ReactNode;
}

const navItems: NavItem[] = [
  { href: '/dashboard', label: 'Dashboard', icon: <LayoutDashboard className="w-5 h-5" /> },
  { href: '/upload', label: 'Subir Documento', icon: <Upload className="w-5 h-5" /> },
  { href: '/documents', label: 'Documentos', icon: <FileText className="w-5 h-5" /> },
  { href: '/reports', label: 'Reportes', icon: <BarChart3 className="w-5 h-5" /> },
];

interface SidebarProps {
  onLogout?: () => void;
}

export function Sidebar({ onLogout }: SidebarProps) {
  const pathname = usePathname();

  return (
    <aside className="fixed left-0 top-0 h-full w-64 bg-white shadow-lg z-40 flex flex-col">
      {/* Logo */}
      <div className="p-6 border-b border-lc-gray-100">
        <Link href="/dashboard" className="flex items-center gap-3">
          <div className="p-2 bg-lc-orange-500 rounded-lg">
            <Pizza className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="font-display font-bold text-lg text-lc-gray-900">
              Little Caesars
            </h1>
            <p className="text-xs text-lc-gray-500">Reports</p>
          </div>
        </Link>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4">
        <ul className="space-y-1">
          {navItems.map((item) => {
            const isActive = pathname === item.href;
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className={clsx(
                    'flex items-center gap-3 px-6 py-3 transition-colors',
                    isActive
                      ? 'bg-lc-orange-50 text-lc-orange-500 border-r-4 border-lc-orange-500'
                      : 'text-lc-gray-600 hover:bg-lc-orange-50 hover:text-lc-orange-500'
                  )}
                >
                  {item.icon}
                  <span className="font-medium">{item.label}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Bottom section */}
      <div className="p-4 border-t border-lc-gray-100">
        <Link
          href="/settings"
          className="flex items-center gap-3 px-4 py-2 text-lc-gray-600 hover:bg-lc-gray-50 rounded-lg transition-colors"
        >
          <Settings className="w-5 h-5" />
          <span className="font-medium">Configuracion</span>
        </Link>
        {onLogout && (
          <button
            onClick={onLogout}
            className="flex items-center gap-3 px-4 py-2 text-lc-gray-600 hover:bg-red-50 hover:text-error rounded-lg transition-colors w-full mt-1"
          >
            <LogOut className="w-5 h-5" />
            <span className="font-medium">Cerrar Sesion</span>
          </button>
        )}
      </div>
    </aside>
  );
}
