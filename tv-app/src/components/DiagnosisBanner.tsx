import React from 'react';
import { DiagnosisInfo } from '../api/types';

interface DiagnosisBannerProps {
  diagnosis: DiagnosisInfo | null;
}

export const DiagnosisBanner: React.FC<DiagnosisBannerProps> = ({ diagnosis }) => {
  const hasIncident = diagnosis?.has_incident ?? false;
  const rawRoot = diagnosis?.root_cause_name || 'Wi-Fi Extender';
  const rootCauseName = rawRoot.replace(' (Simulated)', '');
  const victims = (diagnosis?.victim_names || []).map((v) =>
    v.replace(' (Simulated)', '')
  );

  return (
    <section
      className={`tv-diagnosis-banner ${hasIncident ? 'incident' : 'healthy'}`}
      aria-live="polite"
    >
      <div className="diagnosis-icon">
        {hasIncident ? '🚨' : '✅'}
      </div>
      <div className="diagnosis-content">
        <h2 className="diagnosis-headline">
          {hasIncident ? (
            <>
              Your <span style={{ color: '#F87171' }}>{rootCauseName}</span> is the root cause.{' '}
              {victims.length > 0 && (
                <span style={{ color: '#FDE047', fontWeight: 500, fontSize: '18px' }}>
                  ({victims.join(', ')} are affected)
                </span>
              )}
            </>
          ) : (
            'All simulated devices are online and working normally.'
          )}
        </h2>
        <p className="diagnosis-subtext">
          {hasIncident
            ? diagnosis?.spoken || `Alexa: "I found the issue. Your ${rootCauseName} is offline."`
            : 'Say "Alexa, what\'s my home status?" or test an outage below.'}
        </p>
      </div>
    </section>
  );
};
