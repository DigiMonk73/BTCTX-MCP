import React from 'react';
import './styles/app.css';
import './styles/errorBoundary.css';
import { Routes, Route, Navigate } from 'react-router-dom';

// Layout and routing
import AppLayout from './components/AppLayout';
import PrivateRoute from './components/PrivateRoute';
import ErrorBoundary from './components/ErrorBoundary';

// Pages
import Dashboard from './pages/Dashboard';
import Transactions from './pages/Transactions';
import Reports from './pages/Reports';
import Settings from './pages/Settings';
import LoginPage from './pages/Login';
import RegisterPage from './pages/Register';

// Components
import TransactionForm from './components/TransactionForm';
import ToastContainer from './components/ToastContainer';

// Context providers
import { ToastProvider } from './contexts/ToastContext';

/**
 * The app's pages. All but login and registration need a signed-in user
 * (PrivateRoute); any other address goes to the dashboard.
 */
const App: React.FC = () => {
  return (
    <ErrorBoundary>
      <ToastProvider>
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />

          <Route
            path="/dashboard"
            element={
              <PrivateRoute>
                <AppLayout>
                  <Dashboard />
                </AppLayout>
              </PrivateRoute>
            }
          />
          <Route
            path="/transactions"
            element={
              <PrivateRoute>
                <AppLayout>
                  <Transactions />
                </AppLayout>
              </PrivateRoute>
            }
          />
          <Route
            path="/transactions/new"
            element={
              <PrivateRoute>
                <AppLayout>
                  <TransactionForm />
                </AppLayout>
              </PrivateRoute>
            }
          />
          <Route
            path="/reports"
            element={
              <PrivateRoute>
                <AppLayout>
                  <Reports />
                </AppLayout>
              </PrivateRoute>
            }
          />
          <Route
            path="/settings"
            element={
              <PrivateRoute>
                <AppLayout>
                  <Settings />
                </AppLayout>
              </PrivateRoute>
            }
          />

          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />

          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>

        <ToastContainer position="top-right" />
      </ToastProvider>
    </ErrorBoundary>
  );
};

export default App;
