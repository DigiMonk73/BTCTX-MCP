import React from 'react';
import { useToast } from '../contexts/useToast';
import Toast from './Toast';
import '../styles/toast.css';

interface ToastContainerProps {
  position?: 'top-right' | 'top-left' | 'bottom-right' | 'bottom-left' | 'top-center' | 'bottom-center';
}

export function ToastContainer({ position = 'top-right' }: ToastContainerProps) {
  const { toasts, removeToast } = useToast();

  if (toasts.length === 0) {
    return null;
  }

  return (
    <div className={`toast-container toast-${position}`} aria-live="polite">
      {toasts.map((toast) => (
        <Toast key={toast.id} toast={toast} onDismiss={removeToast} />
      ))}
    </div>
  );
}

export default ToastContainer;
