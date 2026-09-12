/**
 * Turning a photograph of a sticker into an archive copy of it.
 *
 * The goal is the label **as printed** — the code, the digits beside it, the
 * vendor's logo, the device ID some vendors print for exactly this reason —
 * flat, cropped and legible. Not a regenerated QR: that would be sharper and
 * useless, because it would not be the thing that is stuck to the device.
 *
 * Four corners of a shape known to be square give a homography, and applying it
 * flattens the whole photograph rather than only the code. That is the whole
 * trick, and it is why the decoders are asked for corner points.
 *
 * What this deliberately does **not** do is decide where the sticker ends.
 * Finding a printed border means edge detection and contour fitting, which mean
 * OpenCV, which does not belong in a panel bundle — and a crop that guesses
 * wrong quietly guillotines the vendor's logo off someone's archive. So the
 * margin is expressed in code-widths, starts generous, and the person taking
 * the photograph sees the result and adjusts it before anything is stored.
 * A human confirming a crop is worth more than a clever one they never see.
 */

import type { Point } from "./scanner";

/** How far past the code to keep, as a multiple of the code's own width. */
export const DEFAULT_MARGIN = 0.85;
export const MIN_MARGIN = 0.1;
export const MAX_MARGIN = 3;

/** The code's side length in the rectified image. Fixes the effective DPI. */
const CODE_SIDE = 320;

/**
 * The largest rectified image to produce.
 *
 * Every output pixel is an inverse projection and a bilinear sample in
 * JavaScript, so the cost is the area. At the widest margin the untrimmed size
 * would be seven code-widths square — five megapixels, several seconds on a
 * phone, for a picture nobody needs at that size. Past this the code-width
 * shrinks instead, which costs resolution and keeps the framing.
 */
const MAX_OUTPUT = 1400;

/** Quality for the stored WebP: visually lossless on flat printed artwork. */
const QUALITY = 0.9;

/**
 * A 3×3 projective transform, row-major, with h22 fixed at 1.
 *
 * Eight unknowns, four point correspondences, two equations each.
 */
type Homography = number[];

/**
 * Solve for the homography mapping `from` onto `to`.
 *
 * The direct linear transform: each correspondence contributes two rows to an
 * 8×8 system, solved by Gaussian elimination with partial pivoting. Returns
 * `null` for a degenerate set — three collinear corners, or a code detected as
 * a sliver — rather than producing a transform that maps the image to nothing.
 */
export function solveHomography(from: Point[], to: Point[]): Homography | null {
  if (from.length !== 4 || to.length !== 4) {
    return null;
  }

  const matrix: number[][] = [];
  for (let index = 0; index < 4; index++) {
    const { x, y } = from[index];
    const { x: u, y: v } = to[index];
    matrix.push([x, y, 1, 0, 0, 0, -u * x, -u * y, u]);
    matrix.push([0, 0, 0, x, y, 1, -v * x, -v * y, v]);
  }

  for (let column = 0; column < 8; column++) {
    let pivot = column;
    for (let row = column + 1; row < 8; row++) {
      if (Math.abs(matrix[row][column]) > Math.abs(matrix[pivot][column])) {
        pivot = row;
      }
    }
    if (Math.abs(matrix[pivot][column]) < 1e-9) {
      return null;
    }
    [matrix[column], matrix[pivot]] = [matrix[pivot], matrix[column]];

    for (let row = 0; row < 8; row++) {
      if (row === column) {
        continue;
      }
      const factor = matrix[row][column] / matrix[column][column];
      for (let k = column; k <= 8; k++) {
        matrix[row][k] -= factor * matrix[column][k];
      }
    }
  }

  return matrix.map((row, index) => row[8] / row[index]).concat(1);
}

function apply(h: Homography, x: number, y: number): Point {
  const w = h[6] * x + h[7] * y + h[8];
  return { x: (h[0] * x + h[1] * y + h[2]) / w, y: (h[3] * x + h[4] * y + h[5]) / w };
}

export interface Rectified {
  canvas: HTMLCanvasElement;
  /** The margin this was produced with, so the caller can offer to change it. */
  margin: number;
}

/**
 * Flatten a photographed label and crop around its code.
 *
 * The code's corners are mapped to a square of a fixed size, which fixes how
 * many pixels one code-width is — so every label in the archive comes out at
 * the same effective resolution and they look like a set, however far away any
 * one photograph was taken from.
 *
 * Returns `null` when the corners do not describe a code, which is the caller's
 * cue to keep the photograph as it is rather than to fail.
 */
export function rectifyLabel(
  source: HTMLCanvasElement,
  corners: Point[],
  margin = DEFAULT_MARGIN,
): Rectified | null {
  const clamped = Math.min(MAX_MARGIN, Math.max(MIN_MARGIN, margin));
  const wanted = CODE_SIDE * (1 + clamped * 2);
  const side = Math.round(CODE_SIDE * Math.min(1, MAX_OUTPUT / wanted));
  const pad = Math.round(side * clamped);
  const size = side + pad * 2;

  // Fit the *inverse* directly by swapping the point lists: every destination
  // pixel needs its source, and fitting backwards is cheaper and steadier than
  // inverting a matrix that may be near-singular.
  const square: Point[] = [
    { x: pad, y: pad },
    { x: pad + side, y: pad },
    { x: pad + side, y: pad + side },
    { x: pad, y: pad + side },
  ];
  const inverse = solveHomography(square, corners);
  if (!inverse) {
    return null;
  }

  const context = source.getContext("2d", { willReadFrequently: true });
  if (!context) {
    return null;
  }
  const src = context.getImageData(0, 0, source.width, source.height);

  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const out = canvas.getContext("2d");
  if (!out) {
    return null;
  }
  const dst = out.createImageData(size, size);

  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const point = apply(inverse, x + 0.5, y + 0.5);
      sample(src, point.x - 0.5, point.y - 0.5, dst.data, (y * size + x) * 4);
    }
  }
  out.putImageData(dst, 0, 0);
  return { canvas, margin: clamped };
}

/**
 * Bilinear sample, writing RGBA into `target` at `offset`.
 *
 * Bilinear rather than nearest because a rectified label is nearly always being
 * shrunk or rotated a little, and nearest turns the printed digits into a mess
 * of stair-steps exactly where legibility is the point. Pixels outside the
 * photograph come out white, which reads as the edge of a sticker rather than
 * as a black border.
 */
function sample(
  src: ImageData,
  x: number,
  y: number,
  target: Uint8ClampedArray,
  offset: number,
): void {
  const x0 = Math.floor(x);
  const y0 = Math.floor(y);
  if (x0 < 0 || y0 < 0 || x0 + 1 >= src.width || y0 + 1 >= src.height) {
    target[offset] = 255;
    target[offset + 1] = 255;
    target[offset + 2] = 255;
    target[offset + 3] = 255;
    return;
  }

  const fx = x - x0;
  const fy = y - y0;
  const stride = src.width * 4;
  const a = (y0 * src.width + x0) * 4;
  const b = a + 4;
  const c = a + stride;
  const d = c + 4;

  for (let channel = 0; channel < 4; channel++) {
    const top = src.data[a + channel] * (1 - fx) + src.data[b + channel] * fx;
    const bottom = src.data[c + channel] * (1 - fx) + src.data[d + channel] * fx;
    target[offset + channel] = top * (1 - fy) + bottom * fy;
  }
}

/**
 * Encode a canvas for storage.
 *
 * WebP where the browser has it, JPEG otherwise — `toBlob` falls back to PNG
 * silently for a type it does not know, which would triple the size of a
 * photograph, so the result is checked rather than trusted.
 *
 * Re-encoding is also what strips EXIF. A phone tags photographs with the
 * coordinates they were taken at, and a book of device labels carrying the
 * location of the house they are in is not something to put in a backup.
 */
export function encodeLabel(canvas: HTMLCanvasElement): Promise<Blob | null> {
  return new Promise((resolve) => {
    canvas.toBlob(
      (blob) => {
        if (blob?.type === "image/webp") {
          resolve(blob);
          return;
        }
        canvas.toBlob((fallback) => resolve(fallback), "image/jpeg", QUALITY);
      },
      "image/webp",
      QUALITY,
    );
  });
}

/** Read a blob as base64, which is how it crosses a JSON WebSocket. */
export async function toBase64(blob: Blob): Promise<string> {
  const buffer = new Uint8Array(await blob.arrayBuffer());
  let binary = "";
  // In chunks: spreading a megabyte into String.fromCharCode at once overflows
  // the argument limit on every engine that has one.
  for (let index = 0; index < buffer.length; index += 0x8000) {
    binary += String.fromCharCode(...buffer.subarray(index, index + 0x8000));
  }
  return btoa(binary);
}
