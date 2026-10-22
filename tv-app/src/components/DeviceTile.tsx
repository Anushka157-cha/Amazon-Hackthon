import React from 'react';
import { DeviceInfo } from '../api/types';

interface DeviceTileProps {
  device: DeviceInfo;
  isFocused: boolean;
  isRootCause: boolean;
  isVictim: boolean;
  onSelect: () => void;
}

const DEVICE_ICONS: Record<string, string> = {
  router: '🌐',
  wifi_extender: '📶',
  ring_doorbell: '🔔',
  fire_tv: '📺',
  echo_speaker: '🔊',
};

const DEVICE_LABELS: Record<string, string> = {
  router: 'Main Router',
  wifi_extender: 'Wi-Fi Extender',
  ring_doorbell: 'Ring Doorbell',
  fire_tv: 'Fire TV 4K',
  echo_speaker: 'Echo Speaker',
};

export const DeviceTile: React.FC<DeviceTileProps> = ({
  device,
  isFocused,
  isRootCause,
  isVictim,
  onSelect,
}) => {
  const icon = DEVICE_ICONS[device.id] || '⚡';
  const label = DEVICE_LABELS[device.id] || device.name;
  const statusClass = device.status;

  return (
    <div
      role="button"
      tabIndex={0}
      className={`device-tile ${statusClass} ${isFocused ? 'focused' : ''}`}
      onClick={onSelect}
    >
      {isRootCause && <div className="root-cause-tag">ROOT CAUSE</div>}
      {isVictim && <div className="victim-tag">VICTIM</div>}

      <div className="device-icon-wrapper">
        <span>{icon}</span>
      </div>

      <div className="device-name">{label}</div>

      <div className={`device-status-badge status-${statusClass}`}>
        {device.status.toUpperCase()}
      </div>
    </div>
  );
};
