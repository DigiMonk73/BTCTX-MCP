// src/components/AppLayout.tsx
import React from 'react';
import Sidebar from './Sidebar';
import Header from './Header';
import PortBanner from './PortBanner';

interface LayoutProps {
  children: React.ReactNode; // The main page content
}

const AppLayout: React.FC<LayoutProps> = ({ children }) => {
  return (
    <div className="app-container">
      {/* Sidebar on the left, full height */}
      <Sidebar />

      {/* Content area on the right */}
      <div className="content-area">
        {/* Header is just a nav bar, no pageTitle passed */}
        <Header />
        <PortBanner />

        <main className="main-content">
          {children}
        </main>
      </div>
    </div>
  );
};

export default AppLayout;
