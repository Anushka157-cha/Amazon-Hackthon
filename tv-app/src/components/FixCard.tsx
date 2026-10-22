import React from 'react';
import { ProposalInfo } from '../api/types';

interface FixCardProps {
  proposal: ProposalInfo | null;
  focusedButton: 'approve' | 'cancel' | 'undo' | 'inject' | 'clear' | null;
  isExecuting: boolean;
  statusMessage: string | null;
  showUndo: boolean;
  onApprove: () => void;
  onCancel: () => void;
  onUndo: () => void;
  onInjectTestFailure: () => void;
  onClearFailures: () => void;
}

export const FixCard: React.FC<FixCardProps> = ({
  proposal,
  focusedButton,
  isExecuting,
  statusMessage,
  showUndo,
  onApprove,
  onCancel,
  onUndo,
  onInjectTestFailure,
  onClearFailures,
}) => {
  const hasProposal = proposal?.has_proposal ?? false;
  const tier = proposal?.tier || 'MEDIUM';

  return (
    <div className="tv-action-area">
      {isExecuting ? (
        <div className="verification-box">
          <div className="spinner" />
          <div>
            <div style={{ fontSize: '18px', fontWeight: 700 }}>
              Executing Fix & Verifying Stabilization...
            </div>
            <div style={{ fontSize: '14px', color: '#94A3B8', marginTop: '4px' }}>
              Checking all 5 simulated devices across 3 consecutive health ticks.
            </div>
          </div>
        </div>
      ) : hasProposal ? (
        <div className="fix-card">
          <div className="fix-details">
            <div className="fix-title">
              <span>🔧 Proposed Action: {proposal?.proposed_fix || 'Restart Wi-Fi Extender'}</span>
              <span className={`impact-badge impact-${tier}`}>
                IMPACT: {tier} ({proposal?.duration_seconds || 60}s)
              </span>
            </div>
            <p className="fix-description">
              {proposal?.impact?.description ||
                `Restarting will temporarily disconnect ${proposal?.devices_affected?.length || 4} devices. Alexa+ requires explicit approval.`}
            </p>
          </div>

          <div className="fix-buttons">
            <button
              type="button"
              className={`tv-btn tv-btn-primary ${focusedButton === 'approve' ? 'focused' : ''}`}
              onClick={onApprove}
            >
              <span>✅ Approve Fix</span>
              <span style={{ fontSize: '12px', opacity: 0.8 }}>(Press [OK])</span>
            </button>

            <button
              type="button"
              className={`tv-btn tv-btn-secondary ${focusedButton === 'cancel' ? 'focused' : ''}`}
              onClick={onCancel}
            >
              <span>❌ Cancel</span>
            </button>
          </div>
        </div>
      ) : (
        <div className="fix-card" style={{ justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontSize: '17px', fontWeight: 700 }}>
              {statusMessage || 'System Operating Normally'}
            </div>
            <div style={{ fontSize: '14px', color: '#94A3B8', marginTop: '2px' }}>
              {showUndo
                ? 'Fix executed and verified. Snapshot saved for instant rollback.'
                : 'Say "Alexa, check my home" or inject a simulated outage below to test.'}
            </div>
          </div>

          <div style={{ display: 'flex', gap: '14px' }}>
            {showUndo && (
              <button
                type="button"
                className={`tv-btn tv-btn-undo ${focusedButton === 'undo' ? 'focused' : ''}`}
                onClick={onUndo}
              >
                <span>↩️ Undo Fix (Rollback)</span>
              </button>
            )}

            <button
              type="button"
              className={`tv-btn tv-btn-secondary ${focusedButton === 'inject' ? 'focused' : ''}`}
              onClick={onInjectTestFailure}
            >
              <span>⚡ Test Outage (Drop Extender)</span>
            </button>

            <button
              type="button"
              className={`tv-btn tv-btn-secondary ${focusedButton === 'clear' ? 'focused' : ''}`}
              onClick={onClearFailures}
            >
              <span>✨ Clear Outages</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
