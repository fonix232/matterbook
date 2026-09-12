/**
 * Getting a setup code out of a sticker and into the book.
 *
 * Used twice: adding a device, and correcting the code on a row that already
 * exists. Both want the same thing — scan it, photograph it, or type it — so
 * they share this.
 */

import { LitElement, html, nothing, type PropertyValues, type TemplateResult } from "lit";
import { customElement, property, query, state } from "lit/decorators.js";

import { CameraScanner, cameraAvailable, decodeFile } from "../scanner";
import { sharedStyles } from "../styles";

export interface CodeEntryResult {
  code: string;
  name: string;
  area: string;
  notes: string;
}

@customElement("matterbook-code-entry")
export class MatterBookCodeEntry extends LitElement {
  static override styles = sharedStyles;

  /** Heading, so the same element can say "Add a device" or "Change the code". */
  @property() public heading = "Add a device";
  /** Whether to ask for a name and area as well as the code. */
  @property({ type: Boolean }) public withDetails = false;
  @property({ type: Boolean }) public busy = false;
  @property() public code = "";

  @state() private _scanning = false;
  @state() private _message?: string;
  @state() private _decodedBy?: string;

  @query("video") private _video?: HTMLVideoElement;
  @query("#code") private _codeField?: HTMLInputElement;
  @query("#name") private _nameField?: HTMLInputElement;
  @query("#area") private _areaField?: HTMLInputElement;
  @query("#notes") private _notesField?: HTMLTextAreaElement;

  private _scanner?: CameraScanner;

  public override disconnectedCallback(): void {
    super.disconnectedCallback();
    // A camera left running outlives the dialog otherwise.
    this._stopScanning();
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
      <div class="card">
        <h2>${this.heading}</h2>

        ${this._message ? html`<div class="error">${this._message}</div>` : nothing}
        ${this._scanning ? this._renderCamera() : nothing}

        <div class="field">
          <label for="code">Setup code</label>
          <input
            id="code"
            type="text"
            .value=${this.code}
            placeholder="MT:… , the 11-digit pairing code, or the 8-digit passcode"
            @input=${(event: Event) => {
              this.code = (event.target as HTMLInputElement).value;
            }}
          />
          <p class="muted">
            The QR payload is worth the most: it carries the full discriminator, so
            MatterBook can tell exactly which device the code opens. A manual code
            narrows to one device in sixteen, and a bare passcode names none.
            ${this._decodedBy
              ? html`<br /><strong>Scanned.</strong> Decoded by
                  ${this._decodedBy === "native" ? "the browser" : "the bundled decoder"}.`
              : nothing}
          </p>
        </div>

        <div class="toolbar">
          ${cameraAvailable()
            ? html`
                <button
                  class="secondary"
                  ?disabled=${this.busy}
                  @click=${this._toggleScanning}
                >
                  ${this._scanning ? "Stop camera" : "Scan with camera"}
                </button>
              `
            : nothing}
          <button class="secondary" ?disabled=${this.busy} @click=${this._pickPhoto}>
            Take a photo
          </button>
          <input
            id="photo"
            type="file"
            accept="image/*"
            capture="environment"
            hidden
            @change=${this._onPhoto}
          />
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
        ${this.withDetails ? this._renderDetails() : nothing}

        <div class="toolbar">
          <button class="secondary" ?disabled=${this.busy} @click=${this._cancel}>
            Cancel
          </button>
          <div class="spacer"></div>
          <button ?disabled=${this.busy || !this.code.trim()} @click=${this._save}>
            ${this.busy ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
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
        <input id="name" type="text" placeholder="Kitchen ceiling light" />
        <p class="muted">Applied to the device once it pairs.</p>
      </div>
      <div class="field">
        <label for="area">Area</label>
        <input id="area" type="text" placeholder="Kitchen" />
      </div>
      <div class="field">
        <label for="notes">Notes</label>
        <textarea id="notes" rows="2" placeholder="Behind the trim"></textarea>
      </div>
    `;
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

  private _pickPhoto(): void {
    this.renderRoot.querySelector<HTMLInputElement>("#photo")?.click();
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
    if (!code) {
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
