from pathlib import Path

from mdconverter.utils import (
    OUTPUT_FOLDER_PREFIX,
    SourceItem,
    discover_files,
    human_size,
    plan_output_paths,
    prepare_output_dir,
)


def touch(path: Path, text: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_discover_folder_filters_unsupported_and_hidden(tmp_path):
    root = tmp_path / "Reports"
    touch(root / "a.pdf")
    touch(root / "sub" / "b.docx")
    touch(root / "program.exe")
    touch(root / "~$lockfile.docx")
    touch(root / ".git" / "c.html")

    items = discover_files([root])

    names = sorted(i.path.name for i in items)
    assert names == ["a.pdf", "b.docx"]
    assert all(i.base == root.resolve() for i in items)


def test_explicit_files_are_kept_even_if_unsupported_and_deduplicated(tmp_path):
    f = touch(tmp_path / "notes.xyz")
    items = discover_files([f, f, tmp_path / "missing.pdf"])
    assert items == [SourceItem(f.resolve())]


def test_folder_hierarchy_is_replicated(tmp_path):
    root = tmp_path / "Reports"
    touch(root / "2024" / "q1.pdf")
    out = tmp_path / "out"

    [item] = discover_files([root])
    plan = plan_output_paths([item], out, overwrite=False)

    assert plan[item] == out / "Reports" / "2024" / "q1.md"


def test_name_collisions_get_numbered(tmp_path):
    a = SourceItem(touch(tmp_path / "x" / "report.pdf"))
    b = SourceItem(touch(tmp_path / "y" / "report.docx"))
    out = tmp_path / "out"

    plan = plan_output_paths([a, b], out, overwrite=False)

    assert plan[a] == out / "report.md"
    assert plan[b] == out / "report (1).md"


def test_existing_files_respected_unless_overwrite(tmp_path):
    item = SourceItem(touch(tmp_path / "doc.v1.2.pdf"))
    out = tmp_path / "out"
    touch(out / "doc.v1.2.md")

    assert plan_output_paths([item], out, overwrite=False)[item] == out / "doc.v1.2 (1).md"
    assert plan_output_paths([item], out, overwrite=True)[item] == out / "doc.v1.2.md"


def test_prepare_output_dir(tmp_path):
    stamped = prepare_output_dir(tmp_path, create_timestamped_subfolder=True)
    assert stamped.parent == tmp_path and stamped.name.startswith(OUTPUT_FOLDER_PREFIX)
    assert stamped.is_dir()
    assert prepare_output_dir(tmp_path / "fixed", create_timestamped_subfolder=False) == tmp_path / "fixed"


def test_human_size():
    assert human_size(512) == "512 B"
    assert human_size(2048) == "2.0 KB"
    assert human_size(5 * 1024**2) == "5.0 MB"
