import React from 'react';

interface HeaderProps {
  lastUpdated?: string;
  isBackendConnected: boolean;
}

export const Header: React.FC<HeaderProps> = ({ isBackendConnected }) => {
  return (
    <header className="tv-header">
      <div className="tv-title-area">
        <div className="tv-logo-badge">🛡️ HG</div>
        <div>
          <h1 className="tv-app-title">HomeGuard TV</h1>
          <p className="tv-tagline">Conversational Smart Home Self-Healing</p>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            fontSize: '13px',
            color: isBackendConnected ? '#10B981' : '#EF4444',
            fontWeight: 600,
          }}
        >
          <span
            style={{
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              backgroundColor: isBackendConnected ? '#10B981' : '#EF4444',
              boxShadow: isBackendConnected
                ? '0 0 8px #10B981'
                : '0 0 8px #EF4444',
            }}
          />
          {isBackendConnected ? 'LIVE SYNC (2s)' : 'DISCONNECTED'}
        </div>

        {/* Mandatory Hackathon Badge */}
        <div className="simulated-badge">⚠️ SIMULATED DEVICES</div>
      </div>
    </header>
  );
};
