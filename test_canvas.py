from agent_app.canvas.docx import parse_docx_document
from agent_app.canvas.exporters import export_docx, export_latex
from agent_app.canvas.latex import parse_latex_document


def assert_block_type(document, block_type):
    assert any(block["type"] == block_type for block in document["blocks"]), block_type


def test_latex_round_trip_shape():
    source = r"""
\documentclass{article}
\title{A Canvas Paper}
\begin{document}
\maketitle
\section{Introduction}
This is a paragraph with \cite{smith2024} and \ref{fig:one}.

\begin{equation}
\label{eq:one}
E = mc^2
\end{equation}

\begin{figure}
\includegraphics{figures/one.png}
\caption{A sample figure}
\label{fig:one}
\end{figure}

\begin{tikzpicture}
\draw (0,0) -- (1,1);
\end{tikzpicture}
\end{document}
"""
    document = parse_latex_document(source, "paper.tex")
    assert document["title"] == "A Canvas Paper"
    assert_block_type(document, "heading")
    assert_block_type(document, "paragraph")
    assert_block_type(document, "equation")
    assert_block_type(document, "figure")
    assert_block_type(document, "raw_latex")

    exported = export_latex(document)
    assert r"\section{Introduction}" in exported
    assert r"\begin{equation}" in exported
    assert r"\includegraphics" in exported


def test_docx_export_import_shape():
    document = parse_latex_document(
        r"""
\title{DOCX Smoke}
\begin{document}
\section{Method}
The method works.
\begin{equation}
x = y + z
\end{equation}
\end{document}
""",
        "docx-smoke.tex",
    )
    content = export_docx(document)
    parsed, assets = parse_docx_document(content, "roundtrip.docx")
    assert assets == []
    assert parsed["title"] == "DOCX Smoke"
    assert_block_type(parsed, "heading")
    assert_block_type(parsed, "paragraph")


if __name__ == "__main__":
    test_latex_round_trip_shape()
    test_docx_export_import_shape()
    print("Canvas smoke tests passed.")
