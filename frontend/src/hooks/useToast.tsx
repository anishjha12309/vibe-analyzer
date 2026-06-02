import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react';
import type { Toast } from '../types/api';

interface ToastCtx {
  addToast: (message: string, type?: Toast['type']) => void;
}

const ToastContext = createContext<ToastCtx | null>(null);

const TOAST_ICONS: Record<Toast['type'], string> = {
  warning: '⚠',
  error: '✕',
  success: '✓',
  info: 'ℹ',
};

function ToastItem({ toast, onDone }: { toast: Toast; onDone: (id: string) => void }) {
  useEffect(() => {
    const t = setTimeout(() => onDone(toast.id), 5000);
    return () => clearTimeout(t);
  }, [toast.id, onDone]);

  return (
    <div
      role="alert"
      onClick={() => onDone(toast.id)}
      className={`toast toast-${toast.type}`}
    >
      <span className="toast-icon">{TOAST_ICONS[toast.type]}</span>
      {toast.message}
    </div>
  );
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const remove = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  const addToast = useCallback((message: string, type: Toast['type'] = 'info') => {
    const id = Math.random().toString(36).slice(2);
    setToasts(prev => [...prev.slice(-4), { id, message, type }]);
  }, []);

  return (
    <ToastContext.Provider value={{ addToast }}>
      {children}
      <div className="toast-container">
        {toasts.map(t => (
          <ToastItem key={t.id} toast={t} onDone={remove} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastCtx {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used inside <ToastProvider>');
  return ctx;
}
