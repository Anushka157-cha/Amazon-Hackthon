import React from 'react';
import { DiagnosisInfo } from '../api/types';

interface DiagnosisBannerProps {
  diagnosis: DiagnosisInfo | null;
}

export const DiagnosisBanner: React.FC<DiagnosisBannerProps> = ({ diagnosis }) => {
  const hasIncident = diagnosis?.has_incident ?? false;
  const rootCauseName = diagnosis?.root_cause_name || 'Wi-Fi Extender';
  const victims = diagnosis?.victim_names || [];

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
            diagnosis?.summary || (
              <>
                Your <span style={{ color: '#F87171' }}>{rootCauseName}</span> is the root cause.{' '}
                {victims.length > 0 && (
                  <span style={{ color: '#FDE047' }}>
                    {victims.join(', ')} are affected because of it.
                  </span>
                )}
              </>
            )
          ) : (
            'All simulated devices are online and working normally.'
          )}
        </h2>
        <p className="diagnosis-subtext">
          {hasIncident
            ? diagnosis?.spoken || 'Voice command: "Alexa, what\'s wrong with my home?"'
            : 'Dependency graph monitoring 5 smart home devices with zero active failures.'}
        </p>
      </div>
    </section>
  );
};
