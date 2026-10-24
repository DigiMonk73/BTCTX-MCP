import React from 'react';
import './styles/app.css';
import './styles/errorBoundary.css';
import { Routes, Route, Navigate } from 'react-router-dom';

// Layout and routing
import AppLayout from './components/AppLayout';
import PrivateRoute from './components/PrivateRoute';
import ErrorBoundary from './components/ErrorBoundary';
import PrereleaseBanner from './components/PrereleaseBanner';

// Pages
import Dashboard from './pages/Dashboard';
import Transactions from './pages/Transactions';
import Reports from './pages/Reports';
import Settings from './pages/Settings';
import LoginPage from './pages/Login';
import LogoutPage from './pages/Logout';
import RegisterPage from './pages/Register';

// Components
import TransactionForm from './components/TransactionForm';
import ToastContainer from './components/ToastContainer';

// Context providers
import { ToastProvider } from './contexts/ToastContext';

/**
 * The app's pages. All but login, logout and registration need a signed-in
 * user (PrivateRoute); any other address goes to the dashboard. Above each,
 * a pre-release's banner (#670), outside the error boundary so a page that
 * fails still says which version it is.
 */
const App: React.FC = () => {
  return (
    <div className="app-shell">
      <PrereleaseBanner />
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
            <Route path="/logout" element={<LogoutPage />} />
            <Route path="/register" element={<RegisterPage />} />

            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>

          <ToastContainer position="top-right" />
        </ToastProvider>
      </ErrorBoundary>
    </div>
  );
};

export default App;
