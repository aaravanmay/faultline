"""faultline mode-2 (probe / metamorphic) GENUINELY catching the real LangChain markdown bug. No LLM.

Run:  python3 bench/tool_caught/langchain_md_probe.py

Metamorphic test: a markdown doc and the SAME doc with its code fence left unterminated should
both preserve the text that follows. The `unterminate-code-fence` mutator makes that valid edit;
the property "all section content survives the split" then catches that the REAL
ExperimentalMarkdownSyntaxTextSplitter silently drops everything after the unterminated fence.
"""
import faultline as fl
from langchain_text_splitters import ExperimentalMarkdownSyntaxTextSplitter  # REAL, unpatched

DOC = "# Title\nintro\n\n```python\nx = 1\n```\n\n## Section Two\ncritical content\n"


def split_markdown(text):
    return ExperimentalMarkdownSyntaxTextSplitter(strip_headers=False).split_text(text)


def unterminate_fence(text):
    return text.replace("x = 1\n```", "x = 1\n", 1)   # drop the closing ``` (a valid, common edit)


def section_content_must_survive(inp, out, err):
    joined = "\n".join(d.page_content for d in (out or []))
    if err is None and "critical content" not in joined:
        return "the section after the unterminated code fence was silently dropped from the split"


cases = fl.mutations(DOC, ("unterminate-code-fence", unterminate_fence))
fl.probe(split_markdown, cases, [section_content_must_survive],
         label="LangChain markdown: content after fence", unpack=False).report()
