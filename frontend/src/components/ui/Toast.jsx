import React from 'react';
import { useApp } from '../../context/AppContext';

export const ToastContainer = () => {
  const { toasts, removeToast } = useApp();

  const icons = {
    success: '✓',
    error: '×',
    info: 'i',
  };

  return (
    <div className="toast-container" id="toastContainer">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`toast toast-${toast.type}`}
          onClick={() => removeToast(toast.id)}
          style={{ cursor: 'pointer' }}
        >
          <span>{icons[toast.type] || ''}</span> {toast.message}
        </div>
      ))}
    </div>
  );
};
