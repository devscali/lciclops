/**
 * Firebase Client Service
 * Aurelia: "Configuracion de Firebase para el frontend"
 */
import { initializeApp, getApps, FirebaseApp } from 'firebase/app';
import {
  getAuth,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  signOut,
  onAuthStateChanged,
  User,
  GoogleAuthProvider,
  signInWithPopup,
  sendPasswordResetEmail,
} from 'firebase/auth';

const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
};

// Initialize Firebase
let app: FirebaseApp;
if (!getApps().length) {
  app = initializeApp(firebaseConfig);
} else {
  app = getApps()[0];
}

const auth = getAuth(app);
const googleProvider = new GoogleAuthProvider();

// === Auth Functions ===
export const firebaseAuth = {
  /**
   * Login con email y password
   */
  loginWithEmail: async (email: string, password: string) => {
    const userCredential = await signInWithEmailAndPassword(auth, email, password);
    const token = await userCredential.user.getIdToken();
    localStorage.setItem('authToken', token);
    return userCredential.user;
  },

  /**
   * Registro con email y password
   */
  registerWithEmail: async (email: string, password: string) => {
    const userCredential = await createUserWithEmailAndPassword(auth, email, password);
    const token = await userCredential.user.getIdToken();
    localStorage.setItem('authToken', token);
    return userCredential.user;
  },

  /**
   * Login con Google
   */
  loginWithGoogle: async () => {
    const userCredential = await signInWithPopup(auth, googleProvider);
    const token = await userCredential.user.getIdToken();
    localStorage.setItem('authToken', token);
    return userCredential.user;
  },

  /**
   * Cerrar sesion
   */
  logout: async () => {
    await signOut(auth);
    localStorage.removeItem('authToken');
  },

  /**
   * Enviar email de recuperacion de password
   */
  resetPassword: async (email: string) => {
    await sendPasswordResetEmail(auth, email);
  },

  /**
   * Obtener token actual
   */
  getToken: async () => {
    const user = auth.currentUser;
    if (user) {
      return user.getIdToken();
    }
    return null;
  },

  /**
   * Refrescar token
   */
  refreshToken: async () => {
    const user = auth.currentUser;
    if (user) {
      const token = await user.getIdToken(true);
      localStorage.setItem('authToken', token);
      return token;
    }
    return null;
  },

  /**
   * Suscribirse a cambios de autenticacion
   */
  onAuthChange: (callback: (user: User | null) => void) => {
    return onAuthStateChanged(auth, callback);
  },

  /**
   * Obtener usuario actual
   */
  getCurrentUser: () => auth.currentUser,
};

export { auth };
export default app;
