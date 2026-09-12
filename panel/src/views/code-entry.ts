/**
 * Getting a setup code, and the words that go with it, into the book.
 *
 * Used twice: adding a device, and editing a row that already exists. Both want
 * the same thing — scan it, photograph it, or type it, then say what it is — so
 * they share this.
 *
 * Editing never prefills the code field, because the panel is never told the
 * code: what a row shows is a mask. An empty field therefore means "leave the
 * code alone", which is also the right default — most edits are to the name.
 */

import { LitElement, html, nothing, type PropertyValues, type TemplateResult } from "lit";
import { customElement, property, query, state } from "lit/decorators.js";

import { CameraScanner, cameraAvailable, decodeFile } from "../scanner";
import { sharedStyles } from "../styles";

export interface CodeEntryResult {
  /** Empty when editing and the code was left alone. */
  code: string;
  name: string;
  area: string;
  notes: string;
}

@customElement("matterbook-code-entry")
export class MatterBookCodeEntry extends LitElement {
  static override styles = sharedStyles;

  /** Heading, so the same element can say "Add a device" or "Edit entry". */
  @property() public heading = "Add a device";
  @property({ type: Boolean }) public busy = false;
  /** A code the caller already decoded — from the chooser's photo step. */
  @property() public code = "";
  /** The masked code already on the row, shown for context when editing. */
  @property() public existingCode = "";
  /** Whether saving needs a code. Adding does; editing does not. */
  @property({ type: Boolean }) public requireCode = false;
  /** Open the camera as soon as this renders, rather than waiting for a click. */
  @property({ type: Boolean }) public startScanning = false;
  /** Whether the form was reached through the chooser, and can go back to it. */
  @property({ type: Boolean }) public canGoBack = false;
  /** Something the previous step wants to say — a photo that did not decode. */
  @property() public notice = "";
  /** Whether that something is a failure, rather than context. */
  @property({ type: Boolean }) public noticeIsError = false;

  @property() public name = "";
  @property() public area = "";
  @property() public notes = "";

  @state() private _scanning = false;
  @state() private _message?: string;
  @state() private _decodedBy?: string;

  @query("video") private _video?: HTMLVideoElement;
  @query("#code") private _codeField?: HTMLInputElement;
  @query("#name") private _nameField?: HTMLInputElement;
  @query("#area") private _areaField?: HTMLInputElement;
  @query("#notes") private _notesField?: HTMLTextAreaElement;
  @query("#photo") private _photoField?: HTMLInputElement;

  private _scanner?: CameraScanner;

  public override disconnectedCallback(): void {
    super.disconnectedCallback();
    // A camera left running outlives the dialog otherwise.
    this._stopScanning();
  }

  protected override firstUpdated(): void {
    if (this.startScanning) {
      this._scanning = true;
      return;
    }
    // Land on the field this form exists to fill: the code when adding, the
    // name when editing, since the code is usually the part already right.
    (this.requireCode ? this._codeField : this._nameField)?.focus();
  }

  protected override updated(changed: PropertyValues): void {
    if (changed.has("_scanning") && this._scanning && this._video && !this._scanner) {
      this._scanner = new CameraScanner(
        this._video,
        (result) => {
          this.code = result.text;
          this._decodedBy = result.decoder;
          this._message = undefined;
          this._stopScanning();
        },
        (message) => {
          this._message = message;
          this._stopScanning();
        },
      );
      void this._scanner.start();
    }
  }

  protected override render(): TemplateResult {
    return html`
      <div class="card flush">
        <div class="toolbar">
          ${this.canGoBack
            ? html`<button class="link" @click=${this._back}>‹ Back</button>`
            : nothing}
          <h2>${this.heading}</h2>
        </div>

        ${this._message ? html`<div class="error">${this._message}</div>` : nothing}
        ${this.notice && !this._message
          ? html`<div class=${this.noticeIsError ? "error" : "notice"}>${this.notice}</div>`
          : nothing}
        ${this._scanning ? this._renderCamera() : nothing}
        ${this._renderCodeField()}
        ${this._renderCodeActions()}
        ${this._renderDetails()}

        <div class="toolbar">
          <button class="secondary" ?disabled=${this.busy} @click=${this._cancel}>Cancel</button>
          <div class="spacer"></div>
          <button ?disabled=${this.busy || !this._canSave()} @click=${this._save}>
            ${this.busy ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    `;
  }

  private _renderCodeField(): TemplateResult {
    return html`
      <div class="field">
        <label for="code">Setup code</label>
        <input
          id="code"
          type="text"
          .value=${this.code}
          placeholder=${this.existingCode
            ? "Leave blank to keep the code this row already has"
            : "MT:… , the 11-digit pairing code, or the 8-digit passcode"}
          @input=${(event: Event) => {
            this.code = (event.target as HTMLInputElement).value;
          }}
        />
        <p class="muted">
          ${this.existingCode
            ? html`This row holds <code>${this.existingCode}</code>. Typing a new code
                replaces it and clears what was worked out from the old one.<br />`
            : nothing}
          The QR payload is worth the most: it carries the full discriminator, so
          MatterBook can tell exactly which device the code opens. A manual code
          narrows to one device in sixteen, and a bare passcode names none.
          ${this._decodedBy
            ? html`<br /><strong>Scanned.</strong> Decoded by
                ${this._decodedBy === "native" ? "the browser" : "the bundled decoder"}.`
            : nothing}
        </p>
      </div>
    `;
  }

  private _renderCodeActions(): TemplateResult {
    return html`
      <div class="toolbar">
        ${cameraAvailable()
          ? html`
              <button class="secondary" ?disabled=${this.busy} @click=${this._toggleScanning}>
                ${this._scanning ? "Stop camera" : "Scan with camera"}
              </button>
            `
          : nothing}
        <button class="secondary" ?disabled=${this.busy} @click=${() => this._pickPhoto(true)}>
          Take a photo
        </button>
        <button class="secondary" ?disabled=${this.busy} @click=${() => this._pickPhoto(false)}>
          Choose a photo
        </button>
        <input id="photo" type="file" accept="image/*" hidden @change=${this._onPhoto} />
      </div>

      ${cameraAvailable()
        ? nothing
        : html`
            <p class="muted">
              Live scanning needs a secure connection, and this page is not on one.
              <strong>Take a photo</strong> works anyway — on a phone it opens the
              camera — and so does typing the code in.
            </p>
          `}
    `;
  }

  private _renderCamera(): TemplateResult {
    return html`
      <div class="viewfinder">
        <video muted playsinline></video>
        <p class="muted">Point the camera at the QR code on the device or its box.</p>
      </div>
    `;
  }

  private _renderDetails(): TemplateResult {
    return html`
      <div class="field">
        <label for="name">Name</label>
        <input id="name" type="text" .value=${this.name} placeholder="Kitchen ceiling light" />
        <p class="muted">Applied to the device once it pairs.</p>
      </div>
      <div class="field">
        <label for="area">Area</label>
        <input id="area" type="text" .value=${this.area} placeholder="Kitchen" />
      </div>
      <div class="field">
        <label for="notes">Notes</label>
        <textarea id="notes" rows="2" .value=${this.notes} placeholder="Behind the trim"></textarea>
      </div>
    `;
  }

  private _canSave(): boolean {
    return !this.requireCode || this.code.trim().length > 0;
  }

  private _toggleScanning(): void {
    if (this._scanning) {
      this._stopScanning();
    } else {
      this._message = undefined;
      this._scanning = true;
    }
  }

  private _stopScanning(): void {
    this._scanner?.stop();
    this._scanner = undefined;
    this._scanning = false;
  }

  /**
   * `capture` is what makes a phone open the camera instead of the gallery, so
   * it is set per click rather than baked into the markup.
   */
  private _pickPhoto(fromCamera: boolean): void {
    const field = this._photoField;
    if (!field) {
      return;
    }
    if (fromCamera) {
      field.setAttribute("capture", "environment");
    } else {
      field.removeAttribute("capture");
    }
    field.click();
  }

  private async _onPhoto(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = "";
    if (!file) {
      return;
    }

    this._message = undefined;
    try {
      const result = await decodeFile(file);
      if (result) {
        this.code = result.text;
        this._decodedBy = result.decoder;
      } else {
        this._message =
          "No QR code found in that picture. Try again with the code filling more " +
          "of the frame, or type it in.";
      }
    } catch (err) {
      this._message = `That image could not be read: ${String(err)}`;
    }
  }

  private _save(): void {
    const code = (this._codeField?.value ?? this.code).trim();
    if (this.requireCode && !code) {
      return;
    }
    this._stopScanning();
    this.dispatchEvent(
      new CustomEvent<CodeEntryResult>("matterbook-code-entered", {
        detail: {
          code,
          name: this._nameField?.value.trim() ?? "",
          area: this._areaField?.value.trim() ?? "",
          notes: this._notesField?.value.trim() ?? "",
        },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _back(): void {
    this._stopScanning();
    this.dispatchEvent(new CustomEvent("matterbook-back", { bubbles: true, composed: true }));
  }

  private _cancel(): void {
    this._stopScanning();
    this.dispatchEvent(new CustomEvent("matterbook-cancel", { bubbles: true, composed: true }));
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "matterbook-code-entry": MatterBookCodeEntry;
  }
}
