/**
 * Adding or editing one row, as a modal.
 *
 * Adding opens on a menu rather than a form, because the three ways a code gets
 * into the book are genuinely different acts: pointing a camera at a device,
 * picking a photograph of one, and typing. A form with a camera button somewhere
 * in it makes the typing path look like the intended one, and it is the slowest.
 *
 * The photograph paths decode here rather than in the form, so the file picker
 * opens inside the click that asked for it. Opening one a render later works
 * most of the time and fails in exactly the place it matters — a phone, where a
 * browser is strictest about which gesture opened a picker.
 */

import { LitElement, css, html, nothing, type TemplateResult } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import { cameraAvailable, decodeFile } from "../scanner";
import { sharedStyles } from "../styles";
import "./dialog";
import "./code-entry";

/** What the dialog was opened on: a blank row to add, or one to edit. */
export interface EntryDialogTarget {
  /** Set when editing; absent when adding. */
  entryId?: string;
  name: string;
  area: string;
  notes: string;
  /** The masked code already on the row, if it has one. */
  existingCode: string;
  /** A signed URL for the label photograph on the row, if it has one. */
  labelUrl: string | null;
  /** Editing goes straight to the form: the row's data is the point. */
  skipChooser: boolean;
}

@customElement("matterbook-entry-dialog")
export class MatterBookEntryDialog extends LitElement {
  static override styles = [
    sharedStyles,
    css`
      /* The dialog inside is fixed-positioned, so this element only exists to
         own it. Taking no space keeps it out of the panel's column. */
      :host {
        display: contents;
      }
    `,
  ];

  @property({ attribute: false }) public target!: EntryDialogTarget;
  @property({ type: Boolean }) public busy = false;
  /**
   * Something the panel wants said inside the dialog: why it was opened, or
   * what the backend rejected. It belongs here rather than on the page because
   * the page is behind a scrim while this is open.
   */
  @property() public message = "";
  /** Whether that message is a failure, rather than context. */
  @property({ type: Boolean }) public messageIsError = false;

  /** Unset until something navigates; see `_currentStep`. */
  @state() private _step?: "chooser" | "form";
  @state() private _code = "";
  @state() private _startScanning = false;
  @state() private _notice = "";
  @state() private _decoding = false;

  /**
   * Which step to show.
   *
   * Derived rather than initialised, because initialising it would depend on
   * `target` having been set before this element connected — true today, and
   * not something to build on.
   */
  private _currentStep(): "chooser" | "form" {
    return this._step ?? (this.target?.skipChooser ? "form" : "chooser");
  }

  protected override render(): TemplateResult {
    return html`
      <matterbook-dialog
        .dismissable=${!this.busy && !this._decoding}
        @matterbook-back=${this._toChooser}
      >
        ${this._currentStep() === "chooser" ? this._renderChooser() : this._renderForm()}
      </matterbook-dialog>
      <input id="photo" type="file" accept="image/*" hidden @change=${this._onPhoto} />
    `;
  }

  private _renderChooser(): TemplateResult {
    return html`
      <div class="card flush">
        <h2>Add a device</h2>
        ${this._message()
          ? html`<div class=${this._messageIsError() ? "error" : "notice"}>
              ${this._message()}
            </div>`
          : nothing}

        <div class="chooser">
          <button ?disabled=${this._decoding} @click=${this._takePhoto}>
            <strong>Take a photo</strong>
            <span>
              ${cameraAvailable()
                ? "Point the camera at the code on the device or its box."
                : "Opens the camera. Live scanning needs a secure connection, which " +
                  "this page is not on, so the picture is decoded after it is taken."}
            </span>
          </button>

          <button ?disabled=${this._decoding} @click=${this._choosePhoto}>
            <strong>Choose a photo</strong>
            <span>
              ${this._decoding
                ? "Reading the picture…"
                : "Use a picture of the label already on this device."}
            </span>
          </button>

          <button ?disabled=${this._decoding} @click=${this._enterByHand}>
            <strong>Type it in</strong>
            <span>The QR payload, the 11-digit pairing code, or the 8-digit passcode.</span>
          </button>
        </div>

        <div class="toolbar">
          <div class="spacer"></div>
          <button class="secondary" @click=${this._cancel}>Cancel</button>
        </div>
      </div>
    `;
  }

  private _renderForm(): TemplateResult {
    const target = this.target;
    return html`
      <matterbook-code-entry
        .heading=${target.entryId ? "Edit entry" : "Add a device"}
        .code=${this._code}
        .name=${target.name}
        .area=${target.area}
        .notes=${target.notes}
        .existingCode=${target.existingCode}
        .labelUrl=${target.labelUrl}
        .requireCode=${!target.entryId}
        .startScanning=${this._startScanning}
        .canGoBack=${!target.skipChooser}
        .notice=${this._message()}
        .noticeIsError=${this._messageIsError()}
        .busy=${this.busy}
      ></matterbook-code-entry>
    `;
  }

  /** The dialog's own message wins: it is the newer of the two. */
  private _message(): string {
    return this._notice || this.message;
  }

  private _messageIsError(): boolean {
    return this._notice ? false : this.messageIsError;
  }

  private _takePhoto(): void {
    this._notice = "";
    if (cameraAvailable()) {
      // A live viewfinder decodes as it goes, so there is no picture to get
      // wrong and no second attempt to ask for.
      this._startScanning = true;
      this._step = "form";
      return;
    }
    this._pick(true);
  }

  private _choosePhoto(): void {
    this._notice = "";
    this._pick(false);
  }

  private _enterByHand(): void {
    this._notice = "";
    this._step = "form";
  }

  /** `capture` is what makes a phone open the camera rather than the gallery. */
  private _pick(fromCamera: boolean): void {
    const field = this.renderRoot.querySelector<HTMLInputElement>("#photo");
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

    this._decoding = true;
    try {
      const result = await decodeFile(file);
      if (result) {
        this._code = result.text;
        this._notice = "";
      } else {
        // Still go to the form: the digits are printed next to the QR, so a
        // picture that would not decode is usually one the eye can still read.
        this._notice =
          "No QR code found in that picture. Type the code from the label, or go " +
          "back and try a photo with the code filling more of the frame.";
      }
      this._step = "form";
    } catch (err) {
      this._notice = `That image could not be read: ${String(err)}`;
    } finally {
      this._decoding = false;
    }
  }

  private _toChooser(event: Event): void {
    // The chooser is this dialog's own business; the panel only hears about
    // saving and cancelling.
    event.stopPropagation();
    this._notice = "";
    this._startScanning = false;
    this._step = "chooser";
  }

  private _cancel(): void {
    this.dispatchEvent(new CustomEvent("matterbook-cancel", { bubbles: true, composed: true }));
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "matterbook-entry-dialog": MatterBookEntryDialog;
  }
}
