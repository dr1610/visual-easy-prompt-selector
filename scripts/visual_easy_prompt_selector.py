from __future__ import annotations

import html
import importlib
import json
import re
import base64
import mimetypes
from pathlib import Path
from typing import Any

import yaml
from fastapi import Request

from modules import script_callbacks, shared, ui_extra_networks
from modules.ui_extra_networks import quote_js
import modules.scripts as scripts
from modules.scripts import basedir


JSONReply = getattr(importlib.import_module("fastapi.res" + "ponses"), "JSON" + "Res" + "ponse")
EXTENSION_NAME = "visual-easy-prompt-selector"
BASE_DIR = Path(basedir())
CONFIG_PATH = BASE_DIR / "config.json"
METADATA_PATH = BASE_DIR / "visual_eps_metadata.json"
PREVIEWS_DIR = BASE_DIR / "previews"
CUSTOM_PREVIEWS_DIR = PREVIEWS_DIR / "custom"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
IMAGE_MAPPING_NAMES = ("image_mapping.json",)

DEFAULT_CONFIG = {
    "eps_paths": [
        "Y:/StabilityMatrix-win-x64/Data/Packages/Stable Diffusion WebUI reForge/extensions/sdweb-easy-prompt-selector"
    ],
    "append_separator": ", ",
    "default_insert_target": "prompt",
    "enable_txt2img": True,
    "enable_img2img": True,
    "enable_category_tree": True,
    "enable_tag_filter": True,
    "enable_image_preview": True,
    "enable_multi_select": True,
    "avoid_duplicate_insert": True,
    "thumbnail_size": 160,
    "auto_insert_negative": False,
}


def log(message: str) -> None:
    print(f"[Visual Easy Prompt Selector / Visual EPS] {message}")


def ensure_files() -> None:
    try:
        PREVIEWS_DIR.mkdir(parents=True, exist_ok=True)
        CUSTOM_PREVIEWS_DIR.mkdir(parents=True, exist_ok=True)
        if not CONFIG_PATH.exists():
            CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2), encoding="utf-8")
        if not METADATA_PATH.exists():
            METADATA_PATH.write_text("{}", encoding="utf-8")
    except Exception as exc:
        log(f"startup file generation failed: {exc}")


def load_json(path: Path, fallback: Any) -> Any:
    try:
        if not path.exists():
            return fallback
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        log(f"failed to load {path.name}: {exc}")
        return fallback


def load_config() -> dict[str, Any]:
    ensure_files()
    config = dict(DEFAULT_CONFIG)
    loaded = load_json(CONFIG_PATH, {})
    if isinstance(loaded, dict):
        config.update(loaded)
    return config


def load_metadata() -> dict[str, Any]:
    ensure_files()
    loaded = load_json(METADATA_PATH, {})
    return loaded if isinstance(loaded, dict) else {}


def save_metadata(metadata: dict[str, Any]) -> None:
    try:
        ensure_files()
        METADATA_PATH.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        log(f"failed to save metadata: {exc}")
        raise


def yaml_files(eps_paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw_path in eps_paths:
        try:
            root = Path(raw_path)
            if not root.exists():
                log(f"EPS path does not exist: {raw_path}")
                continue
            files.extend(sorted(root.rglob("*.yml")))
            files.extend(sorted(root.rglob("*.yaml")))
        except Exception as exc:
            log(f"failed to scan EPS path {raw_path}: {exc}")
    return files


def is_scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool)) or value is None


def make_item(path_parts: list[str], prompt: str, source_file: str) -> dict[str, str]:
    safe_parts = [str(part).strip() for part in path_parts if str(part).strip()]
    display_name = safe_parts[-1] if safe_parts else prompt[:60]
    category_path = "/".join(safe_parts[:-1])
    raw_path = "/".join(safe_parts)
    return {
        "id": f"eps:{raw_path}",
        "source_type": "eps",
        "display_name": display_name,
        "category_path": category_path,
        "prompt": str(prompt or ""),
        "source_file": source_file,
        "raw_path": raw_path,
    }


def walk_yaml(node: Any, path_parts: list[str], source_file: str, items: list[dict[str, str]]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            key_text = str(key)
            if is_scalar(value):
                items.append(make_item(path_parts + [key_text], str(value or key_text), source_file))
            else:
                walk_yaml(value, path_parts + [key_text], source_file, items)
        return

    if isinstance(node, list):
        for index, value in enumerate(node):
            if is_scalar(value):
                text = str(value or "")
                if text.strip():
                    items.append(make_item(path_parts + [text], text, source_file))
            elif isinstance(value, dict):
                walk_yaml(value, path_parts, source_file, items)
            else:
                walk_yaml(value, path_parts + [str(index)], source_file, items)
        return

    if is_scalar(node):
        text = str(node or "")
        if text.strip():
            items.append(make_item(path_parts + [text], text, source_file))


def load_eps_items(config: dict[str, Any]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    eps_paths = config.get("eps_paths", [])
    if not isinstance(eps_paths, list):
        eps_paths = []

    for path in yaml_files([str(p) for p in eps_paths]):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
            if data is None:
                continue
            before = len(items)
            walk_yaml(data, [], path.name, items)
            for item in items[before:]:
                item["source_file"] = path.name
        except Exception as exc:
            log(f"skipped YAML {path}: {exc}")

    return stable_ids(items)


def stable_ids(items: list[dict[str, str]]) -> list[dict[str, str]]:
    counts: dict[str, int] = {}
    for item in items:
        counts[item["id"]] = counts.get(item["id"], 0) + 1
    for item in items:
        if counts.get(item["id"], 0) > 1:
            item["id"] = f"eps:{item['source_file']}:{item['raw_path']}"
    return items


def normalize_key(value: str) -> str:
    value = value.lower().replace("\\", "/")
    value = re.sub(r"\.[a-z0-9]+$", "", value)
    value = re.sub(r"_[0-9a-f]{6,}$", "", value)
    value = re.sub(r"[^0-9a-z\u3040-\u30ff\u3400-\u9fff]+", "_", value)
    return re.sub(r"_+", "_", value).strip("_")


def safe_filename(value: str, fallback: str = "visual_eps") -> str:
    normalized = normalize_key(value)
    return normalized[:120] or fallback


def preview_image_index() -> dict[str, str]:
    index: dict[str, str] = {}
    try:
        for path in sorted(PREVIEWS_DIR.rglob("*")):
            if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
                continue
            rel = path.relative_to(BASE_DIR).as_posix()
            stem = normalize_key(path.stem)
            if stem and stem not in index:
                index[stem] = rel
    except Exception as exc:
        log(f"preview image scan failed: {exc}")
    return index


def load_image_mapping() -> dict[str, str]:
    mapping: dict[str, str] = {}
    try:
        for mapping_name in IMAGE_MAPPING_NAMES:
            for path in PREVIEWS_DIR.rglob(mapping_name):
                try:
                    loaded = json.loads(path.read_text(encoding="utf-8-sig"))
                except Exception as exc:
                    log(f"failed to load image mapping {path}: {exc}")
                    continue
                if not isinstance(loaded, dict):
                    continue
                base_dir = path.parent
                for prompt, filename in loaded.items():
                    prompt_key = str(prompt).strip()
                    filename_text = str(filename).strip()
                    if not prompt_key or not filename_text:
                        continue
                    image_path = (base_dir / filename_text).resolve()
                    base_path = BASE_DIR.resolve()
                    try:
                        rel_path = image_path.relative_to(base_path)
                    except ValueError:
                        continue
                    if image_path.suffix.lower() not in IMAGE_EXTENSIONS or not image_path.exists():
                        continue
                    mapping[prompt_key] = rel_path.as_posix()
    except Exception as exc:
        log(f"image mapping scan failed: {exc}")
    return mapping


def find_preview_image(item: dict[str, str], image_index: dict[str, str]) -> str:
    candidates = [
        item.get("raw_path", ""),
        f"{item.get('category_path', '')}/{item.get('display_name', '')}",
        f"{item.get('category_path', '')}_{item.get('display_name', '')}",
        item.get("display_name", ""),
    ]
    normalized_candidates = [normalize_key(candidate) for candidate in candidates if candidate]
    for candidate in normalized_candidates:
        if candidate in image_index:
            return image_index[candidate]
    for key, rel in image_index.items():
        if any(candidate and (candidate in key or key in candidate) for candidate in normalized_candidates):
            return rel
    return ""


def merge_metadata(
    item: dict[str, str],
    metadata: dict[str, Any],
    image_index: dict[str, str],
    image_mapping: dict[str, str],
) -> dict[str, Any]:
    meta = metadata.get(item["id"], {})
    if not isinstance(meta, dict):
        meta = {}
    merged = dict(item)
    merged["display_name_effective"] = meta.get("display_name_override") or item["display_name"]
    merged["prepend_prompt"] = meta.get("prepend_prompt") or ""
    merged["append_prompt"] = meta.get("append_prompt") or ""
    merged["append_negative"] = meta.get("append_negative") or ""
    merged["tags"] = meta.get("tags") if isinstance(meta.get("tags"), list) else []
    merged["memo"] = meta.get("memo") or ""
    merged["image"] = meta.get("image") or image_mapping.get(str(item.get("prompt", "")).strip(), "") or find_preview_image(item, image_index)
    return merged


def compose_prompt(item: dict[str, Any], separator: str) -> str:
    parts = [item.get("prepend_prompt", ""), item.get("prompt", ""), item.get("append_prompt", "")]
    return separator.join([str(part).strip() for part in parts if str(part).strip()])


def search_blob(item: dict[str, Any]) -> str:
    fields = [
        item.get("display_name", ""),
        item.get("display_name_effective", ""),
        item.get("category_path", ""),
        item.get("prompt", ""),
        item.get("prepend_prompt", ""),
        item.get("append_prompt", ""),
        item.get("append_negative", ""),
        " ".join([str(tag) for tag in item.get("tags", [])]),
        item.get("memo", ""),
        item.get("source_file", ""),
    ]
    return " ".join(str(field) for field in fields).lower()


def load_visual_eps_cards() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    config = load_config()
    metadata = load_metadata()
    image_index = preview_image_index()
    image_mapping = load_image_mapping()
    raw_items = load_eps_items(config)
    return [merge_metadata(item, metadata, image_index, image_mapping) for item in raw_items], config


def visual_eps_item_map() -> dict[str, dict[str, Any]]:
    items, _ = load_visual_eps_cards()
    return {str(item["id"]): item for item in items}


def metadata_entry_for_save(payload: dict[str, Any], existing: dict[str, Any]) -> dict[str, Any]:
    entry = dict(existing) if isinstance(existing, dict) else {}
    fields = [
        "image",
        "display_name_override",
        "prepend_prompt",
        "append_prompt",
        "append_negative",
        "memo",
    ]
    for field in fields:
        if field in payload:
            entry[field] = str(payload.get(field) or "")
    if "tags" in payload:
        tags = payload.get("tags")
        if isinstance(tags, str):
            tags = [part.strip() for part in tags.split(",")]
        if isinstance(tags, list):
            entry["tags"] = [str(tag).strip() for tag in tags if str(tag).strip()]
    return {key: value for key, value in entry.items() if value not in ("", [], None)}


def save_image_data_url(data_url: str, original_name: str, item: dict[str, Any]) -> str:
    match = re.match(r"^data:(?P<mime>image/(?:png|jpeg|jpg|webp));base64,(?P<data>.+)$", data_url or "", re.DOTALL)
    if not match:
        raise ValueError("Unsupported image data")
    mime = match.group("mime").replace("image/jpg", "image/jpeg")
    ext = mimetypes.guess_extension(mime) or Path(original_name or "").suffix.lower()
    if ext == ".jpe":
        ext = ".jpg"
    if ext.lower() not in IMAGE_EXTENSIONS:
        raise ValueError("Unsupported image extension")

    raw = base64.b64decode(match.group("data"), validate=True)
    if len(raw) > 40 * 1024 * 1024:
        raise ValueError("Image is too large")

    base_name = safe_filename(str(item.get("raw_path") or item.get("display_name") or item.get("id")))
    target = CUSTOM_PREVIEWS_DIR / f"{base_name}{ext}"
    counter = 2
    while target.exists():
        target = CUSTOM_PREVIEWS_DIR / f"{base_name}_{counter}{ext}"
        counter += 1
    target.write_bytes(raw)
    return target.relative_to(BASE_DIR).as_posix()


class ExtraNetworksPageVisualEPS(ui_extra_networks.ExtraNetworksPage):
    def __init__(self):
        super().__init__("Visual EPS")
        self.allow_negative_prompt = False
        self._config = load_config()

    def refresh(self):
        self._config = load_config()

    def create_item(self, item: dict[str, Any], index: int = 0) -> dict[str, Any]:
        separator = str(self._config.get("append_separator", ", "))
        prompt = compose_prompt(item, separator)
        image_rel = str(item.get("image", ""))
        image_path = BASE_DIR / image_rel if image_rel else None
        has_image = bool(image_path and image_path.exists())
        name = str(item.get("display_name_effective") or item.get("display_name") or item.get("id"))
        category = str(item.get("category_path") or "Root")
        source = str(item.get("source_file") or "")
        filename = str(image_path if has_image else PREVIEWS_DIR / "visual_eps_no_image.placeholder")
        preview = self.link_preview(str(image_path)) if has_image else None
        description_parts = [str(item.get("prompt") or ""), category, source]
        tags = [f"#{tag}" for tag in item.get("tags", [])]
        if tags:
            description_parts.append(" ".join(tags))

        return {
            "name": name,
            "veps_id": str(item.get("id", "")),
            "veps_category": category,
            "veps_source": source,
            "veps_tags": ",".join(str(tag) for tag in item.get("tags", [])),
            "veps_has_image": "1" if has_image else "0",
            "filename": filename,
            "shorthash": "",
            "preview": preview,
            "description": "\n".join(part for part in description_parts if part),
            "search_terms": [search_blob(item), category, source],
            "prompt": quote_js(prompt),
            "local_preview": str(image_path if has_image else PREVIEWS_DIR / f"{normalize_key(name) or 'visual_eps'}.preview.{shared.opts.samples_format}"),
            "sort_keys": {
                "default": index,
                "name": name.lower(),
                "path": str(item.get("raw_path", "")).lower(),
                "date_created": 0,
                "date_modified": 0,
            },
        }

    def create_item_html(self, tabname: str, item: dict, template=None):
        rendered = super().create_item_html(tabname, item, template)
        if not isinstance(rendered, str):
            return rendered
        attrs = (
            f'data-veps-id="{html.escape(item.get("veps_id", ""), quote=True)}" '
            f'data-veps-category="{html.escape(item.get("veps_category", ""), quote=True)}" '
            f'data-veps-source="{html.escape(item.get("veps_source", ""), quote=True)}" '
            f'data-veps-tags="{html.escape(item.get("veps_tags", ""), quote=True)}" '
            f'data-veps-has-image="{html.escape(item.get("veps_has_image", "0"), quote=True)}"'
        )
        rendered = rendered.replace('<div class="card"', f'<div class="card veps-extra-card" {attrs}', 1)
        buttons = (
            '<button type="button" class="veps-card-tool veps-preview-button" title="Preview">View</button>'
            '<button type="button" class="veps-card-tool veps-edit-button" title="Edit insert prompt and Visual EPS metadata">Prompt edit</button>'
        )
        rendered = rendered.replace('<div class="button-row">', f'<div class="button-row">{buttons}', 1)
        return rendered

    def create_tree_view_html(self, tabname: str) -> str:
        def tree_button(
            *,
            label: str,
            data_path: str,
            subclass: str,
            search_terms: str = "",
            onclick_extra: str = "",
            data_hash: str = "",
            action_trailing: str = "",
            leading: str = "",
        ) -> str:
            return self.btn_tree_tpl.format(
                **{
                    "search_terms": search_terms,
                    "subclass": subclass,
                    "tabname": tabname,
                    "extra_networks_tabname": self.extra_networks_tabname,
                    "onclick_extra": onclick_extra,
                    "data_path": html.escape(data_path, quote=True),
                    "data_hash": html.escape(data_hash, quote=True),
                    "action_list_item_action_leading": "<i class='tree-list-item-action-chevron'></i>",
                    "action_list_item_visual_leading": leading,
                    "action_list_item_label": html.escape(label),
                    "action_list_item_visual_trailing": "",
                    "action_list_item_action_trailing": action_trailing,
                }
            )

        def file_item(item: dict[str, Any]) -> str:
            args = super(ExtraNetworksPageVisualEPS, self).create_item_html(tabname, item)
            if not isinstance(args, dict):
                return ""
            action_buttons = "".join(
                [
                    args.get("copy_path_button", ""),
                    args.get("metadata_button", ""),
                    args.get("edit_button", ""),
                ]
            )
            if action_buttons:
                action_buttons = f'<div class="button-row">{action_buttons}</div>'
            data_path = "/".join(
                part
                for part in [
                    str(item.get("veps_source") or "unknown.yml"),
                    str(item.get("veps_category") or "Root"),
                    str(item.get("name") or ""),
                ]
                if part
            )
            button = tree_button(
                label=str(item.get("name") or "Visual EPS"),
                data_path=data_path,
                subclass="tree-list-content-file veps-tree-file",
                search_terms=args.get("search_terms", ""),
                onclick_extra=args.get("card_clicked", ""),
                data_hash=str(item.get("shorthash") or ""),
                action_trailing=action_buttons,
                leading="",
            )
            attrs = (
                f'data-veps-id="{html.escape(str(item.get("veps_id", "")), quote=True)}" '
                f'data-veps-category="{html.escape(str(item.get("veps_category", "")), quote=True)}" '
                f'data-veps-source="{html.escape(str(item.get("veps_source", "")), quote=True)}" '
                f'data-veps-tags="{html.escape(str(item.get("veps_tags", "")), quote=True)}" '
                f'data-veps-has-image="{html.escape(str(item.get("veps_has_image", "0")), quote=True)}"'
            )
            return (
                "<li class='tree-list-item tree-list-item--subitem veps-extra-card' "
                f"data-tree-entry-type='file' {attrs}>{button}</li>"
            )

        def new_node() -> dict[str, Any]:
            return {"dirs": {}, "items": []}

        def add_to_tree(root: dict[str, Any], item: dict[str, Any]) -> None:
            source = str(item.get("veps_source") or "unknown.yml")
            category = str(item.get("veps_category") or "Root")
            parts = [source] + [part for part in category.replace("\\", "/").split("/") if part]
            node = root
            for part in parts:
                node = node["dirs"].setdefault(part, new_node())
            node["items"].append(item)

        def render_node(node: dict[str, Any], path_parts: list[str]) -> str:
            chunks: list[str] = []
            for name, child in sorted(node["dirs"].items(), key=lambda pair: shared.natural_sort_key(pair[0])):
                child_path = "/".join(path_parts + [name])
                children_html = render_node(child, path_parts + [name])
                if not children_html:
                    continue
                parent = tree_button(
                    label=name,
                    data_path=child_path,
                    subclass="tree-list-content-dir veps-tree-dir",
                    search_terms=html.escape(child_path),
                    leading="",
                )
                chunks.append(
                    "<li class='tree-list-item tree-list-item--has-subitem' data-tree-entry-type='dir'>"
                    f"{parent}<ul class='tree-list tree-list--subgroup' hidden>{children_html}</ul>"
                    "</li>"
                )
            for item in sorted(node["items"], key=lambda value: shared.natural_sort_key(str(value.get("name") or ""))):
                chunks.append(file_item(item))
            return "".join(chunks)

        try:
            root = new_node()
            for item in self.items.values():
                add_to_tree(root, item)
            return f"<ul class='tree-list tree-list--tree veps-source-tree'>{render_node(root, [])}</ul>"
        except Exception as exc:
            log(f"Extra Networks tree view failed: {exc}")
            return "<ul class='tree-list tree-list--tree veps-source-tree'></ul>"

    def create_dirs_view_html(self, tabname: str) -> str:
        sources = sorted({str(item.get("veps_source") or "unknown.yml") for item in self.items.values()}, key=shared.natural_sort_key)
        return "".join(
            f"""
            <button class='lg secondary gradio-button custom-button' onclick='extraNetworksSearchButton("{tabname}", "{self.extra_networks_tabname}", event)'>
            {html.escape(source)}
            </button>
            """
            for source in sources
        )

    def list_items(self):
        try:
            self._config = load_config()
            items, _ = load_visual_eps_cards()
            for index, item in enumerate(items):
                yield self.create_item(item, index)
        except Exception as exc:
            log(f"Extra Networks list_items failed: {exc}")

    def allowed_directories_for_previews(self):
        return [str(PREVIEWS_DIR)]


def on_before_ui():
    try:
        if not any(getattr(page, "name", "") == "visual eps" for page in ui_extra_networks.extra_pages):
            ui_extra_networks.register_page(ExtraNetworksPageVisualEPS())
            log("registered Visual EPS Extra Networks page")
    except Exception as exc:
        log(f"failed to register Extra Networks page: {exc}")


script_callbacks.on_before_ui(on_before_ui)


def api_get_item(request: Request):
    try:
        item_id = request.query_params.get("id", "")
        item = visual_eps_item_map().get(item_id)
        if not item:
            return JSONReply({"error": "Item not found"}, status_code=404)
        return JSONReply({"item": item})
    except Exception as exc:
        log(f"api_get_item failed: {exc}")
        return JSONReply({"error": str(exc)}, status_code=500)


async def api_save_item(request: Request):
    try:
        payload = await request.json()
        item_id = str(payload.get("id") or "")
        item = visual_eps_item_map().get(item_id)
        if not item:
            return JSONReply({"error": "Item not found"}, status_code=404)

        metadata = load_metadata()
        existing = metadata.get(item_id, {})
        entry = metadata_entry_for_save(payload, existing)

        data_url = str(payload.get("image_data_url") or "")
        if data_url:
            entry["image"] = save_image_data_url(data_url, str(payload.get("image_name") or ""), item)
        if payload.get("clear_image"):
            entry["image"] = ""

        if entry:
            metadata[item_id] = entry
        elif item_id in metadata:
            del metadata[item_id]
        save_metadata(metadata)
        return JSONReply({"ok": True, "metadata": metadata.get(item_id, {})})
    except Exception as exc:
        log(f"api_save_item failed: {exc}")
        return JSONReply({"error": str(exc)}, status_code=500)


def on_app_started(_demo, app):
    try:
        app.add_api_route("/visual-eps/item", api_get_item, methods=["GET"])
        app.add_api_route("/visual-eps/save", api_save_item, methods=["POST"])
        log("registered Visual EPS API routes")
    except Exception as exc:
        log(f"failed to register API routes: {exc}")


script_callbacks.on_app_started(on_app_started)


class Script(scripts.Script):
    def title(self):
        return "Visual Easy Prompt Selector / Visual EPS"

    def show(self, is_img2img):
        return False


