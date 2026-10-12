// What narrate studio imports from CodeMirror: one module, bundled by
// scripts/vendor.sh into src/narrate/studio/static/vendor/codemirror.js
export { basicSetup, EditorView } from "codemirror";
export { Annotation, Compartment, EditorSelection, EditorState, RangeSetBuilder, StateEffect, StateField } from "@codemirror/state";
export { Decoration, GutterMarker, ViewPlugin, WidgetType, gutter, keymap } from "@codemirror/view";
export { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
export { markdown } from "@codemirror/lang-markdown";
export { lintGutter, linter, setDiagnostics } from "@codemirror/lint";
export { autocompletion } from "@codemirror/autocomplete";
export { indentWithTab } from "@codemirror/commands";
export { tags } from "@lezer/highlight";
