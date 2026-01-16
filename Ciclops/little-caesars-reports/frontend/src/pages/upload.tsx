/**
 * Upload Page
 * Elena: "Pagina para subir documentos, bonita y funcional"
 */
'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { FileText, CheckCircle, AlertCircle, ArrowRight } from 'lucide-react';
import { MainLayout } from '../components/layout';
import { Card, CardHeader, DropZone, Button, Alert } from '../components/ui';
import { documentsAPI } from '../services/api';

interface ProcessingResult {
  success: boolean;
  documentId?: string;
  type?: string;
  confidence?: number;
  extractedData?: any;
  error?: string;
}

export default function UploadPage() {
  const router = useRouter();
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [result, setResult] = useState<ProcessingResult | null>(null);

  const handleFileSelect = async (file: File) => {
    setUploading(true);
    setUploadProgress(0);
    setResult(null);

    try {
      // Simular progreso
      const progressInterval = setInterval(() => {
        setUploadProgress((prev) => {
          if (prev >= 90) {
            clearInterval(progressInterval);
            return prev;
          }
          return prev + 10;
        });
      }, 200);

      // Subir archivo
      const response = await documentsAPI.upload(file);

      clearInterval(progressInterval);
      setUploadProgress(100);

      setResult({
        success: true,
        documentId: response.data.id,
        type: response.data.type,
        confidence: response.data.confidence,
        extractedData: response.data,
      });
    } catch (err: any) {
      console.error('Upload error:', err);
      setResult({
        success: false,
        error: err.response?.data?.detail || 'Error al procesar el documento',
      });
    } finally {
      setUploading(false);
    }
  };

  const handleViewDocument = () => {
    if (result?.documentId) {
      router.push(`/documents/${result.documentId}`);
    }
  };

  const handleUploadAnother = () => {
    setResult(null);
    setUploadProgress(0);
  };

  return (
    <MainLayout
      title="Subir Documento"
      subtitle="Sube tus estados financieros, facturas o reportes"
      user={{ name: 'Usuario', email: 'usuario@littlecaesars.com' }}
    >
      <div className="max-w-2xl mx-auto">
        <Card>
          <CardHeader
            title="Subir Documento"
            subtitle="Julia procesara el documento automaticamente"
            icon={<FileText className="w-5 h-5" />}
          />

          {!result ? (
            <>
              <DropZone
                onFileSelect={handleFileSelect}
                uploading={uploading}
                uploadProgress={uploadProgress}
                className="mb-6"
              />

              <div className="border-t border-lc-gray-100 pt-6">
                <h4 className="font-medium text-lc-gray-900 mb-3">
                  Tipos de documentos soportados:
                </h4>
                <ul className="space-y-2 text-sm text-lc-gray-600">
                  <li className="flex items-center gap-2">
                    <CheckCircle className="w-4 h-4 text-success" />
                    Estados de cuenta bancarios
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle className="w-4 h-4 text-success" />
                    Facturas de proveedores (CFDI)
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle className="w-4 h-4 text-success" />
                    Reportes de ventas diarios
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle className="w-4 h-4 text-success" />
                    Inventarios y stock
                  </li>
                </ul>
              </div>
            </>
          ) : (
            <div className="text-center py-8">
              {result.success ? (
                <>
                  <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
                    <CheckCircle className="w-8 h-8 text-success" />
                  </div>
                  <h3 className="text-xl font-semibold text-lc-gray-900 mb-2">
                    Documento Procesado
                  </h3>
                  <p className="text-lc-gray-500 mb-2">
                    Tipo detectado:{' '}
                    <span className="font-medium text-lc-gray-900">
                      {result.type?.replace('_', ' ').toUpperCase()}
                    </span>
                  </p>
                  <p className="text-lc-gray-500 mb-6">
                    Confianza:{' '}
                    <span className="font-medium text-lc-gray-900">
                      {((result.confidence || 0) * 100).toFixed(0)}%
                    </span>
                  </p>

                  {/* Preview de datos extraidos */}
                  {result.extractedData && (
                    <div className="bg-lc-gray-50 rounded-lg p-4 mb-6 text-left">
                      <h4 className="font-medium text-lc-gray-900 mb-2">
                        Datos extraidos:
                      </h4>
                      <pre className="text-xs text-lc-gray-600 overflow-auto max-h-40">
                        {JSON.stringify(result.extractedData, null, 2)}
                      </pre>
                    </div>
                  )}

                  <div className="flex gap-3 justify-center">
                    <Button
                      variant="primary"
                      onClick={handleViewDocument}
                      icon={<ArrowRight className="w-4 h-4" />}
                    >
                      Ver Documento
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={handleUploadAnother}
                    >
                      Subir Otro
                    </Button>
                  </div>
                </>
              ) : (
                <>
                  <div className="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-4">
                    <AlertCircle className="w-8 h-8 text-error" />
                  </div>
                  <h3 className="text-xl font-semibold text-lc-gray-900 mb-2">
                    Error al Procesar
                  </h3>
                  <Alert
                    type="error"
                    message={result.error || 'Error desconocido'}
                    className="mb-6"
                  />
                  <Button
                    variant="primary"
                    onClick={handleUploadAnother}
                  >
                    Intentar de Nuevo
                  </Button>
                </>
              )}
            </div>
          )}
        </Card>

        {/* Tips */}
        <Card className="mt-6">
          <h4 className="font-medium text-lc-gray-900 mb-3">
            Tips para mejores resultados:
          </h4>
          <ul className="space-y-2 text-sm text-lc-gray-600">
            <li>
              Asegurate de que el documento sea legible y no este borroso
            </li>
            <li>
              Si es un PDF escaneado, usa una resolucion de al menos 300 DPI
            </li>
            <li>
              Los documentos en espanol tienen mejor precision
            </li>
            <li>
              Evita documentos con marcas de agua muy oscuras
            </li>
          </ul>
        </Card>
      </div>
    </MainLayout>
  );
}
