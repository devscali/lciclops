/**
 * Alert Component
 * Elena: "Para mostrar alertas y notificaciones"
 */
import React from 'react';
import { clsx } from 'clsx';
import { AlertCircle, AlertTriangle, CheckCircle, Info, X } from 'lucide-react';

interface AlertProps {
  type?: 'info' | 'warning' | 'error' | 'success';
  title?: string;
  message: string;
  onClose?: () => void;
  className?: string;
}

export function Alert({
  type = 'info',
  title,
  message,
  onClose,
  className,
}: AlertProps) {
  const styles = {
    info: {
      bg: 'bg-blue-50',
      border: 'border-blue-200',
      text: 'text-blue-800',
      icon: Info,
    },
    warning: {
      bg: 'bg-amber-50',
      border: 'border-amber-200',
      text: 'text-amber-800',
      icon: AlertTriangle,
    },
    error: {
      bg: 'bg-red-50',
      border: 'border-red-200',
      text: 'text-red-800',
      icon: AlertCircle,
    },
    success: {
      bg: 'bg-green-50',
      border: 'border-green-200',
      text: 'text-green-800',
      icon: CheckCircle,
    },
  };

  const { bg, border, text, icon: Icon } = styles[type];

  return (
    <div
      className={clsx(
        'p-4 rounded-lg border flex items-start gap-3',
        bg,
        border,
        text,
        className
      )}
    >
      <Icon className="w-5 h-5 flex-shrink-0 mt-0.5" />
      <div className="flex-1">
        {title && (
          <h4 className="font-semibold mb-1">{title}</h4>
        )}
        <p className="text-sm">{message}</p>
      </div>
      {onClose && (
        <button
          onClick={onClose}
          className="flex-shrink-0 p-1 hover:bg-black/5 rounded"
        >
          <X className="w-4 h-4" />
        </button>
      )}
    </div>
  );
}

interface AlertListProps {
  alerts: Array<{
    type: 'info' | 'warning' | 'error' | 'success';
    message: string;
    id?: string;
  }>;
  onDismiss?: (id: string) => void;
}

export function AlertList({ alerts, onDismiss }: AlertListProps) {
  if (alerts.length === 0) return null;

  return (
    <div className="space-y-2">
      {alerts.map((alert, index) => (
        <Alert
          key={alert.id || index}
          type={alert.type}
          message={alert.message}
          onClose={onDismiss ? () => onDismiss(alert.id || String(index)) : undefined}
        />
      ))}
    </div>
  );
}
