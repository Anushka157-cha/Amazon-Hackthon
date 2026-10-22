import React, { useEffect, useState, useCallback, useRef } from 'react';
import {
  DeviceInfo,
  DiagnosisInfo,
  ProposalInfo,
} from './api/types';
import {
  fetchStatus,
  fetchDiagnosis,
  fetchProposal,
  approveFix,
  rollbackFix,
  injectFailure,
  clearFailures,
} from './api/client';
import { Header } from './components/Header';
import { DiagnosisBanner } from './components/DiagnosisBanner';
import { HomeMap } from './components/HomeMap';
import { FixCard } from './components/FixCard';
import { TvRemoteGuide } from './components/TvRemoteGuide';
import './styles/tv.css';

type FocusTarget =
  | { type: 'device'; id: string }
  | { type: 'button'; id: 'approve' | 'cancel' | 'undo' | 'inject' };

export const App: React.FC = () => {
  // State
  const [devices, setDevices] = useState<Record<string, DeviceInfo>>({});
  const [diagnosis, setDiagnosis] = useState<DiagnosisInfo | null>(null);
  const [proposal, setProposal] = useState<ProposalInfo | null>(null);
  const [isBackendConnected, setIsBackendConnected] = useState<boolean>(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isExecuting, setIsExecuting] = useState<boolean>(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [showUndo, setShowUndo] = useState<boolean>(false);

  // Focus navigation state
  const [focus, setFocus] = useState<FocusTarget>({ type: 'button', id: 'inject' });

  // Refs for tracking in intervals/handlers
  const proposalRef = useRef<ProposalInfo | null>(null);
  proposalRef.current = proposal;

  const showUndoRef = useRef<boolean>(showUndo);
  showUndoRef.current = showUndo;

  // Poll backend every 2 seconds
  const pollBackend = useCallback(async () => {
    try {
      const [statusRes, diagRes, propRes] = await Promise.all([
        fetchStatus(),
        fetchDiagnosis(),
        fetchProposal(),
      ]);

      setDevices(statusRes.devices || {});
      setDiagnosis(diagRes);
      setProposal(propRes);
      setIsBackendConnected(true);
      setErrorMessage(null);

      // Auto-focus Approve button if a new proposal appears
      if (propRes.has_proposal && focus.type !== 'button') {
        setFocus({ type: 'button', id: 'approve' });
      }
    } catch (err: any) {
      setIsBackendConnected(false);
      setErrorMessage('⚠️ Unable to connect to HomeGuard backend at http://127.0.0.1:8000. Retrying in 2s...');
    }
  }, [focus.type]);

  useEffect(() => {
    pollBackend();
    const interval = setInterval(pollBackend, 2000);
    return () => clearInterval(interval);
  }, [pollBackend]);

  // Actions
  const handleApprove = async () => {
    if (isExecuting) return;
    setIsExecuting(true);
    setStatusMessage('Executing fix and verifying stabilization across 3 ticks...');

    try {
      const res = await approveFix(proposal?.incident_id || undefined, true);
      setIsExecuting(false);

      if (res.auto_rollback) {
        setStatusMessage('⚠️ Verification failed. Automatically rolled back to safe snapshot.');
        setShowUndo(false);
      } else if (res.verified) {
        setStatusMessage('✅ Everything is back! All devices stabilized across 3 checks.');
        setShowUndo(true);
        setFocus({ type: 'button', id: 'undo' });
      } else {
        setStatusMessage(res.message || 'Fix executed.');
        setShowUndo(true);
      }

      await pollBackend();
    } catch (err: any) {
      setIsExecuting(false);
      setStatusMessage(`Error executing fix: ${err.message}`);
    }
  };

  const handleCancel = async () => {
    try {
      await clearFailures();
      setStatusMessage('Fix proposal cancelled. No changes made.');
      setFocus({ type: 'button', id: 'inject' });
      await pollBackend();
    } catch (err: any) {
      setStatusMessage(`Error cancelling: ${err.message}`);
    }
  };

  const handleUndo = async () => {
    try {
      setIsExecuting(true);
      const res = await rollbackFix();
      setIsExecuting(false);
      setStatusMessage(res.spoken || 'Fix rolled back. Restored previous snapshot.');
      setShowUndo(false);
      setFocus({ type: 'button', id: 'inject' });
      await pollBackend();
    } catch (err: any) {
      setIsExecuting(false);
      setStatusMessage(`Error rolling back: ${err.message}`);
    }
  };

  const handleInjectTestFailure = async () => {
    try {
      setStatusMessage('Simulating outage: Wi-Fi Extender dropped offline...');
      await injectFailure('wifi_extender', 'offline');
      await pollBackend();
      setFocus({ type: 'button', id: 'approve' });
    } catch (err: any) {
      setStatusMessage(`Error injecting failure: ${err.message}`);
    }
  };

  // Spatial Navigation D-Pad Handler
  const handleDpad = useCallback(
    (action: 'up' | 'down' | 'left' | 'right' | 'select' | 'back') => {
      if (action === 'select') {
        if (focus.type === 'button') {
          if (focus.id === 'approve') handleApprove();
          else if (focus.id === 'cancel') handleCancel();
          else if (focus.id === 'undo') handleUndo();
          else if (focus.id === 'inject') handleInjectTestFailure();
        }
        return;
      }

      if (action === 'back') {
        if (proposalRef.current?.has_proposal) {
          handleCancel();
        } else if (showUndoRef.current) {
          handleUndo();
        }
        return;
      }

      // Directional navigation
      setFocus((current) => {
        const hasProposal = proposalRef.current?.has_proposal ?? false;
        const hasUndo = showUndoRef.current;

        if (action === 'down') {
          // Down always moves to the action card buttons
          if (hasProposal) return { type: 'button', id: 'approve' };
          if (hasUndo) return { type: 'button', id: 'undo' };
          return { type: 'button', id: 'inject' };
        }

        if (action === 'up') {
          // Up moves to the device graph
          return { type: 'device', id: 'wifi_extender' };
        }

        if (action === 'left') {
          if (current.type === 'button') {
            if (current.id === 'cancel') return { type: 'button', id: 'approve' };
            if (current.id === 'inject' && hasUndo) return { type: 'button', id: 'undo' };
          } else if (current.type === 'device') {
            if (['ring_doorbell', 'fire_tv', 'echo_speaker'].includes(current.id)) {
              return { type: 'device', id: 'wifi_extender' };
            }
            if (current.id === 'wifi_extender') {
              return { type: 'device', id: 'router' };
            }
          }
        }

        if (action === 'right') {
          if (current.type === 'button') {
            if (current.id === 'approve') return { type: 'button', id: 'cancel' };
            if (current.id === 'undo') return { type: 'button', id: 'inject' };
          } else if (current.type === 'device') {
            if (current.id === 'router') {
              return { type: 'device', id: 'wifi_extender' };
            }
            if (current.id === 'wifi_extender') {
              return { type: 'device', id: 'fire_tv' };
            }
          }
        }

        return current;
      });
    },
    []
  );

  // Keyboard navigation for TV remotes / browser testing
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Enter', 'Escape', 'Backspace'].includes(e.key)) {
        e.preventDefault();
      }
      switch (e.key) {
        case 'ArrowUp':
          handleDpad('up');
          break;
        case 'ArrowDown':
          handleDpad('down');
          break;
        case 'ArrowLeft':
          handleDpad('left');
          break;
        case 'ArrowRight':
          handleDpad('right');
          break;
        case 'Enter':
        case ' ':
          handleDpad('select');
          break;
        case 'Escape':
        case 'Backspace':
          handleDpad('back');
          break;
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [handleDpad]);

  return (
    <main className="tv-screen">
      {/* Backend connection warning banner */}
      {!isBackendConnected && errorMessage && (
        <div className="backend-error-bar">{errorMessage}</div>
      )}

      {/* Top Header */}
      <Header isBackendConnected={isBackendConnected} />

      {/* Diagnosis Banner */}
      <DiagnosisBanner diagnosis={diagnosis} />

      {/* Home Map Graph */}
      <HomeMap
        devices={devices}
        diagnosis={diagnosis}
        focusedDeviceId={focus.type === 'device' ? focus.id : null}
        onSelectDevice={(id) => setFocus({ type: 'device', id })}
      />

      {/* Fix Card & Action Buttons */}
      <FixCard
        proposal={proposal}
        focusedButton={focus.type === 'button' ? focus.id : null}
        isExecuting={isExecuting}
        statusMessage={statusMessage}
        showUndo={showUndo}
        onApprove={handleApprove}
        onCancel={handleCancel}
        onUndo={handleUndo}
        onInjectTestFailure={handleInjectTestFailure}
      />

      {/* Footer / Remote Guide */}
      <TvRemoteGuide onDpadPress={handleDpad} />
    </main>
  );
};
