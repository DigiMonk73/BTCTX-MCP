import { createContext, useContext } from 'react';
import type { ToastContextValue } from './ToastContext';

// Kept apart from ToastContext.tsx so that file exports only components
// (React Fast Refresh requirement).
export const ToastContext = createContext<ToastContextValue | undefined>(undefined);

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext);
  if (context === undefined) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
}
