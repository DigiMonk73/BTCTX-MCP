import React from 'react';
import Sidebar from './Sidebar';
import Header from './Header';
import PortBanner from './PortBanner';
import PriceSourcePrompt from './PriceSourcePrompt';

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
        <PriceSourcePrompt />

        <main className="main-content">
          {children}
        </main>
      </div>
    </div>
  );
};

export default AppLayout;
