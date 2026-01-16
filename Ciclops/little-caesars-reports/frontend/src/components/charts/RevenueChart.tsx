/**
 * Revenue Chart Component
 * Elena: "Grafica de ventas con los colores de Little Caesars"
 */
'use client';

import React from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import { Card, CardHeader } from '../ui/Card';
import { BarChart3 } from 'lucide-react';

interface RevenueData {
  name: string;
  mostrador: number;
  delivery: number;
  app: number;
}

interface RevenueChartProps {
  data: RevenueData[];
  title?: string;
}

const formatCurrency = (value: number) => {
  return new Intl.NumberFormat('es-MX', {
    style: 'currency',
    currency: 'MXN',
    minimumFractionDigits: 0,
  }).format(value);
};

export function RevenueChart({ data, title = 'Ventas por Canal' }: RevenueChartProps) {
  return (
    <Card>
      <CardHeader
        title={title}
        icon={<BarChart3 className="w-5 h-5" />}
      />
      <div className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#E5E5E5" />
            <XAxis
              dataKey="name"
              tick={{ fill: '#737373', fontSize: 12 }}
              axisLine={{ stroke: '#E5E5E5' }}
            />
            <YAxis
              tick={{ fill: '#737373', fontSize: 12 }}
              axisLine={{ stroke: '#E5E5E5' }}
              tickFormatter={(value) => `$${(value / 1000).toFixed(0)}k`}
            />
            <Tooltip
              formatter={(value: number) => formatCurrency(value)}
              contentStyle={{
                backgroundColor: '#FFFFFF',
                border: '1px solid #E5E5E5',
                borderRadius: '8px',
                boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
              }}
            />
            <Legend />
            <Bar
              dataKey="mostrador"
              name="Mostrador"
              fill="#F15A22"
              radius={[4, 4, 0, 0]}
            />
            <Bar
              dataKey="delivery"
              name="Delivery"
              fill="#FF8A54"
              radius={[4, 4, 0, 0]}
            />
            <Bar
              dataKey="app"
              name="App"
              fill="#FFCBB0"
              radius={[4, 4, 0, 0]}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
