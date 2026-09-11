/** Typed wrappers around the integration's WebSocket commands. */

import type { BookEntry, HomeAssistant, MatterBookState } from "./types";

/**
 * Subscribe to the whole MatterBook state.
 *
 * The coordinator already notifies listeners on every scan, so this is a live
 * view rather than a poll: a device entering pairing mode shows up on its own,
 * and a row that pairs updates without a refresh.
 *
 * @returns an unsubscribe function.
 */
export async function subscribeMatterBook(
  hass: HomeAssistant,
  onState: (state: MatterBookState) => void,
): Promise<() => Promise<void>> {
  return hass.connection.subscribeMessage<MatterBookState>(onState, {
    type: "matterbook/subscribe",
  });
}

export interface AddEntryInput {
  code: string;
  name?: string;
  area?: string;
  notes?: string;
  serial_number?: string;
}

export function addEntry(hass: HomeAssistant, input: AddEntryInput): Promise<BookEntry> {
  return hass.callWS<BookEntry>({ type: "matterbook/add", ...input });
}

export function removeEntry(hass: HomeAssistant, entryId: string): Promise<BookEntry> {
  return hass.callWS<BookEntry>({ type: "matterbook/remove", entry_id: entryId });
}

export interface UpdateEntryInput {
  name?: string;
  area?: string;
  notes?: string;
  enabled?: boolean;
}

export function updateEntry(
  hass: HomeAssistant,
  entryId: string,
  changes: UpdateEntryInput,
): Promise<BookEntry> {
  return hass.callWS<BookEntry>({ type: "matterbook/update", entry_id: entryId, ...changes });
}

export function scan(hass: HomeAssistant): Promise<MatterBookState> {
  return hass.callWS<MatterBookState>({ type: "matterbook/scan" });
}

/**
 * Commission one entry, optionally against one specific device.
 *
 * Naming a device is how conflict resolution works: the human supplies the
 * answer the matcher refused to guess, and the backend then takes its ordinary
 * path — the chosen device's discriminator is folded into a synthesised payload,
 * so the attempt is addressed exactly at it.
 */
export function pairEntry(
  hass: HomeAssistant,
  entryId: string,
  deviceKey?: string,
): Promise<{ node_id: number | null }> {
  return hass.callWS<{ node_id: number | null }>({
    type: "matterbook/pair",
    entry_id: entryId,
    ...(deviceKey ? { device_key: deviceKey } : {}),
  });
}

export interface ImportSummary {
  found: number;
  imported: number;
  already_known: number;
}

/**
 * Snapshot the devices already commissioned onto this fabric.
 *
 * Setup codes cannot be imported — a commissioned device keeps a PASE verifier,
 * not its passcode — so the rows this creates are inventory waiting for their
 * stickers to be found.
 */
export function importFromMatter(hass: HomeAssistant): Promise<ImportSummary> {
  return hass.callWS<ImportSummary>({ type: "matterbook/import" });
}

/** Give an imported row its setup code. */
export function setCode(
  hass: HomeAssistant,
  entryId: string,
  code: string,
): Promise<BookEntry> {
  return hass.callWS<BookEntry>({ type: "matterbook/set_code", entry_id: entryId, code });
}
