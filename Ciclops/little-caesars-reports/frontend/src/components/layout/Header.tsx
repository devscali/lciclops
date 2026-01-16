/**
 * Header Component
 * Elena: "Header con el usuario y notificaciones"
 */
'use client';

import React from 'react';
import { Bell, User, ChevronDown } from 'lucide-react';

interface HeaderProps {
  title: string;
  subtitle?: string;
  user?: {
    name: string;
    email: string;
  };
  alertCount?: number;
}

export function Header({ title, subtitle, user, alertCount = 0 }: HeaderProps) {
  return (
    <header className="bg-white border-b border-lc-gray-100 px-8 py-4">
      <div className="flex items-center justify-between">
        {/* Title */}
        <div>
          <h1 className="text-2xl font-display font-bold text-lc-gray-900">
            {title}
          </h1>
          {subtitle && (
            <p className="text-sm text-lc-gray-500 mt-1">{subtitle}</p>
          )}
        </div>

        {/* Right section */}
        <div className="flex items-center gap-4">
          {/* Notifications */}
          <button className="relative p-2 text-lc-gray-500 hover:bg-lc-gray-50 rounded-lg transition-colors">
            <Bell className="w-5 h-5" />
            {alertCount > 0 && (
              <span className="absolute top-1 right-1 w-4 h-4 bg-error text-white text-xs rounded-full flex items-center justify-center">
                {alertCount > 9 ? '9+' : alertCount}
              </span>
            )}
          </button>

          {/* User menu */}
          {user && (
            <button className="flex items-center gap-3 p-2 hover:bg-lc-gray-50 rounded-lg transition-colors">
              <div className="w-8 h-8 bg-lc-orange-100 rounded-full flex items-center justify-center">
                <User className="w-4 h-4 text-lc-orange-500" />
              </div>
              <div className="text-left">
                <p className="text-sm font-medium text-lc-gray-900">
                  {user.name}
                </p>
                <p className="text-xs text-lc-gray-500">{user.email}</p>
              </div>
              <ChevronDown className="w-4 h-4 text-lc-gray-400" />
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
