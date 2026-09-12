/**
 * Reading a Matter QR code with the device's camera.
 *
 * Two decoders, in order of preference:
 *
 * 1. `BarcodeDetector`, which is native and free. Chrome and the Android
 *    WebView have it; Safari and Firefox do not.
 * 2. jsQR, bundled as a fallback so the feature does not simply vanish on iOS.
 *
 * And two ways to get an image, which matters more than it looks:
 *
 * * A **live camera** needs `getUserMedia`, which browsers only expose in a
 *   secure context. A Home Assistant reached over plain `http://` on the local
 *   network is *not* one, so on many perfectly normal installs the live scanner
 *   cannot work at all.
 * * A **file input** with `capture="environment"` has no such restriction and
 *   opens the camera app on a phone. It is the fallback that keeps this usable
 *   over plain HTTP, and it is also how you scan a sticker you photographed
 *   earlier.
 */

import jsQR from "jsqr";

export interface ScanResult {
  text: string;
  decoder: "native" | "jsqr";
}

interface BarcodeDetectorLike {
  detect(source: CanvasImageSource): Promise<{ rawValue: string }[]>;
}

type BarcodeDetectorCtor = new (options?: { formats?: string[] }) => BarcodeDetectorLike;

function nativeDetector(): BarcodeDetectorLike | null {
  const ctor = (globalThis as { BarcodeDetector?: BarcodeDetectorCtor }).BarcodeDetector;
  if (!ctor) {
    return null;
  }
  try {
    return new ctor({ formats: ["qr_code"] });
  } catch {
    return null;
  }
}

/** Whether a live camera stream is available at all. */
export function cameraAvailable(): boolean {
  // `isSecureContext` is the honest check: over plain HTTP, mediaDevices is
  // simply absent, and asking for it throws rather than prompting.
  return Boolean(globalThis.isSecureContext && navigator.mediaDevices?.getUserMedia);
}

/** Decode a QR code from an image element or canvas. */
export async function decodeImage(source: HTMLImageElement): Promise<ScanResult | null> {
  const canvas = document.createElement("canvas");
  canvas.width = source.naturalWidth;
  canvas.height = source.naturalHeight;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) {
    return null;
  }
  context.drawImage(source, 0, 0);
  return decodeCanvas(canvas, context);
}

async function decodeCanvas(
  canvas: HTMLCanvasElement,
  context: CanvasRenderingContext2D,
): Promise<ScanResult | null> {
  const detector = nativeDetector();
  if (detector) {
    try {
      const [found] = await detector.detect(canvas);
      if (found?.rawValue) {
        return { text: found.rawValue, decoder: "native" };
      }
    } catch {
      // Fall through to jsQR: some implementations throw on odd frame sizes.
    }
  }

  const { width, height } = canvas;
  if (width === 0 || height === 0) {
    return null;
  }
  const image = context.getImageData(0, 0, width, height);
  const found = jsQR(image.data, width, height, { inversionAttempts: "attemptBoth" });
  return found?.data ? { text: found.data, decoder: "jsqr" } : null;
}

/** Decode a QR code from a photograph the user picked or took. */
export async function decodeFile(file: File): Promise<ScanResult | null> {
  const url = URL.createObjectURL(file);
  try {
    const image = new Image();
    image.src = url;
    await image.decode();
    return await decodeImage(image);
  } finally {
    URL.revokeObjectURL(url);
  }
}

/**
 * A live camera scan.
 *
 * Holds the stream, samples frames, and stops as soon as something decodes.
 * `stop()` is safe to call at any point and must be called when the view goes
 * away — a camera left running is both a battery drain and a privacy problem.
 */
export class CameraScanner {
  private _stream?: MediaStream;
  private _timer?: number;
  private _stopped = false;

  constructor(
    private readonly _video: HTMLVideoElement,
    private readonly _onResult: (result: ScanResult) => void,
    private readonly _onError: (message: string) => void,
  ) {}

  async start(): Promise<void> {
    if (!cameraAvailable()) {
      this._onError(
        "The camera needs a secure connection. Open Home Assistant over HTTPS or " +
          "through the companion app, or use Take a photo instead.",
      );
      return;
    }

    try {
      this._stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" } },
        audio: false,
      });
    } catch (err) {
      this._onError(
        err instanceof DOMException && err.name === "NotAllowedError"
          ? "Camera permission was refused."
          : `The camera could not be opened: ${String(err)}`,
      );
      return;
    }

    if (this._stopped) {
      // stop() landed while permission was pending; do not leave it running.
      this._releaseStream();
      return;
    }

    this._video.srcObject = this._stream;
    this._video.setAttribute("playsinline", "");
    await this._video.play().catch(() => undefined);
    this._tick();
  }

  stop(): void {
    this._stopped = true;
    if (this._timer !== undefined) {
      clearTimeout(this._timer);
      this._timer = undefined;
    }
    this._releaseStream();
  }

  private _releaseStream(): void {
    this._stream?.getTracks().forEach((track) => track.stop());
    this._stream = undefined;
    this._video.srcObject = null;
  }

  private _tick = (): void => {
    if (this._stopped) {
      return;
    }
    void this._sample().finally(() => {
      if (!this._stopped) {
        // ~8 frames a second: fast enough to feel instant, slow enough not to
        // pin a phone's CPU while the user lines the sticker up.
        this._timer = globalThis.setTimeout(this._tick, 120);
      }
    });
  };

  private async _sample(): Promise<void> {
    const { videoWidth: width, videoHeight: height } = this._video;
    if (!width || !height) {
      return;
    }

    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d", { willReadFrequently: true });
    if (!context) {
      return;
    }
    context.drawImage(this._video, 0, 0, width, height);

    const result = await decodeCanvas(canvas, context);
    if (result && !this._stopped) {
      this.stop();
      this._onResult(result);
    }
  }
}
