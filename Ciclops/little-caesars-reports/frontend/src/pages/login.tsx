/**
 * Login Page
 * Elena: "Pagina de login minimalista con el estilo Little Caesars"
 */
'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Pizza, Mail, Lock, Eye, EyeOff } from 'lucide-react';
import { Button, Input, Alert } from '../components/ui';
import { firebaseAuth } from '../services/firebase';
import { authAPI } from '../services/api';

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await firebaseAuth.loginWithEmail(email, password);
      router.push('/dashboard');
    } catch (err: any) {
      console.error('Login error:', err);
      if (err.code === 'auth/user-not-found') {
        setError('No existe una cuenta con este correo');
      } else if (err.code === 'auth/wrong-password') {
        setError('Contrasena incorrecta');
      } else if (err.code === 'auth/invalid-email') {
        setError('Correo electronico invalido');
      } else {
        setError('Error al iniciar sesion. Intenta de nuevo.');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleLogin = async () => {
    setError('');
    setLoading(true);

    try {
      const user = await firebaseAuth.loginWithGoogle();
      // Verificar si es nuevo usuario
      if (user.metadata.creationTime === user.metadata.lastSignInTime) {
        // Nuevo usuario, crear perfil
        await authAPI.setupProfile({
          display_name: user.displayName || 'Usuario',
        });
      }
      router.push('/dashboard');
    } catch (err: any) {
      console.error('Google login error:', err);
      setError('Error al iniciar sesion con Google');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-lc-orange-50 to-white flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center p-4 bg-lc-orange-500 rounded-2xl mb-4">
            <Pizza className="w-12 h-12 text-white" />
          </div>
          <h1 className="text-2xl font-display font-bold text-lc-gray-900">
            Little Caesars Reports
          </h1>
          <p className="text-lc-gray-500 mt-2">
            Inicia sesion para continuar
          </p>
        </div>

        {/* Form */}
        <div className="bg-white rounded-2xl shadow-lg p-8">
          {error && (
            <Alert type="error" message={error} className="mb-6" />
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <Input
              label="Correo electronico"
              type="email"
              placeholder="tu@email.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              icon={<Mail className="w-5 h-5" />}
              required
            />

            <div className="relative">
              <Input
                label="Contrasena"
                type={showPassword ? 'text' : 'password'}
                placeholder="********"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                icon={<Lock className="w-5 h-5" />}
                required
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-9 text-lc-gray-400 hover:text-lc-gray-600"
              >
                {showPassword ? (
                  <EyeOff className="w-5 h-5" />
                ) : (
                  <Eye className="w-5 h-5" />
                )}
              </button>
            </div>

            <div className="flex items-center justify-between text-sm">
              <label className="flex items-center gap-2">
                <input type="checkbox" className="rounded border-lc-gray-300" />
                <span className="text-lc-gray-600">Recordarme</span>
              </label>
              <Link
                href="/forgot-password"
                className="text-lc-orange-500 hover:text-lc-orange-600"
              >
                Olvide mi contrasena
              </Link>
            </div>

            <Button
              type="submit"
              className="w-full"
              loading={loading}
            >
              Iniciar Sesion
            </Button>
          </form>

          <div className="relative my-6">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-lc-gray-200" />
            </div>
            <div className="relative flex justify-center text-sm">
              <span className="px-2 bg-white text-lc-gray-500">o continua con</span>
            </div>
          </div>

          <Button
            type="button"
            variant="secondary"
            className="w-full"
            onClick={handleGoogleLogin}
            disabled={loading}
          >
            <svg className="w-5 h-5 mr-2" viewBox="0 0 24 24">
              <path
                fill="currentColor"
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
              />
              <path
                fill="currentColor"
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
              />
              <path
                fill="currentColor"
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
              />
              <path
                fill="currentColor"
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
              />
            </svg>
            Google
          </Button>

          <p className="text-center text-sm text-lc-gray-500 mt-6">
            No tienes cuenta?{' '}
            <Link
              href="/register"
              className="text-lc-orange-500 hover:text-lc-orange-600 font-medium"
            >
              Registrate aqui
            </Link>
          </p>
        </div>

        {/* Footer */}
        <p className="text-center text-xs text-lc-gray-400 mt-8">
          Little Caesars Reports v1.0
        </p>
      </div>
    </div>
  );
}
