/**
 * Types for the slice of Home Assistant the panel touches, and for MatterBook's
 * own payloads.
 *
 * Home Assistant does not publish its frontend types as a stable package, so
 * rather than depend on an unofficial mirror of them, this declares only what is
 * actually used. If the frontend changes something here, it shows up as a type
 * error in our own file instead of a mystery at runtime.
 */

export interface HomeAssistant {
  /** Send a typed command over the frontend's existing WebSocket connection. */
  callWS<T>(message: Record<string, unknown>): Promise<T>;
  connection: {
    subscribeMessage<T>(
      callback: (message: T) => void,
      subscription: Record<string, unknown>,
    ): Promise<() => Promise<void>>;
  };
  language: string;
  themes: { darkMode: boolean };
  user?: { is_admin: boolean; name: string };
  localize(key: string, ...args: unknown[]): string;
}

/** How precisely an entry's code names one device. See DESIGN.md. */
export type IdentityStrength = "exact" | "short" | "none";

/** Which form the stored code takes. */
export type CodeType = "qr" | "manual" | "passcode" | "invalid";

export type EntryStatus = "pending" | "paired" | "failed";

/**
 * A row of the book as the panel sees it.
 *
 * `code` is always masked: the passcode never leaves the integration, so it
 * cannot end up in a screenshot, a browser cache or a bug report. Reading one
 * out needs a deliberate `matterbook/reveal`.
 */
export interface BookEntry {
  id: string;
  name: string;
  code: string;
  code_type: CodeType;
  identity_strength: IdentityStrength;
  vendor_id: number | null;
  product_id: number | null;
  discriminator: number | null;
  short_discriminator: number | null;
  serial_number: string;
  unique_id: string;
  area: string;
  notes: string;
  enabled: boolean;
  status: EntryStatus;
  node_id: number | null;
  paired_at: string;
  last_attempt_at: string;
  attempt_count: number;
  trial_used: boolean;
  last_error: string;
}

/** A device currently advertising that it is commissionable. */
export interface DiscoveredDevice {
  key: string;
  source: "matter_server" | "bluetooth";
  discriminator: number | null;
  vendor_id: number | null;
  product_id: number | null;
  instance_name: string | null;
  name: string | null;
  address: string | null;
  addresses: string[];
  commissioning_mode: number | null;
  /** Signal strength, when a Bluetooth proxy heard it. Helps place a device physically. */
  rssi: number | null;
}

export interface MatchInfo {
  entry_id: string;
  device_key: string;
  confidence: "exact" | "short";
}

/** A device that several entries could describe, or the reverse. */
export interface AmbiguityInfo {
  entry_id: string;
  device_key: string;
}

/** A blind attempt the backend considers allowable. */
export interface TrialInfo {
  entry_id: string;
  device_key: string;
  reason: string;
}

/** The whole state of MatterBook, pushed on every coordinator update. */
export interface MatterBookState {
  entries: BookEntry[];
  devices: DiscoveredDevice[];
  matches: MatchInfo[];
  ambiguous: AmbiguityInfo[];
  trials: TrialInfo[];
  unknown_device_keys: string[];
  auto_pair_enabled: boolean;
  last_scan: string | null;
  last_paired: string | null;
  last_error: string | null;
}
