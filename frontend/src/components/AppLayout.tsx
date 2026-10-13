import React from 'react';
import Sidebar from './Sidebar';
import Header from './Header';
import PortBanner from './PortBanner';

interface LayoutProps {
  children: React.ReactNode;
}

const AppLayout: React.FC<LayoutProps> = ({ children }) => {
  return (
    <div className="app-container">
      <Sidebar />

      <div className="content-area">
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
