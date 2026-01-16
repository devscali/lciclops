/**
 * Expense Pie Chart Component
 * Elena: "Grafica de pastel para ver la distribucion de gastos"
 */
'use client';

import React from 'react';
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
  Legend,
} from 'recharts';
import { Card, CardHeader } from '../ui/Card';
import { PieChart as PieChartIcon } from 'lucide-react';

interface ExpenseData {
  name: string;
  value: number;
}

interface ExpensePieChartProps {
  data: ExpenseData[];
  title?: string;
}

const COLORS = [
  '#F15A22', // Orange primary
  '#FF8A54', // Orange light
  '#FFCBB0', // Orange lighter
  '#737373', // Gray
  '#A3A3A3', // Gray light
  '#D4D4D4', // Gray lighter
];

const formatCurrency = (value: number) => {
  return new Intl.NumberFormat('es-MX', {
    style: 'currency',
    currency: 'MXN',
    minimumFractionDigits: 0,
  }).format(value);
};

export function ExpensePieChart({
  data,
  title = 'Distribucion de Gastos',
}: ExpensePieChartProps) {
  const total = data.reduce((sum, item) => sum + item.value, 0);

  return (
    <Card>
      <CardHeader
        title={title}
        icon={<PieChartIcon className="w-5 h-5" />}
      />
      <div className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              cx="50%"
              cy="50%"
              innerRadius={60}
              outerRadius={100}
              paddingAngle={2}
              dataKey="value"
              label={({ name, percent }) =>
                `${name} ${(percent * 100).toFixed(0)}%`
              }
              labelLine={false}
            >
              {data.map((_, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={COLORS[index % COLORS.length]}
                />
              ))}
            </Pie>
            <Tooltip
              formatter={(value: number) => [formatCurrency(value), 'Monto']}
              contentStyle={{
                backgroundColor: '#FFFFFF',
                border: '1px solid #E5E5E5',
                borderRadius: '8px',
                boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
              }}
            />
            <Legend
              formatter={(value, entry) => (
                <span className="text-sm text-lc-gray-700">{value}</span>
              )}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-4 pt-4 border-t border-lc-gray-100">
        <div className="flex justify-between items-center">
          <span className="text-sm text-lc-gray-500">Total</span>
          <span className="text-lg font-bold text-lc-gray-900 font-mono">
            {formatCurrency(total)}
          </span>
        </div>
      </div>
    </Card>
  );
}
