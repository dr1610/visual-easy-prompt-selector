# Visual Easy Prompt Selector

Visual Easy Prompt Selector is a Stable Diffusion WebUI Forge/ReForge/AUTOMATIC1111 extension that shows Easy Prompt Selector YAML entries as searchable image cards in the Extra Networks area.

The extension reads Easy Prompt Selector files in read-only mode. It does not edit ESP YAML files.

## Quick Start

1. Copy this folder into your WebUI `extensions` directory:

```text
stable-diffusion-webui/extensions/visual-easy-prompt-selector
```

2. Restart WebUI.
3. Open the Extra Networks area and select the `Visual ESP` tab.

The package includes `sample_esp`, so the tab can open even when Easy Prompt Selector is not installed yet.

## First-Run Detection

On startup, the extension tries to use a real Easy Prompt Selector install when it is found next to this extension:

```text
extensions/sdweb-easy-prompt-selector
extensions/sd-easy-prompt-selector
extensions/easy-prompt-selector
```

If one of those folders exists and `config.json` still points only to `sample_esp`, Visual ESP automatically uses the detected folder. If nothing is found, it falls back to the bundled sample files.

To force a custom folder, edit `config.json`:

```json
{
  "esp_paths": [
    "../sdweb-easy-prompt-selector"
  ]
}
```

Relative paths are resolved from the Visual ESP extension folder.

## Features

- Adds a `Visual ESP` Extra Networks tab.
- Reads `.yml` and `.yaml` files from Easy Prompt Selector folders.
- Turns nested YAML entries into searchable cards.
- Inserts the selected ESP prompt into the active prompt box.
- Supports category, tag, text, AND/OR, and image/no-image filters.
- Supports optional preview images from `previews/`.
- Keeps local display names, tags, notes, and prompt edits in `visual_esp_metadata.json`.

## Preview Images

Preview images are optional. Put images under:

```text
previews/
```

The recommended generated-image structure is:

```text
previews/imported/
  image_mapping.json
  example_prompt_image.png
```

`image_mapping.json` maps ESP prompt text to image filenames:

```json
{
  "smile": "smile_example.png",
  "long hair": "long_hair_example.png"
}
```

If a prompt does not have a preview image, the extension can use `previews/placeholder.png`.

## Files Written Locally

The extension writes only inside its own folder:

- `config.json`
- `visual_esp_metadata.json`
- `previews/`

It does not modify Easy Prompt Selector, prompt YAML files, models, or other extensions.

## Troubleshooting

If the tab still shows only samples after installing Easy Prompt Selector, check `config.json`. If it contains a custom path, that custom setting is respected. Set it to your ESP folder or delete `config.json` and restart WebUI to regenerate it.

After updating the extension JavaScript, restart WebUI and hard-refresh the browser with `Ctrl + F5`.

## License

MIT License. See `LICENSE` for details.
