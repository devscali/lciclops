/**
 * API Service
 * Aurelia: "Cliente HTTP para comunicarse con el backend"
 */
import axios from 'axios';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export const api = axios.create({
  baseURL: `${API_BASE_URL}/api`,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Interceptor para agregar token de autenticacion
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('authToken');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Interceptor para manejar errores
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Token expirado o invalido
      localStorage.removeItem('authToken');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// === Auth API ===
export const authAPI = {
  setupProfile: (data: { display_name: string; franchise_id?: string }) =>
    api.post('/auth/setup-profile', data),

  getProfile: () => api.get('/auth/me'),

  updateProfile: (data: { display_name?: string; preferences?: object }) =>
    api.put('/auth/profile', data),
};

// === Documents API ===
export const documentsAPI = {
  upload: (file: File, documentType?: string) => {
    const formData = new FormData();
    formData.append('file', file);
    if (documentType) {
      formData.append('document_type', documentType);
    }
    return api.post('/documents/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
  },

  list: (params?: { page?: number; page_size?: number; status?: string; type?: string }) =>
    api.get('/documents', { params }),

  get: (documentId: string) => api.get(`/documents/${documentId}`),

  delete: (documentId: string) => api.delete(`/documents/${documentId}`),

  reprocess: (documentId: string) => api.post(`/documents/${documentId}/reprocess`),
};

// === Reports API ===
export const reportsAPI = {
  getDashboard: () => api.get('/reports/dashboard'),

  getPnL: (period?: string) => api.get('/reports/pnl', { params: { period } }),

  getSales: (startDate?: string, endDate?: string) =>
    api.get('/reports/sales', { params: { start_date: startDate, end_date: endDate } }),

  getInsights: (period?: string) => api.get('/reports/insights', { params: { period } }),

  export: (reportType: string, format: 'pdf' | 'excel', period?: string) =>
    api.post(
      '/reports/export',
      null,
      {
        params: { report_type: reportType, format, period },
        responseType: 'blob',
      }
    ),
};

export default api;
