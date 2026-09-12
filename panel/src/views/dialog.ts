/**
 * A modal shell.
 *
 * Home Assistant's own `ha-dialog` is internal to the frontend and only defined
 * once it happens to have loaded the chunk that imports it, which a custom panel
 * cannot rely on — the same reason the panel carries its own QR decoder. This is
 * the small amount of dialog behaviour that actually matters: a scrim that
 * closes on click, Escape to close, focus moved into the dialog, and the page
 * behind it kept still.
 */

import { LitElement, html, type TemplateResult } from "lit";
import { customElement, property } from "lit/decorators.js";
import { css } from "lit";

@customElement("matterbook-dialog")
export class MatterBookDialog extends LitElement {
  static override styles = css`
    :host {
      position: fixed;
      inset: 0;
      z-index: 100;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 16px;
      box-sizing: border-box;
      /* The panel sits inside Home Assistant's chrome, so the scrim has to be
         drawn by us rather than borrowed from a dialog manager. */
      background: rgba(0, 0, 0, 0.5);
    }

    .surface {
      width: 100%;
      outline: none;
      max-width: 560px;
      max-height: calc(100% - 32px);
      overflow: auto;
      border-radius: var(--ha-card-border-radius, 12px);
      background: var(--card-background-color, #fff);
      color: var(--primary-text-color, #212121);
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
    }

    @media (max-width: 600px) {
      :host {
        padding: 0;
      }

      .surface {
        max-width: none;
        max-height: 100%;
        height: 100%;
        border-radius: 0;
      }
    }
  `;

  /** Whether clicking the scrim or pressing Escape may close the dialog. */
  @property({ type: Boolean }) public dismissable = true;

  public override connectedCallback(): void {
    super.connectedCallback();
    document.addEventListener("keydown", this._onKeyDown);
    // Stop the list behind the dialog scrolling under it on touch.
    this._previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
  }

  public override disconnectedCallback(): void {
    super.disconnectedCallback();
    document.removeEventListener("keydown", this._onKeyDown);
    document.body.style.overflow = this._previousOverflow;
  }

  private _previousOverflow = "";

  protected override render(): TemplateResult {
    return html`
      <div
        class="surface"
        role="dialog"
        aria-modal="true"
        tabindex="-1"
        @click=${(event: Event) => event.stopPropagation()}
      >
        <slot></slot>
      </div>
    `;
  }

  protected override firstUpdated(): void {
    this.addEventListener("click", this._onScrimClick);
    // Move focus inside, so keyboard and screen-reader users land in the dialog
    // rather than behind it. The slotted content is a custom element with its
    // own shadow root, so there is usually nothing here to find — the surface
    // itself is the reliable target, and the content focuses its own first
    // control when it has one worth focusing.
    if (this.contains(document.activeElement)) {
      // The content focused its own first control; leave it there.
      return;
    }
    const focusable = this.querySelector<HTMLElement>(
      "input, button, textarea, select, [tabindex]",
    );
    (focusable ?? this.renderRoot.querySelector<HTMLElement>(".surface"))?.focus();
  }

  private _onScrimClick = (): void => {
    if (this.dismissable) {
      this._close();
    }
  };

  private _onKeyDown = (event: KeyboardEvent): void => {
    if (event.key === "Escape" && this.dismissable) {
      event.stopPropagation();
      this._close();
    }
  };

  private _close(): void {
    this.dispatchEvent(new CustomEvent("matterbook-cancel", { bubbles: true, composed: true }));
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "matterbook-dialog": MatterBookDialog;
  }
}
