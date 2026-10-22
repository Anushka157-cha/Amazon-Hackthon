import React from 'react';
import { DeviceInfo, DiagnosisInfo } from '../api/types';
import { DeviceTile } from './DeviceTile';

interface HomeMapProps {
  devices: Record<string, DeviceInfo>;
  diagnosis: DiagnosisInfo | null;
  focusedDeviceId: string | null;
  onSelectDevice: (deviceId: string) => void;
}

export const HomeMap: React.FC<HomeMapProps> = ({
  devices,
  diagnosis,
  focusedDeviceId,
  onSelectDevice,
}) => {
  const router = devices['router'] || {
    id: 'router',
    name: 'Main Router',
    status: 'online',
    device_type: 'network_gateway',
    simulated: true,
    upstream: [],
    downstream: ['wifi_extender'],
  };

  const extender = devices['wifi_extender'] || {
    id: 'wifi_extender',
    name: 'Wi-Fi Extender',
    status: 'online',
    device_type: 'network_repeater',
    simulated: true,
    upstream: ['router'],
    downstream: ['ring_doorbell', 'fire_tv', 'echo_speaker'],
  };

  const downstreamIds = ['ring_doorbell', 'fire_tv', 'echo_speaker'];

  const rootCause = diagnosis?.root_cause;
  const victims = diagnosis?.victims || [];

  return (
    <div className="home-map-container">
      <div className="map-header">
        <span>🌐 Smart Home Dependency Graph</span>
        <span style={{ fontSize: '12px', color: '#64748B' }}>
          (Router ➔ Extender ➔ Endpoints)
        </span>
      </div>

      <div className="graph-row">
        {/* Tier 1: Router */}
        <div>
          <DeviceTile
            device={router}
            isFocused={focusedDeviceId === 'router'}
            isRootCause={rootCause === 'router'}
            isVictim={victims.includes('router')}
            onSelect={() => onSelectDevice('router')}
          />
        </div>

        {/* Connector 1 */}
        <div className="graph-connector">
          <div className="connector-line active" />
          <span>►</span>
        </div>

        {/* Tier 2: Extender */}
        <div>
          <DeviceTile
            device={extender}
            isFocused={focusedDeviceId === 'wifi_extender'}
            isRootCause={rootCause === 'wifi_extender'}
            isVictim={victims.includes('wifi_extender')}
            onSelect={() => onSelectDevice('wifi_extender')}
          />
        </div>

        {/* Connector 2 */}
        <div className="graph-connector">
          <div className="connector-line active" />
          <span>►</span>
        </div>

        {/* Tier 3: Downstream Devices */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {downstreamIds.map((id) => {
            const dev = devices[id] || {
              id,
              name: id,
              status: 'online',
              device_type: 'endpoint',
              simulated: true,
              upstream: ['wifi_extender'],
              downstream: [],
            };
            return (
              <DeviceTile
                key={id}
                device={dev}
                isFocused={focusedDeviceId === id}
                isRootCause={rootCause === id}
                isVictim={victims.includes(id)}
                onSelect={() => onSelectDevice(id)}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
};
