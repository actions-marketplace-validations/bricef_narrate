// The script editor: CodeMirror 6 with narrate's own line kinds highlighted.
import {
  Annotation, Decoration, EditorView, HighlightStyle, RangeSetBuilder, StateEffect, StateField, ViewPlugin, WidgetType,
  basicSetup, indentWithTab, keymap, lintGutter, markdown, setDiagnostics, syntaxHighlighting, tags,
} from "./vendor/codemirror.js";

// Changes that came from disk rather than the keyboard: they don't make the script unsaved
export const fromDisk = Annotation.define();
// Cursor moves made for the user, such as following the timeline (#60): not the user moving on
export const quiet = Annotation.define();

const SEPARATOR = /^ {0,3}-{3,}\s*$/;
const FENCE = /^ {0,3}(`{3,}|~{3,})(.*)$/;
const DIRECTIVE = /^\s*\(\s*[A-Za-z][\w -]*?\s*:/;
const MEDIA = /^\s*!\[[^\]]*\]\(/;

/** The narrate kind of every line: header, scene separators, directions, media, slides, render blocks, SSML. */
export function lineKinds(doc) {
  const kinds = new Array(doc.lines + 1).fill(null);
  let fence = null, fenceKind = null, ssml = false, header = false;
  const first = doc.lines >= 1 ? doc.line(1).text : "";
  if (SEPARATOR.test(first)) header = true;
  for (let n = 1; n <= doc.lines; n++) {
    const text = doc.line(n).text;
    if (header) {
      kinds[n] = "header";
      if (n > 1 && SEPARATOR.test(text)) header = false;
      continue;
    }
    if (fence) {
      kinds[n] = fenceKind;
      const m = FENCE.exec(text);
      if (m && m[1][0] === fence[0] && m[1].length >= fence.length && !m[2].trim()) fence = null;
      continue;
    }
    const m = FENCE.exec(text);
    if (m) {
      fence = m[1];
      fenceKind = /^\s*render:/i.test(m[2]) ? "render" : "slide";
      kinds[n] = fenceKind;
      continue;
    }
    if (ssml || /^\s*<speak/.test(text)) {
      kinds[n] = "ssml";
      ssml = !/<\/speak>/.test(text);
      continue;
    }
    if (SEPARATOR.test(text)) kinds[n] = "scene";
    else if (DIRECTIVE.test(text)) kinds[n] = "directive";
    else if (MEDIA.test(text)) kinds[n] = "media";
  }
  return kinds;
}

function decorate(view) {
  const builder = new RangeSetBuilder();
  const kinds = lineKinds(view.state.doc);
  for (const { from, to } of view.visibleRanges) {
    for (let pos = from; pos <= to;) {
      const line = view.state.doc.lineAt(pos);
      if (kinds[line.number]) builder.add(line.from, line.from, Decoration.line({ class: `cm-narrate-${kinds[line.number]}` }));
      pos = line.to + 1;
    }
  }
  return builder.finish();
}

const narrateLines = ViewPlugin.fromClass(class {
  constructor(view) { this.decorations = decorate(view); }
  update(update) {
    if (update.docChanged || update.viewportChanged) this.decorations = decorate(update.view);
  }
}, { decorations: (plugin) => plugin.decorations });

// Colours come from the page's CSS variables (style.css), so light and dark schemes both follow
const highlight = HighlightStyle.define([
  { tag: tags.heading, fontWeight: "bold" },
  { tag: tags.emphasis, fontStyle: "italic" },
  { tag: tags.strong, fontWeight: "bold" },
  { tag: tags.strikethrough, textDecoration: "line-through" },
  { tag: [tags.link, tags.url], color: "var(--media)" },
  // Code inside fences takes its line's colour: grey for slides, orange for render blocks
  { tag: tags.contentSeparator, color: "var(--scene)", fontWeight: "bold" },
  { tag: tags.quote, color: "var(--muted)", fontStyle: "italic" },
  { tag: [tags.processingInstruction, tags.meta, tags.comment], color: "var(--muted)" },
]);

const theme = EditorView.theme({
  "&": { color: "var(--fg)", backgroundColor: "var(--panel)", height: "100%" },
  ".cm-gutters": { backgroundColor: "var(--panel)", color: "var(--muted)", borderRight: "1px solid var(--line)" },
  ".cm-activeLine": { backgroundColor: "color-mix(in srgb, var(--accent) 7%, transparent)" },
  ".cm-activeLineGutter": { backgroundColor: "color-mix(in srgb, var(--accent) 12%, transparent)" },
  ".cm-cursor, .cm-dropCursor": { borderLeftColor: "var(--fg)" },
  "&.cm-focused > .cm-scroller > .cm-selectionLayer .cm-selectionBackground, .cm-selectionBackground":
    { backgroundColor: "color-mix(in srgb, var(--accent) 28%, transparent)" },
  ".cm-foldPlaceholder": { backgroundColor: "transparent", border: "1px solid var(--line)", color: "var(--muted)" },
});

// -- what the server's analysis says about the script (#52) ----------------------

class Label extends WidgetType {
  constructor(text, className, title, playLine = null) {
    super(); this.text = text; this.className = className; this.title = title; this.playLine = playLine;
  }
  eq(other) {
    return other.text === this.text && other.className === this.className && other.title === this.title
      && other.playLine === this.playLine;
  }
  toDOM() {
    const span = document.createElement("span");
    span.className = this.className;
    span.textContent = this.text;
    if (this.title) span.title = this.title;
    if (this.playLine != null) {
      // A paragraph's length doubles as its play button (#54): the app listens for narrate-play
      span.setAttribute("role", "button");
      span.dataset.line = String(this.playLine);
      span.addEventListener("mousedown", (e) => {
        e.preventDefault();
        window.dispatchEvent(new CustomEvent("narrate-play", { detail: { line: this.playLine } }));
      });
    }
    return span;
  }
  ignoreEvent() { return true; }
}

const setLabels = StateEffect.define();

// Labels move with the text as it's edited, until the next analysis replaces them
const labels = StateField.define({
  create: () => Decoration.none,
  update(value, tr) {
    value = value.map(tr.changes);
    for (const effect of tr.effects) if (effect.is(setLabels)) value = effect.value;
    return value;
  },
  provide: (field) => EditorView.decorations.from(field),
});

export const seconds = (s) => (s < 60 ? `${s.toFixed(1)} s` : `${Math.floor(s / 60)}:${(s % 60).toFixed(1).padStart(4, "0")}`);

/** Show an analysis: scene labels on separators, paragraph lengths, and problems as diagnostics. */
export function showAnalysis(view, analysis) {
  const doc = view.state.doc;
  const widgets = [];
  const lineEnd = (n) => (n >= 1 && n <= doc.lines ? doc.line(n).to : null);
  for (const scene of analysis.scenes) {
    // The separator before the scene (its own first line for the first scene)
    const at = lineEnd(scene.index > 1 ? scene.line - 1 : scene.line);
    const length = scene.duration == null ? "can't be timed" : seconds(scene.duration);
    if (at != null) widgets.push(Decoration.widget({
      widget: new Label(`scene ${scene.index} · ${scene.title} · ${length}`, "cm-narrate-scene-label"), side: 1,
    }).range(at));
    for (const p of scene.paragraphs) {
      const end = lineEnd(p.line);
      if (end == null) continue;
      const length = seconds(p.end - p.start);
      widgets.push(Decoration.widget({
        widget: new Label(`▶ ${p.estimated ? "≈ " : ""}${length}`, `cm-narrate-length${p.estimated ? " estimated" : ""}`,
          `play the scene from here (${p.estimated ? "estimated from the text: not synthesised yet" : "synthesised"})`,
          p.line),
        side: 1,
      }).range(end));
    }
  }
  widgets.sort((a, b) => a.from - b.from);
  const diagnostics = analysis.problems.filter((p) => p.line >= 1 && p.line <= doc.lines).map((p) => {
    const line = doc.line(p.line);
    return { from: line.from, to: line.to, severity: p.severity, message: p.message };
  });
  view.dispatch(setDiagnostics(view.state, diagnostics));
  view.dispatch({ effects: setLabels.of(Decoration.set(widgets)) });
}

/** Put the cursor on `line` and bring it into view. */
export function goToLine(view, line) {
  const target = view.state.doc.line(Math.max(1, Math.min(line, view.state.doc.lines)));
  view.dispatch({ selection: { anchor: target.from }, scrollIntoView: true });
  view.focus();
}

/** Move the cursor to `line` to follow something else (the timeline), without taking the focus. */
export function followLine(view, line) {
  const target = view.state.doc.line(Math.max(1, Math.min(line, view.state.doc.lines)));
  if (view.state.doc.lineAt(view.state.selection.main.head).number === target.number) return;
  view.dispatch({ selection: { anchor: target.from }, scrollIntoView: true, annotations: quiet.of(true) });
}

/** An editor in `parent` holding `text`; calls onChange() on typing and onSave() on Mod-S. */
export function createEditor(parent, text, { onChange, onSave, onCursor = () => {}, extensions = [] }) {
  const view = new EditorView({
    parent,
    doc: text,
    extensions: [
      basicSetup,
      markdown(),
      syntaxHighlighting(highlight),
      theme,
      narrateLines,
      labels,
      lintGutter(),
      EditorView.lineWrapping,
      keymap.of([indentWithTab, { key: "Mod-s", preventDefault: true, run: () => { onSave(); return true; } }]),
      EditorView.updateListener.of((update) => {
        if (update.docChanged && !update.transactions.some((t) => t.annotation(fromDisk))) onChange(update);
        if (update.docChanged || update.selectionSet) {
          const followed = update.transactions.every((t) => t.annotation(quiet) || t.annotation(fromDisk));
          onCursor(update.state.doc.lineAt(update.state.selection.main.head).number, update.docChanged, followed);
        }
      }),
      ...extensions,
    ],
  });
  return {
    view,
    text: () => view.state.doc.toString(),
    /** Replace the text with the file's, keeping the cursor near where it was. */
    replace(newText) {
      const head = Math.min(view.state.selection.main.head, newText.length);
      view.dispatch({
        changes: { from: 0, to: view.state.doc.length, insert: newText },
        selection: { anchor: head },
        annotations: fromDisk.of(true),
      });
    },
  };
}
