/**
 * DropZone Component
 * Elena: "Para subir archivos arrastrando o haciendo click"
 */
'use client';

import React, { useCallback, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { clsx } from 'clsx';
import { Upload, FileText, X, CheckCircle, Loader2 } from 'lucide-react';
import { Button } from './Button';

interface DropZoneProps {
  onFileSelect: (file: File) => void;
  accept?: Record<string, string[]>;
  maxSize?: number;
  uploading?: boolean;
  uploadProgress?: number;
  className?: string;
}

export function DropZone({
  onFileSelect,
  accept = {
    'application/pdf': ['.pdf'],
    'image/png': ['.png'],
    'image/jpeg': ['.jpg', '.jpeg'],
  },
  maxSize = 10 * 1024 * 1024, // 10MB
  uploading = false,
  uploadProgress = 0,
  className,
}: DropZoneProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);

  const onDrop = useCallback(
    (acceptedFiles: File[], rejectedFiles: any[]) => {
      setError(null);

      if (rejectedFiles.length > 0) {
        const rejection = rejectedFiles[0];
        if (rejection.errors[0]?.code === 'file-too-large') {
          setError(`El archivo es muy grande. Maximo: ${maxSize / 1024 / 1024}MB`);
        } else if (rejection.errors[0]?.code === 'file-invalid-type') {
          setError('Tipo de archivo no soportado. Usa PDF, PNG o JPG');
        } else {
          setError('Error al cargar el archivo');
        }
        return;
      }

      if (acceptedFiles.length > 0) {
        const file = acceptedFiles[0];
        setSelectedFile(file);
        onFileSelect(file);
      }
    },
    [onFileSelect, maxSize]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept,
    maxSize,
    multiple: false,
  });

  const clearFile = () => {
    setSelectedFile(null);
    setError(null);
  };

  return (
    <div className={className}>
      {!selectedFile ? (
        <div
          {...getRootProps()}
          className={clsx(
            'border-2 border-dashed rounded-card p-8 text-center cursor-pointer transition-all duration-200',
            isDragActive
              ? 'border-lc-orange-500 bg-lc-orange-50'
              : 'border-lc-gray-300 hover:border-lc-orange-500 hover:bg-lc-orange-50'
          )}
        >
          <input {...getInputProps()} />
          <Upload
            className={clsx(
              'w-12 h-12 mx-auto mb-4',
              isDragActive ? 'text-lc-orange-500' : 'text-lc-gray-400'
            )}
          />
          <p className="text-lg font-medium text-lc-gray-700 mb-2">
            {isDragActive
              ? 'Suelta el archivo aqui...'
              : 'Arrastra tu archivo aqui'}
          </p>
          <p className="text-sm text-lc-gray-500 mb-4">
            o haz click para seleccionar
          </p>
          <p className="text-xs text-lc-gray-400">
            PDF, PNG o JPG (max. {maxSize / 1024 / 1024}MB)
          </p>
        </div>
      ) : (
        <div className="border border-lc-gray-200 rounded-card p-4">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-lc-orange-50 rounded-lg">
              <FileText className="w-6 h-6 text-lc-orange-500" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="font-medium text-lc-gray-900 truncate">
                {selectedFile.name}
              </p>
              <p className="text-sm text-lc-gray-500">
                {(selectedFile.size / 1024).toFixed(1)} KB
              </p>
            </div>
            {uploading ? (
              <div className="flex items-center gap-2 text-lc-orange-500">
                <Loader2 className="w-5 h-5 animate-spin" />
                <span className="text-sm font-medium">{uploadProgress}%</span>
              </div>
            ) : (
              <>
                <CheckCircle className="w-5 h-5 text-success" />
                <button
                  onClick={clearFile}
                  className="p-1 hover:bg-lc-gray-100 rounded"
                >
                  <X className="w-5 h-5 text-lc-gray-400" />
                </button>
              </>
            )}
          </div>
          {uploading && (
            <div className="mt-3">
              <div className="h-2 bg-lc-gray-100 rounded-full overflow-hidden">
                <div
                  className="h-full bg-lc-orange-500 transition-all duration-300"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>
            </div>
          )}
        </div>
      )}
      {error && (
        <p className="mt-2 text-sm text-error">{error}</p>
      )}
    </div>
  );
}
