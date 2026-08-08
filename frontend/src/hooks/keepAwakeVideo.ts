/**
 * The keep-awake fallback video: a one-pixel hidden element whose playback
 * keeps the compositor busy where the Wake Lock API is unavailable, which in
 * practice means an HTTP LAN URL, because that is not a secure context.
 *
 * Both halves of its life live here because they share one private detail, the
 * bookkeeping stashed on the element under `_edcaKeepAwake`. The hook holds a
 * ref to the element and never looks inside it.
 */

const CANVAS_EDGE_PX = 1;
const CANVAS_CAPTURE_FPS = 1;
const CANVAS_REPAINT_INTERVAL_MS = 1000;

/**
 * Two near-black fills alternated on the captured canvas. They differ so each
 * repaint is a real frame; both are invisible against the hidden element.
 */
const CANVAS_TICK_FILL = '#000';
const CANVAS_TICK_FILL_ALTERNATE = '#001';

/** Overlay geometry: present in the layout but occupying nothing visible. */
const HIDDEN_VIDEO_STYLE: Partial<CSSStyleDeclaration> = {
  position: 'fixed',
  width: '1px',
  height: '1px',
  opacity: '0',
  pointerEvents: 'none',
  left: '0',
  top: '0',
  zIndex: '-1',
};

type KeepAwakeMeta = { intervalId: number; stream: MediaStream };
type KeepAwakeVideo = HTMLVideoElement & { _edcaKeepAwake?: KeepAwakeMeta };
type CapturableCanvas = HTMLCanvasElement & { captureStream?: (fps?: number) => MediaStream };
type StreamSourced = { srcObject: MediaStream | null };

const TINY_MP4_DATA_URL =
  'data:video/mp4;base64,AAAAHGZ0eXBtcDQyAAAAAG1wNDJtcDQxaXNvbThtcDQyAAACAGlzb21pc28yYXZjMW1wNDEAAABsbW9vdgAAAGxtdmhkAAAAANr3xWna98VpAAABAAABR0gAAQAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgAAABR0cmFrAAAAXHRraGQAAAAD2vfFadr3xWkAAAABAAAAAAAAAUdIAAEAAAAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgAAAAAABAAAAAQAAAAAAAEAAQAAAAEAAAAAAAAAAAAAAAAAAAAAACR0a2hkAAAAA9r3xWna98VpAAAAAQAAAAAAAAFHSAABAAAAAAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgAAAAAABAAAAAQAAAAAAAEAAQAAAAEAAAAAAAAAAAAAAAAAAAAAAAABdHJha2QAAAAcZHRzZAAAAAABAAAAAQAAAAEAAAABAAAAAQAAAAAAAAABAAAAAQAAAAEAAAABAAAAAQAAAAAAAAABAAAAAQAAAAEAAAABAAAAAQAAAAAAAAABAAAAAQAAAAEAAAABAAAAAQAAAAAAAAABAAAAAQAAAAEAAAABAAAAAQAAAAAAAAABAAAAAQAAAAEAAAABAAAAAQAAAAAAAAABAAAAAQAAAAEAAAABAAAAAQAAAAAAAAABAAAAAQAAAAEAAAABAAAAAQAAAAAAAAABAAAAAQAAAAEAAAABAAAAAQAAAAAAAAABAAAAAQAAAAEAAAABAAAAAQAAAAAAAAABAAAAAQAAAAEAAAABAAAAAQAAAAAAAAABAAAAAQAAAAEAAAABAAAAAQAAAAAAAAABAAAAAQAAAAEAAAABAAAAAQAAAAAAAAABAAAAAQAAAAEAAAABAAAAAQAAAAAAAAABAAAAAQAAAAEAAAABAAAAAQAAAAAAAAABAAAAAQAAAAEAAAABAAAAAQAAAAAAAAABAAAAAQAAAAEAAAABAAAAAQAAAAAAAAABAAAAAQAAAAEAAAABAAAAAQAAAAAAAAABAAAAAQAAAAEAAAABAAAAAQAAAAAAAAABAAAAAQAAAAEAAAABAAAAAQAAAAAAAAABAAAAAQAAAAEAAAABAAAAAQAAAAAAAAABAAAAAQAAAAEAAAABAAAAAQAAAAAAAAABAAAAAQAAAAEAAAABAAAAAQAAAAAAAAABAAAAAQAAAAEAAAABAAAAAQAAAAAAAAABAAAAAQAAAAAAAAAA';

/**
 * Prefer a canvas capture stream, which needs no codec, over the data URL and
 * force frame production by repainting the canvas on an interval. A stream that
 * never changes is one a browser is free to treat as idle.
 */
const attachCanvasStream = (video: HTMLVideoElement): boolean => {
  const canvas = document.createElement('canvas') as CapturableCanvas;
  canvas.width = CANVAS_EDGE_PX;
  canvas.height = CANVAS_EDGE_PX;

  const captureStream = canvas.captureStream;
  if (typeof captureStream !== 'function' || !('srcObject' in video)) return false;

  const stream = captureStream.call(canvas, CANVAS_CAPTURE_FPS);
  (video as unknown as StreamSourced).srcObject = stream;

  const ctx = canvas.getContext('2d');
  let on = false;
  const intervalId = window.setInterval(() => {
    if (!ctx) return;
    on = !on;
    ctx.fillStyle = on ? CANVAS_TICK_FILL : CANVAS_TICK_FILL_ALTERNATE;
    ctx.fillRect(0, 0, CANVAS_EDGE_PX, CANVAS_EDGE_PX);
  }, CANVAS_REPAINT_INTERVAL_MS);

  (video as KeepAwakeVideo)._edcaKeepAwake = { intervalId, stream };
  return true;
};

export const createHiddenVideoElement = (): HTMLVideoElement => {
  const video = document.createElement('video');
  video.setAttribute('playsinline', 'true');
  video.muted = true;
  video.loop = true;
  video.preload = 'auto';

  try {
    if (!attachCanvasStream(video)) {
      video.src = TINY_MP4_DATA_URL;
    }
  } catch {
    video.src = TINY_MP4_DATA_URL;
  }

  Object.assign(video.style, HIDDEN_VIDEO_STYLE);

  return video;
};

/**
 * Tear the element down and take its capture stream with it. Every step is
 * best-effort: this runs from effect cleanup, where a failure to release is
 * worth less than an exception escaping.
 */
export const destroyHiddenVideoElement = (video: HTMLVideoElement): void => {
  try {
    const meta = (video as KeepAwakeVideo)._edcaKeepAwake;

    if (meta) {
      try { window.clearInterval(meta.intervalId); } catch {}
      try { meta.stream.getTracks().forEach((t) => t.stop()); } catch {}
      try { (video as unknown as StreamSourced).srcObject = null; } catch {}
      delete (video as KeepAwakeVideo)._edcaKeepAwake;
    }
  } catch {
    // ignore
  }

  try { video.pause(); } catch {}
  try { video.remove(); } catch {}
};
