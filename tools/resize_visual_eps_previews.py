from __future__ import annotations

import json
import queue
import shutil
import sys
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageOps

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
SKIP_DIR_NAMES = {"_original_backup", "__pycache__"}


@dataclass
class ConvertResult:
    source: Path
    target: Path
    old_size: int
    new_size: int = 0
    skipped: str = ""


@dataclass
class ConvertOptions:
    previews_dir: Path
    max_size: int = 256
    quality: int = 84
    dry_run: bool = False
    backup_originals: bool = True
    remove_originals: bool = True
    update_refs: bool = True
    limit: int = 0
    min_kb: int = 0
    include_webp: bool = False


def extension_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def is_inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def target_for(path: Path) -> Path:
    return path.with_suffix(".webp")


def unique_backup_root(previews_dir: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    root = previews_dir / "_original_backup" / stamp
    counter = 2
    while root.exists():
        root = previews_dir / "_original_backup" / f"{stamp}_{counter}"
        counter += 1
    return root


def candidate_images(previews_dir: Path, min_bytes: int, include_webp: bool) -> list[Path]:
    files: list[Path] = []
    for path in previews_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        if path.name.lower() == "placeholder.png":
            continue
        if not include_webp and path.suffix.lower() == ".webp":
            continue
        if min_bytes and path.stat().st_size < min_bytes:
            continue
        files.append(path)
    return sorted(files, key=lambda item: item.stat().st_size, reverse=True)


def save_webp(source: Path, target: Path, max_size: int, quality: int) -> int:
    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image)
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
        image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        temp = target.with_name(target.stem + ".tmp.webp")
        image.save(temp, "WEBP", quality=quality, method=6)
    if target.exists():
        target.unlink()
    temp.replace(target)
    return target.stat().st_size


def rel_for(path: Path, base: Path) -> str:
    return path.resolve().relative_to(base.resolve()).as_posix()


def update_mapping_file(mapping_path: Path, old_name_to_new_name: dict[str, str]) -> bool:
    try:
        data = json.loads(mapping_path.read_text(encoding="utf-8-sig"))
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    changed = False
    for key, value in list(data.items()):
        value_text = str(value)
        new_name = old_name_to_new_name.get(value_text)
        if not new_name:
            mapped_path = mapping_path.parent / value_text
            fallback_webp = mapped_path.with_suffix(".webp")
            if not mapped_path.exists() and fallback_webp.exists():
                new_name = fallback_webp.name
        if new_name:
            data[key] = new_name
            changed = True
    if changed:
        mapping_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changed


def update_metadata(metadata_path: Path, old_rel_to_new_rel: dict[str, str]) -> bool:
    if not metadata_path.exists():
        return False
    try:
        data = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    changed = False
    for entry in data.values():
        if not isinstance(entry, dict):
            continue
        image = str(entry.get("image") or "")
        if image in old_rel_to_new_rel:
            entry["image"] = old_rel_to_new_rel[image]
            changed = True
    if changed:
        metadata_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changed



def update_yaml_refs(base_dir: Path, old_rel_to_new_rel: dict[str, str]) -> int:
    replacements: dict[str, str] = {}
    for old_rel, new_rel in old_rel_to_new_rel.items():
        old_path = Path(old_rel)
        new_path = Path(new_rel)
        replacements[old_rel] = new_rel
        replacements[old_rel.replace("/", "\\")] = new_rel.replace("/", "\\")
        replacements[old_path.name] = new_path.name

    if not replacements:
        return 0

    changed_count = 0
    yaml_paths = list(base_dir.rglob("*.yml")) + list(base_dir.rglob("*.yaml"))
    for yaml_path in yaml_paths:
        if any(part in SKIP_DIR_NAMES for part in yaml_path.parts):
            continue
        try:
            original = yaml_path.read_text(encoding="utf-8-sig")
        except Exception:
            continue
        updated = original
        for old_text, new_text in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
            updated = updated.replace(old_text, new_text)
        if updated == original:
            continue
        yaml_path.write_text(updated, encoding="utf-8")
        changed_count += 1
    return changed_count
def convert_previews(options: ConvertOptions, progress: Callable[[str], None] | None = None) -> tuple[list[ConvertResult], list[str]]:
    def log(message: str) -> None:
        if progress:
            progress(message)

    previews_dir = options.previews_dir.resolve()
    base_dir = previews_dir.parent.resolve()
    if not previews_dir.exists() or previews_dir.name != "previews":
        raise ValueError("Visual EPS の previews フォルダを選択してください。")
    if not is_inside(previews_dir, base_dir):
        raise ValueError("previews フォルダの指定が不正です。")

    min_bytes = max(0, int(options.min_kb)) * 1024
    files = candidate_images(previews_dir, min_bytes=min_bytes, include_webp=options.include_webp)
    if options.limit > 0:
        files = files[: options.limit]

    results: list[ConvertResult] = []
    messages: list[str] = []
    backup_root = unique_backup_root(previews_dir) if options.backup_originals and not options.dry_run else None
    old_rel_to_new_rel: dict[str, str] = {}
    per_mapping_updates: dict[Path, dict[str, str]] = {}

    total = len(files)
    old_total = sum(path.stat().st_size for path in files)
    log(f"対象画像: {total} 枚 / {old_total / 1024 / 1024:.2f} MB")

    for index, source in enumerate(files, start=1):
        target = target_for(source)
        old_size = source.stat().st_size
        result = ConvertResult(source=source, target=target, old_size=old_size)
        old_rel = rel_for(source, base_dir)
        new_rel = rel_for(target, base_dir)
        old_rel_to_new_rel[old_rel] = new_rel

        mapping_path = source.parent / "image_mapping.json"
        if mapping_path.exists():
            per_mapping_updates.setdefault(mapping_path, {})[source.name] = target.name

        if options.dry_run:
            results.append(result)
            if index % 100 == 0 or index == total:
                log(f"確認中: {index}/{total}")
            continue

        try:
            if backup_root:
                backup_target = backup_root / source.relative_to(previews_dir)
                backup_target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, backup_target)

            target.parent.mkdir(parents=True, exist_ok=True)
            result.new_size = save_webp(source, target, max_size=options.max_size, quality=options.quality)
            if options.remove_originals and source.resolve() != target.resolve() and source.exists():
                source.unlink()
        except Exception as exc:
            result.skipped = str(exc)
            log(f"失敗: {source.name} / {exc}")
        results.append(result)

        if index % 10 == 0 or index == total:
            log(f"変換中: {index}/{total}")

    if not options.dry_run and options.update_refs:
        for mapping_path, updates in per_mapping_updates.items():
            if update_mapping_file(mapping_path, updates):
                messages.append(f"参照を更新: {mapping_path.relative_to(base_dir)}")
        for metadata_name in ("visual_eps_metadata.json", "visual_esp_metadata.json"):
            metadata_path = base_dir / metadata_name
            if update_metadata(metadata_path, old_rel_to_new_rel):
                messages.append(f"参照を更新: {metadata_path.name}")
        yaml_changed = update_yaml_refs(base_dir, old_rel_to_new_rel)
        if yaml_changed:
            messages.append(f"YAML参照を更新: {yaml_changed} ファイル")

    if backup_root:
        messages.append(f"元画像のバックアップ先: {backup_root}")
    return results, messages


def format_summary(results: list[ConvertResult], messages: list[str], dry_run: bool) -> str:
    old_total = sum(item.old_size for item in results)
    new_total = sum(item.new_size for item in results)
    failed = sum(1 for item in results if item.skipped)
    lines = [
        f"モード: {'確認のみ' if dry_run else '変換済み'}",
        f"対象画像: {len(results)} 枚",
        f"変換前: {old_total / 1024 / 1024:.2f} MB",
    ]
    if not dry_run:
        lines.append(f"変換後: {new_total / 1024 / 1024:.2f} MB")
        if old_total:
            lines.append(f"削減量: {(old_total - new_total) / 1024 / 1024:.2f} MB")
        if failed:
            lines.append(f"失敗: {failed} 枚")
    lines.extend(messages)
    return "\n".join(lines)


def run_gui() -> None:
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext

    base = extension_dir()
    default_previews = base / "previews"
    events: queue.Queue[tuple[str, Any]] = queue.Queue()
    worker: threading.Thread | None = None

    root = tk.Tk()
    root.title("Visual EPS プレビュー画像 WebP 軽量化ツール")
    root.geometry("820x620")

    previews_var = tk.StringVar(value=str(default_previews))
    max_var = tk.IntVar(value=256)
    quality_var = tk.IntVar(value=84)
    limit_var = tk.IntVar(value=50)
    min_kb_var = tk.IntVar(value=100)
    include_webp_var = tk.BooleanVar(value=False)
    backup_var = tk.BooleanVar(value=True)
    remove_var = tk.BooleanVar(value=True)
    refs_var = tk.BooleanVar(value=True)
    status_var = tk.StringVar(value="待機中")

    frame = tk.Frame(root, padx=12, pady=12)
    frame.pack(fill="both", expand=True)

    tk.Label(frame, text="previews フォルダ").grid(row=0, column=0, columnspan=4, sticky="w")
    tk.Entry(frame, textvariable=previews_var).grid(row=1, column=0, columnspan=3, sticky="ew", padx=(0, 8))
    tk.Button(frame, text="参照", command=lambda: previews_var.set(filedialog.askdirectory(initialdir=previews_var.get()) or previews_var.get())).grid(row=1, column=3)

    tk.Label(frame, text="最大px").grid(row=2, column=0, sticky="w", pady=(10, 0))
    tk.Spinbox(frame, from_=64, to=1024, increment=32, textvariable=max_var, width=8).grid(row=3, column=0, sticky="w")
    tk.Label(frame, text="WebP品質").grid(row=2, column=1, sticky="w", pady=(10, 0))
    tk.Spinbox(frame, from_=40, to=100, increment=1, textvariable=quality_var, width=8).grid(row=3, column=1, sticky="w")
    tk.Label(frame, text="変換上限 0=全部").grid(row=2, column=2, sticky="w", pady=(10, 0))
    tk.Spinbox(frame, from_=0, to=999999, increment=10, textvariable=limit_var, width=10).grid(row=3, column=2, sticky="w")
    tk.Label(frame, text="最小サイズKB").grid(row=2, column=3, sticky="w", pady=(10, 0))
    tk.Spinbox(frame, from_=0, to=1048576, increment=50, textvariable=min_kb_var, width=10).grid(row=3, column=3, sticky="w")

    tk.Checkbutton(frame, text="既存WebPも再変換する", variable=include_webp_var).grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 0))
    tk.Checkbutton(frame, text="置換前に元画像をバックアップする", variable=backup_var).grid(row=5, column=0, columnspan=2, sticky="w")
    tk.Checkbutton(frame, text="WebP変換後に元のPNG/JPGを削除する", variable=remove_var).grid(row=6, column=0, columnspan=2, sticky="w")
    tk.Checkbutton(frame, text="image_mapping.json / metadata / YAML の画像パスを更新する", variable=refs_var).grid(row=7, column=0, columnspan=3, sticky="w")

    output = scrolledtext.ScrolledText(frame, height=20)
    output.grid(row=10, column=0, columnspan=4, sticky="nsew", pady=(12, 0))
    tk.Label(frame, textvariable=status_var).grid(row=9, column=0, columnspan=4, sticky="w", pady=(8, 0))

    def append(text: str) -> None:
        output.insert("end", text + "\n")
        output.see("end")

    def set_controls(enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for child in frame.winfo_children():
            if isinstance(child, (tk.Button, tk.Checkbutton, tk.Entry, tk.Spinbox)):
                child.configure(state=state)

    def build_options(dry_run: bool) -> ConvertOptions:
        return ConvertOptions(
            previews_dir=Path(previews_var.get()),
            max_size=int(max_var.get()),
            quality=int(quality_var.get()),
            dry_run=dry_run,
            backup_originals=bool(backup_var.get()),
            remove_originals=bool(remove_var.get()),
            update_refs=bool(refs_var.get()),
            limit=int(limit_var.get()),
            min_kb=int(min_kb_var.get()),
            include_webp=bool(include_webp_var.get()),
        )

    def start(dry_run: bool) -> None:
        nonlocal worker
        if worker and worker.is_alive():
            messagebox.showinfo("処理中", "現在の処理が終わるまで待ってください。")
            return
        output.delete("1.0", "end")
        set_controls(False)
        status_var.set("処理中...")
        options = build_options(dry_run)

        def target() -> None:
            try:
                results, messages = convert_previews(options, progress=lambda message: events.put(("log", message)))
                events.put(("done", (results, messages, options.dry_run)))
            except Exception as exc:
                events.put(("error", exc))

        worker = threading.Thread(target=target, daemon=True)
        worker.start()

    def poll() -> None:
        while True:
            try:
                kind, payload = events.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                append(str(payload))
            elif kind == "done":
                results, messages, dry_run = payload
                append("")
                append(format_summary(results, messages, dry_run))
                status_var.set("完了")
                set_controls(True)
            elif kind == "error":
                status_var.set("エラー")
                set_controls(True)
                messagebox.showerror("Visual EPS プレビュー画像 WebP 軽量化ツール", str(payload))
        root.after(100, poll)

    buttons = tk.Frame(frame)
    buttons.grid(row=8, column=0, columnspan=4, sticky="w", pady=(12, 0))
    tk.Button(buttons, text="確認のみ", command=lambda: start(True)).pack(side="left", padx=(0, 8))
    tk.Button(buttons, text="変換する", command=lambda: start(False)).pack(side="left")

    frame.columnconfigure(0, weight=1)
    frame.columnconfigure(1, weight=1)
    frame.columnconfigure(2, weight=1)
    frame.columnconfigure(3, weight=1)
    frame.rowconfigure(10, weight=1)
    root.after(100, poll)
    root.mainloop()


if __name__ == "__main__":
    if "--run" in sys.argv:
        dry_run = "--dry-run" in sys.argv
        options = ConvertOptions(previews_dir=extension_dir() / "previews", dry_run=dry_run)
        results, messages = convert_previews(options, progress=print)
        print(format_summary(results, messages, dry_run))
    else:
        run_gui()


