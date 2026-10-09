// The script editor: CodeMirror 6 with narrate's own line kinds highlighted.
import {
  Annotation, Decoration, EditorView, HighlightStyle, RangeSetBuilder, ViewPlugin, basicSetup, indentWithTab, keymap,
  markdown, syntaxHighlighting, tags,
} from "./vendor/codemirror.js";

// Changes that came from disk rather than the keyboard: they don't make the script unsaved
export const fromDisk = Annotation.define();

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

/** An editor in `parent` holding `text`; calls onChange() on typing and onSave() on Mod-S. */
export function createEditor(parent, text, { onChange, onSave, extensions = [] }) {
  const view = new EditorView({
    parent,
    doc: text,
    extensions: [
      basicSetup,
      markdown(),
      syntaxHighlighting(highlight),
      theme,
      narrateLines,
      EditorView.lineWrapping,
      keymap.of([indentWithTab, { key: "Mod-s", preventDefault: true, run: () => { onSave(); return true; } }]),
      EditorView.updateListener.of((update) => {
        if (update.docChanged && !update.transactions.some((t) => t.annotation(fromDisk))) onChange(update);
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
