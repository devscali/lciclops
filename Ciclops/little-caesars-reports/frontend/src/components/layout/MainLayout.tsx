/**
 * Main Layout Component
 * Elena: "Layout principal con sidebar y header"
 */
'use client';

import React from 'react';
import { Sidebar } from './Sidebar';
import { Header } from './Header';

interface MainLayoutProps {
  children: React.ReactNode;
  title: string;
  subtitle?: string;
  user?: {
    name: string;
    email: string;
  };
  alertCount?: number;
  onLogout?: () => void;
}

export function MainLayout({
  children,
  title,
  subtitle,
  user,
  alertCount,
  onLogout,
}: MainLayoutProps) {
  return (
    <div className="min-h-screen bg-lc-gray-50">
      <Sidebar onLogout={onLogout} />
      <div className="ml-64">
        <Header
          title={title}
          subtitle={subtitle}
          user={user}
          alertCount={alertCount}
        />
        <main className="p-8">{children}</main>
      </div>
    </div>
  );
}
