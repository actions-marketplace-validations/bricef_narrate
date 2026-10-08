"""Convert downloaded Narakeet doc pages (<main> only) to Markdown.

Usage: python narakeet_html_to_md.py <html_dir> <out_dir>
"""
import pathlib
import re
import sys

from markdownify import MarkdownConverter


class Conv(MarkdownConverter):
    # Rouge wraps code in <div class="language-X highlighter-rouge"><pre><code>;
    # keep the language so fenced blocks stay readable.
    def convert_pre(self, el, text, parent_tags=None, **kw):
        lang = ""
        node = el.parent
        while node is not None and lang == "":
            for c in node.get("class", []) or []:
                if c.startswith("language-"):
                    lang = c[len("language-"):]
            node = node.parent if node.name != "body" else None
        code = el.get_text()
        fence = "````" if "```" in code else "```"
        return f"\n\n{fence}{lang}\n{code.rstrip()}\n{fence}\n\n"


def main():
    src, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    from bs4 import BeautifulSoup

    for f in sorted(src.glob("*.html")):
        soup = BeautifulSoup(f.read_text(encoding="utf-8"), "html.parser")
        main_el = soup.find("main") or soup.body
        for tag in main_el.find_all(["script", "style", "nav", "svg"]):
            tag.decompose()
        toc = main_el.find(id="markdown-toc")
        if toc:
            toc.decompose()
        md = Conv(heading_style="ATX", bullets="-").convert_soup(main_el)
        md = re.sub(r"\n{3,}", "\n\n", md).strip() + "\n"
        (out / (f.stem + ".md")).write_text(md, encoding="utf-8")
        print(f"{f.stem}: {len(md)} chars")


if __name__ == "__main__":
    main()
