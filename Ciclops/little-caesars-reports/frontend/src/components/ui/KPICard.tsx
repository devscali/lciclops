/**
 * KPI Card Component
 * Elena: "Para mostrar las métricas importantes bien grandotas"
 */
import React from 'react';
import { clsx } from 'clsx';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { Card } from './Card';

interface KPICardProps {
  label: string;
  value: string | number;
  trend?: string;
  trendDirection?: 'up' | 'down' | 'neutral';
  icon?: React.ReactNode;
  format?: 'currency' | 'percentage' | 'number';
  className?: string;
}

export function KPICard({
  label,
  value,
  trend,
  trendDirection = 'neutral',
  icon,
  format = 'number',
  className,
}: KPICardProps) {
  const formatValue = (val: string | number) => {
    if (typeof val === 'string') return val;

    switch (format) {
      case 'currency':
        return new Intl.NumberFormat('es-MX', {
          style: 'currency',
          currency: 'MXN',
          minimumFractionDigits: 0,
          maximumFractionDigits: 0,
        }).format(val);
      case 'percentage':
        return `${val}%`;
      default:
        return new Intl.NumberFormat('es-MX').format(val);
    }
  };

  const TrendIcon = {
    up: TrendingUp,
    down: TrendingDown,
    neutral: Minus,
  }[trendDirection];

  const trendColors = {
    up: 'text-success',
    down: 'text-error',
    neutral: 'text-lc-gray-500',
  };

  return (
    <Card className={clsx('flex flex-col', className)}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm text-lc-gray-500 uppercase tracking-wide">
          {label}
        </span>
        {icon && (
          <div className="p-2 bg-lc-orange-50 rounded-lg text-lc-orange-500">
            {icon}
          </div>
        )}
      </div>
      <div className="flex items-end justify-between">
        <span className="text-3xl font-bold text-lc-gray-900 font-mono">
          {formatValue(value)}
        </span>
        {trend && (
          <div className={clsx('flex items-center gap-1 text-sm font-medium', trendColors[trendDirection])}>
            <TrendIcon className="w-4 h-4" />
            <span>{trend}</span>
          </div>
        )}
      </div>
    </Card>
  );
}
