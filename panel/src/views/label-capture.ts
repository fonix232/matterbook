/**
 * Photographing a label, and deciding what to keep of it.
 *
 * The crop is not guessed. Rectifying is deterministic — four corners of a
 * square — but where a sticker *ends* is not, and a crop that guesses wrong
 * quietly cuts the vendor's logo off someone's archive. So the margin is a
 * control, the result is on screen before anything is stored, and the whole
 * photograph is one click away.
 */

import { LitElement, html, nothing, type TemplateResult } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import {
  DEFAULT_MARGIN,
  MAX_MARGIN,
  MIN_MARGIN,
  encodeLabel,
  rectifyLabel,
} from "../label";
import { captureFile, type Point } from "../scanner";
import { sharedStyles } from "../styles";

/** What the form should do with the label when it saves. */
export interface LabelChange {
  /** A new image, `null` to remove the stored one, `undefined` to leave it. */
  blob: Blob | null | undefined;
  /** The code read off this photograph, when it carried one. */
  code?: string;
}

@customElement("matterbook-label-capture")
export class MatterBookLabelCapture extends LitElement {
  static override styles = sharedStyles;

  /** A signed URL for the label already stored on this row, if there is one. */
  @property() public existingUrl: string | null = null;
  @property({ type: Boolean }) public busy = false;

  @state() private _source?: HTMLCanvasElement;
  @state() private _corners?: Point[];
  @state() private _preview?: string;
  @state() private _margin = DEFAULT_MARGIN;
  @state() private _whole = false;
  @state() private _removed = false;
  @state() private _working = false;
  @state() private _message = "";

  protected override render(): TemplateResult {
    return html`
      <div class="field">
        <label>Label photo</label>
        ${this._renderBody()}
        <input id="label-photo" type="file" accept="image/*" hidden @change=${this._onFile} />
      </div>
    `;
  }

  private _renderBody(): TemplateResult {
    if (this._message) {
      return html`
        <div class="notice">${this._message}</div>
        ${this._renderActions()}
      `;
    }
    if (this._working) {
      return html`<p class="muted">Flattening the photograph…</p>`;
    }
    if (this._preview) {
      return html`
        <img class="label-image preview" src=${this._preview} alt="The label as it will be kept" />
        ${this._corners && !this._whole ? this._renderMargin() : nothing}
        <label class="checkline">
          <input
            type="checkbox"
            .checked=${this._whole}
            ?disabled=${!this._corners}
            @change=${this._onWhole}
          />
          <span>
            ${this._corners
              ? "Keep the whole photograph instead of the flattened crop"
              : "The code's corners were not reported, so the photograph is kept as taken."}
          </span>
        </label>
        ${this._renderActions()}
      `;
    }
    if (this.existingUrl && !this._removed) {
      return html`
        <img class="label-image preview" src=${this.existingUrl} alt="The stored label" />
        ${this._renderActions()}
      `;
    }
    return html`
      <p class="muted">
        A photograph of the sticker keeps what the rendered code cannot: the printed
        digits, the vendor's logo, and the device ID some vendors put there for
        exactly this reason.
      </p>
      ${this._renderActions()}
    `;
  }

  private _renderMargin(): TemplateResult {
    return html`
      <label class="checkline">
        <input
          type="range"
          min=${MIN_MARGIN}
          max=${MAX_MARGIN}
          step="0.05"
          .value=${String(this._margin)}
          @change=${this._onMargin}
        />
        <span>How much around the code to keep</span>
      </label>
    `;
  }

  private _renderActions(): TemplateResult {
    const has = Boolean(this._preview) || (Boolean(this.existingUrl) && !this._removed);
    return html`
      <div class="toolbar">
        <button class="secondary" ?disabled=${this.busy || this._working} @click=${this._pick}>
          ${has ? "Replace photo" : "Add a photo"}
        </button>
        ${has
          ? html`
              <button class="link" ?disabled=${this.busy || this._working} @click=${this._remove}>
                Remove
              </button>
            `
          : nothing}
      </div>
    `;
  }

  private _pick(): void {
    this.renderRoot.querySelector<HTMLInputElement>("#label-photo")?.click();
  }

  private async _onFile(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = "";
    if (!file) {
      return;
    }

    this._working = true;
    this._message = "";
    try {
      const { result, canvas } = await captureFile(file);
      this._source = canvas;
      this._corners = result?.corners;
      this._whole = !result?.corners;
      this._removed = false;
      await this._rebuild(result?.text);
    } catch (err) {
      this._message = `That photograph could not be read: ${String(err)}`;
    } finally {
      this._working = false;
    }
  }

  private async _onMargin(event: Event): Promise<void> {
    this._margin = Number((event.target as HTMLInputElement).value);
    this._working = true;
    try {
      await this._rebuild();
    } finally {
      this._working = false;
    }
  }

  private async _onWhole(event: Event): Promise<void> {
    this._whole = (event.target as HTMLInputElement).checked;
    this._working = true;
    try {
      await this._rebuild();
    } finally {
      this._working = false;
    }
  }

  /** Re-run the pipeline and publish the result. */
  private async _rebuild(code?: string): Promise<void> {
    const source = this._source;
    if (!source) {
      return;
    }

    let canvas = source;
    if (!this._whole && this._corners) {
      const rectified = rectifyLabel(source, this._corners, this._margin);
      if (rectified) {
        canvas = rectified.canvas;
      } else {
        // Degenerate corners: a code detected as a sliver, or three of its
        // corners on a line. The photograph itself is still a fine label.
        this._whole = true;
        this._message =
          "The code's corners did not describe a square, so the photograph is kept as taken.";
      }
    }

    const blob = await encodeLabel(canvas);
    if (!blob) {
      this._message = "This browser could not encode the photograph.";
      return;
    }
    this._preview = canvas.toDataURL();
    this._emit({ blob, code });
  }

  private _remove(): void {
    this._source = undefined;
    this._corners = undefined;
    this._preview = undefined;
    this._removed = true;
    this._message = "";
    // `null` rather than `undefined`: the row had one and is to lose it.
    this._emit({ blob: this.existingUrl ? null : undefined });
  }

  private _emit(change: LabelChange): void {
    this.dispatchEvent(
      new CustomEvent<LabelChange>("matterbook-label-changed", {
        detail: change,
        bubbles: true,
        composed: true,
      }),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "matterbook-label-capture": MatterBookLabelCapture;
  }
}
