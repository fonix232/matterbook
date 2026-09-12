/** Typed wrappers around the integration's WebSocket commands. */

import type { BookEntry, HomeAssistant, MatterBookOptions, MatterBookState } from "./types";

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

/**
 * Set a row's setup code: fill in an imported row, or correct a wrong one.
 *
 * `replace` has to be asked for, so a row that already has a code never changes
 * it as a side effect.
 */
export function setCode(
  hass: HomeAssistant,
  entryId: string,
  code: string,
  replace = false,
): Promise<BookEntry> {
  return hass.callWS<BookEntry>({
    type: "matterbook/set_code",
    entry_id: entryId,
    code,
    replace,
  });
}

/** Read the current settings, with the backend's defaults already filled in. */
export function getOptions(hass: HomeAssistant): Promise<MatterBookOptions> {
  return hass.callWS<MatterBookOptions>({ type: "matterbook/options" });
}

/**
 * Save settings.
 *
 * This reloads the config entry, which is what makes a new scan interval take
 * effect — and which tears the subscription down, so the caller has to take a
 * new one out afterwards.
 */
export function setOptions(
  hass: HomeAssistant,
  options: Partial<MatterBookOptions>,
): Promise<MatterBookOptions> {
  return hass.callWS<MatterBookOptions>({ type: "matterbook/set_options", options });
}

/**
 * Read one row's setup code, unmasked.
 *
 * The deliberate exception to masking. It is what the rows with no scannable
 * label need: a manual pairing code and a bare passcode are digits, so there is
 * no picture to scan off the screen and reading the number out is the only way
 * to hand it to another controller's app. The backend logs every call.
 */
export function revealCode(hass: HomeAssistant, entryId: string): Promise<{ code: string }> {
  return hass.callWS<{ code: string }>({ type: "matterbook/reveal", entry_id: entryId });
}

/**
 * Ask a paired row's device to make itself obvious.
 *
 * Only works once a device is commissioned — Identify is a cluster command, and
 * an uncommissioned device has no fabric to accept one over.
 */
export function identify(hass: HomeAssistant, entryId: string): Promise<{ seconds: number }> {
  return hass.callWS<{ seconds: number }>({ type: "matterbook/identify", entry_id: entryId });
}

/** Store a photograph of a row's label, or clear it by passing `null`. */
export function setLabel(
  hass: HomeAssistant,
  entryId: string,
  image: string | null,
): Promise<BookEntry> {
  return hass.callWS<BookEntry>({ type: "matterbook/set_label", entry_id: entryId, image });
}
