import React from 'react';

interface TvRemoteGuideProps {
  onDpadPress: (direction: 'up' | 'down' | 'left' | 'right' | 'select' | 'back') => void;
}

export const TvRemoteGuide: React.FC<TvRemoteGuideProps> = ({ onDpadPress }) => {
  return (
    <footer className="tv-footer">
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        <span>🎮 Fire TV D-Pad Controls:</span>
        <span>
          <span className="remote-hint-badge">▲ ▼ ◄ ►</span> Navigate
        </span>
        <span>
          <span className="remote-hint-badge">SELECT / ENTER</span> Confirm / Approve
        </span>
        <span>
          <span className="remote-hint-badge">BACK / ESC</span> Cancel / Undo
        </span>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
        <button
          type="button"
          style={{
            background: 'rgba(255, 255, 255, 0.08)',
            border: '1px solid rgba(255, 255, 255, 0.15)',
            color: 'white',
            borderRadius: '4px',
            padding: '2px 8px',
            fontSize: '11px',
            cursor: 'pointer',
          }}
          onClick={() => onDpadPress('left')}
        >
          ◄
        </button>
        <button
          type="button"
          style={{
            background: 'rgba(255, 255, 255, 0.08)',
            border: '1px solid rgba(255, 255, 255, 0.15)',
            color: 'white',
            borderRadius: '4px',
            padding: '2px 8px',
            fontSize: '11px',
            cursor: 'pointer',
          }}
          onClick={() => onDpadPress('up')}
        >
          ▲
        </button>
        <button
          type="button"
          style={{
            background: 'rgba(255, 255, 255, 0.08)',
            border: '1px solid rgba(255, 255, 255, 0.15)',
            color: 'white',
            borderRadius: '4px',
            padding: '2px 8px',
            fontSize: '11px',
            cursor: 'pointer',
          }}
          onClick={() => onDpadPress('down')}
        >
          ▼
        </button>
        <button
          type="button"
          style={{
            background: 'rgba(255, 255, 255, 0.08)',
            border: '1px solid rgba(255, 255, 255, 0.15)',
            color: 'white',
            borderRadius: '4px',
            padding: '2px 8px',
            fontSize: '11px',
            cursor: 'pointer',
          }}
          onClick={() => onDpadPress('right')}
        >
          ►
        </button>
        <button
          type="button"
          style={{
            background: '#2563EB',
            border: 'none',
            color: 'white',
            borderRadius: '4px',
            padding: '2px 8px',
            fontSize: '11px',
            fontWeight: 'bold',
            cursor: 'pointer',
          }}
          onClick={() => onDpadPress('select')}
        >
          SELECT
        </button>
      </div>
    </footer>
  );
};
