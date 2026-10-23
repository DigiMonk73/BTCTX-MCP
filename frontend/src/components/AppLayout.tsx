import React, { useCallback, useRef } from 'react';
import Sidebar from './Sidebar';
import Header from './Header';
import PortBanner from './PortBanner';
import { ReportUnsavedChanges } from '../contexts/unsavedChanges';

interface LayoutProps {
  children: React.ReactNode;
}

const AppLayout: React.FC<LayoutProps> = ({ children }) => {
  // Read when Logout is pressed, not rendered: the panel sets it in the same
  // effects as its navigation blocker, so the two always agree (as state it
  // reached the header a render later, and Logout asked twice)
  const unsavedChanges = useRef(false);
  const reportUnsaved = useCallback((unsaved: boolean) => {
    unsavedChanges.current = unsaved;
  }, []);
  const hasUnsavedChanges = useCallback(() => unsavedChanges.current, []);

  return (
    <ReportUnsavedChanges.Provider value={reportUnsaved}>
      <div className="app-container">
        <Sidebar />

        <div className="content-area">
          <Header hasUnsavedChanges={hasUnsavedChanges} />
          <PortBanner />

          <main className="main-content">
            {children}
          </main>
        </div>
      </div>
    </ReportUnsavedChanges.Provider>
  );
};

export default AppLayout;
