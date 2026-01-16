/**
 * Dashboard Page
 * Elena: "El dashboard principal con las metricas importantes"
 */
'use client';

import React, { useEffect, useState } from 'react';
import {
  DollarSign,
  TrendingUp,
  Receipt,
  AlertTriangle,
  Upload,
} from 'lucide-react';
import { MainLayout } from '../components/layout';
import { KPICard, Card, CardHeader, AlertList, Button } from '../components/ui';
import { RevenueChart, ExpensePieChart } from '../components/charts';
import { reportsAPI } from '../services/api';
import Link from 'next/link';

interface DashboardData {
  current_period: string;
  total_revenue: number;
  net_margin: number;
  net_profit: number;
  revenue_trend: string;
  alerts: Array<{ type: string; message: string; severity: string }>;
  revenue_by_channel: Record<string, number>;
  expenses_breakdown: Record<string, number>;
  message?: string;
}

export default function DashboardPage() {
  const [dashboardData, setDashboardData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Datos de ejemplo para las graficas
  const revenueChartData = [
    { name: 'Lun', mostrador: 12000, delivery: 8000, app: 3000 },
    { name: 'Mar', mostrador: 15000, delivery: 9000, app: 4000 },
    { name: 'Mie', mostrador: 13000, delivery: 7500, app: 3500 },
    { name: 'Jue', mostrador: 14000, delivery: 8500, app: 4500 },
    { name: 'Vie', mostrador: 20000, delivery: 12000, app: 6000 },
    { name: 'Sab', mostrador: 25000, delivery: 15000, app: 8000 },
    { name: 'Dom', mostrador: 18000, delivery: 10000, app: 5000 },
  ];

  useEffect(() => {
    loadDashboardData();
  }, []);

  const loadDashboardData = async () => {
    try {
      setLoading(true);
      const response = await reportsAPI.getDashboard();
      setDashboardData(response.data);
    } catch (err: any) {
      console.error('Error loading dashboard:', err);
      // Usar datos de ejemplo si falla el API
      setDashboardData({
        current_period: new Date().toISOString().slice(0, 7),
        total_revenue: 230000,
        net_margin: 18.5,
        net_profit: 42550,
        revenue_trend: '+15%',
        alerts: [
          { type: 'warning', message: 'El costo de luz subio 40% vs mes pasado', severity: 'warning' },
          { type: 'info', message: 'Stock de queso esta bajo, considera reordenar', severity: 'info' },
        ],
        revenue_by_channel: {
          Mostrador: 150000,
          Delivery: 60000,
          App: 20000,
        },
        expenses_breakdown: {
          Nomina: 45000,
          Renta: 25000,
          Servicios: 15000,
          Marketing: 5000,
          Otros: 8000,
        },
      });
    } finally {
      setLoading(false);
    }
  };

  const expenseData = dashboardData
    ? Object.entries(dashboardData.expenses_breakdown).map(([name, value]) => ({
        name,
        value,
      }))
    : [];

  const alerts = dashboardData?.alerts.map((alert, index) => ({
    id: String(index),
    type: alert.severity as 'info' | 'warning' | 'error' | 'success',
    message: alert.message,
  })) || [];

  // Determinar direccion de tendencia
  const trendDirection = dashboardData?.revenue_trend?.startsWith('+')
    ? 'up'
    : dashboardData?.revenue_trend?.startsWith('-')
    ? 'down'
    : 'neutral';

  return (
    <MainLayout
      title="Dashboard"
      subtitle={`Periodo: ${dashboardData?.current_period || 'Cargando...'}`}
      user={{ name: 'Usuario', email: 'usuario@littlecaesars.com' }}
      alertCount={alerts.length}
    >
      {/* KPIs */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <KPICard
          label="Ventas Totales"
          value={dashboardData?.total_revenue || 0}
          format="currency"
          trend={dashboardData?.revenue_trend}
          trendDirection={trendDirection}
          icon={<DollarSign className="w-5 h-5" />}
        />
        <KPICard
          label="Margen Neto"
          value={dashboardData?.net_margin || 0}
          format="percentage"
          icon={<TrendingUp className="w-5 h-5" />}
        />
        <KPICard
          label="Utilidad Neta"
          value={dashboardData?.net_profit || 0}
          format="currency"
          icon={<Receipt className="w-5 h-5" />}
        />
        <KPICard
          label="Alertas"
          value={alerts.length}
          format="number"
          icon={<AlertTriangle className="w-5 h-5" />}
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        <RevenueChart data={revenueChartData} />
        <ExpensePieChart data={expenseData} />
      </div>

      {/* Alerts & Quick Actions */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Alerts */}
        <Card>
          <CardHeader
            title="Alertas"
            subtitle={`${alerts.length} alertas activas`}
            icon={<AlertTriangle className="w-5 h-5" />}
          />
          {alerts.length > 0 ? (
            <AlertList alerts={alerts} />
          ) : (
            <p className="text-lc-gray-500 text-center py-8">
              No hay alertas pendientes
            </p>
          )}
        </Card>

        {/* Quick Actions */}
        <Card>
          <CardHeader
            title="Acciones Rapidas"
            subtitle="Sube documentos o genera reportes"
          />
          <div className="space-y-3">
            <Link href="/upload">
              <Button variant="primary" className="w-full justify-start" icon={<Upload className="w-5 h-5" />}>
                Subir Documento
              </Button>
            </Link>
            <Link href="/reports">
              <Button variant="secondary" className="w-full justify-start" icon={<Receipt className="w-5 h-5" />}>
                Ver Estado de Resultados
              </Button>
            </Link>
            <Link href="/reports?export=true">
              <Button variant="ghost" className="w-full justify-start" icon={<TrendingUp className="w-5 h-5" />}>
                Exportar Reporte
              </Button>
            </Link>
          </div>
        </Card>
      </div>

      {/* Empty State */}
      {dashboardData?.message && (
        <Card className="mt-8 text-center py-12">
          <div className="max-w-md mx-auto">
            <Upload className="w-16 h-16 text-lc-gray-300 mx-auto mb-4" />
            <h3 className="text-xl font-semibold text-lc-gray-900 mb-2">
              Bienvenido a Little Caesars Reports
            </h3>
            <p className="text-lc-gray-500 mb-6">{dashboardData.message}</p>
            <Link href="/upload">
              <Button variant="primary" icon={<Upload className="w-5 h-5" />}>
                Subir Primer Documento
              </Button>
            </Link>
          </div>
        </Card>
      )}
    </MainLayout>
  );
}
