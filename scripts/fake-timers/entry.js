// The fake clock an HTML scene runs on in the studio's preview (#73), bundled by scripts/vendor.sh
// into src/narrate/studio/static/vendor/fake-timers.js as a plain script defining NarrateFakeTimers
export { withGlobal } from "@sinonjs/fake-timers";
