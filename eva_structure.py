from pathlib import Path
import math

ROOT_DIR = Path(r"C:\Users\uneedme\eva")
OUTPUT_FILE = "eva_dump.txt"

EXCLUDE_DIRS = {
    ".git", "__pycache__", "node_modules",
    ".venv", "dist", "build", ".vs"
}

EXCLUDE_FILES = {OUTPUT_FILE}

TEXT_EXTENSIONS = {
    ".py", ".js", ".ts", ".php",
    ".html", ".css", ".tsx",
    ".json", ".md", ".txt",
    ".yml", ".yaml", ".env", ".sql"
}

# --- Unlimited content ---
KEEP_RATIO = 1           
MIN_LINES_REQUIRED = 5          
MAX_LINES_PER_FILE = None    


# =========================
# HELPERS
# =========================

def should_exclude(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)

    if any(part in EXCLUDE_DIRS for part in rel.parts):
        return True

    if path.name in EXCLUDE_FILES:
        return True

    return False


def is_text_file(path: Path) -> bool:
    return path.suffix.lower() in TEXT_EXTENSIONS


def smart_truncate(lines: list[str]) -> list[str]:
    """
    With KEEP_RATIO = 1 and MAX_LINES_PER_FILE = None,
    this function returns the full file content.
    """
    total = len(lines)

    keep = max(
        math.ceil(total * KEEP_RATIO),
        MIN_LINES_REQUIRED
    )

    if MAX_LINES_PER_FILE is not None:
        keep = min(keep, MAX_LINES_PER_FILE)

    return lines[:keep]


def code_language(ext: str) -> str:
    return {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".php": "php",
        ".html": "html",
        ".css": "css",
        ".json": "json",
        ".yml": "yaml",
        ".yaml": "yaml",
        ".sql": "sql",
        ".md": "markdown",
        ".tsx": "tsx",
    }.get(ext.lower(), "")


# =========================
# MAIN
# =========================

def dump_markdown_for_llm(root: Path, output_path: Path):
    with output_path.open("w", encoding="utf-8") as out:

        # -------- PROJECT CONTEXT --------
        out.write("# Project Dump\n\n")
        
        # -------- DIRECTORY TREE --------
        out.write("## Directory Tree\n\n")
        out.write("```text\n")
        for path in sorted(root.rglob("*")):
            if should_exclude(path, root):
                continue
            out.write(f"{path.relative_to(root)}\n")
        out.write("```\n\n")

        # -------- FILE CONTENTS --------
        out.write("## Files\n\n")

        for path in sorted(root.rglob("*")):
            if should_exclude(path, root):
                continue

            if not path.is_file():
                continue

            if not is_text_file(path):
                continue

            rel = path.relative_to(root)
            lang = code_language(path.suffix)

            out.write(f"### `{rel}`\n\n")
            out.write(f"- **Size:** {path.stat().st_size} bytes\n")
            out.write(f"- **Extension:** `{path.suffix}`\n\n")

            try:
                lines = path.read_text(
                    encoding="utf-8",
                    errors="replace"
                ).splitlines()

                content = smart_truncate(lines)

                out.write("```" + lang + "\n")
                out.write("\n".join(content))
                out.write("\n```\n\n")

            except Exception as e:
                out.write(f"> ❌ Error reading file: `{e}`\n\n")

        out.write("---\n")
        out.write("_End of dump_\n")


# =========================
# ENTRY POINT
# =========================

if __name__ == "__main__":
    dump_markdown_for_llm(ROOT_DIR, Path(OUTPUT_FILE))
    print(f"Markdown export completed → {OUTPUT_FILE}")
