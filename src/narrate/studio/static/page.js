// narrate studio: HTML scenes and overlays in the preview, scrubbed on their own clock (#73, #74, design D12-D13).
import { html, useEffect, useRef } from "./vendor/htm-preact.js";

/** An HTML scene at a moment of its scene. The page comes from /pages/ with a fake clock and its cues
    installed (page-clock.js moves the clock when told the time), laid out at its viewport and fitted
    into the frame as a build fits it (`page.box`). `time` is the moment in the scene; while `follow`
    (the scene's narration, an <audio>) plays, the page keeps up with it frame by frame instead.
    An `overlay` (#74) is transparent: the frame shows through wherever the page draws nothing. */
export function PageFrame({ page, time, follow, style, overlay = false }) {
  const frame = useRef(null);
  const latest = useRef(0);  // the page's time to show, sent again whenever the page (re)loads
  const post = () => {
    const target = frame.current && frame.current.contentWindow;
    if (target) target.postMessage({ narrate: "time", time: latest.current }, location.origin);
  };
  const pageTime = (sceneTime) => Math.max(0, sceneTime - page.start);
  useEffect(() => {
    if (follow) return;
    latest.current = pageTime(time);
    post();
  }, [page.url, page.start, time, follow]);
  useEffect(() => {
    if (!follow) return undefined;
    let id;
    const step = () => {
      latest.current = pageTime(follow.currentTime);
      post();
      id = requestAnimationFrame(step);
    };
    id = requestAnimationFrame(step);
    return () => cancelAnimationFrame(id);
  }, [page.url, page.start, follow]);
  const { left, top, scale_x: sx, scale_y: sy } = page.box;
  const [vw, vh] = page.size;
  return html`<div class=${overlay ? "page-frame overlay" : "page-frame"} data-testid=${overlay ? "overlay" : "page-frame"}
    style=${overlay ? style : `${style};background:${page.canvas}`}>
    <iframe ref=${frame} title=${overlay ? "overlay" : "frame"} src=${page.url} tabindex="-1" onLoad=${post}
      style=${`width:${vw}px;height:${vh}px;transform:translate(${left}px, ${top}px) scale(${sx}, ${sy})`}></iframe>
  </div>`;
}
