[README.md](https://github.com/user-attachments/files/28814072/README.md)
# Visual Easy Prompt Selector

Visual Easy Prompt Selector is an extension for Stable Diffusion WebUI, Forge, and reForge. It displays Easy Prompt Selector YAML entries as searchable visual cards in the Extra Networks panel.

The extension reads Easy Prompt Selector files in read-only mode. It does not edit your original YAML files.

## Status

Current test release: `v0.1-test2`

This is still a test release. Please report issues with your WebUI type, browser, and a short description of what happened.

## What It Does

- Adds a `Visual EPS` tab to Extra Networks.
- Reads `.yml` and `.yaml` files from Easy Prompt Selector folders.
- Converts nested YAML entries into searchable prompt cards.
- Inserts the selected prompt into the active prompt box.
- Supports text search, category filtering, tag filtering, AND/OR search, and image/no-image filtering.
- Supports optional preview images.
- Stores local display names, tags, notes, prompt additions, and preview-image links in this extension folder.

## Installation

### Recommended: install from Git URL

Use this method if you want WebUI's extension updater to work.

1. Open WebUI.
2. Go to `Extensions` > `Install from URL`.
3. Paste this URL:

```text
https://github.com/dr1610/visual-easy-prompt-selector.git
```

4. Click install.
5. Click `Apply and quit`.
6. Restart WebUI.

After this, future updates can be installed from:

```text
Extensions > Installed > Check for updates > Apply and quit
```

### ZIP/manual install

Manual install also works, but WebUI's update button will not update the extension automatically.

1. Download the ZIP or copy the folder.
2. Put it here:

```text
stable-diffusion-webui/extensions/visual-easy-prompt-selector
```

3. Restart WebUI.

If you installed an older ZIP test version, delete the old `visual-easy-prompt-selector` folder before installing the new one.

## Updating

### If installed from Git URL

1. Open `Extensions` > `Installed`.
2. Click `Check for updates`.
3. Click `Apply and quit`.
4. Restart WebUI.
5. Reload the browser page once.

### If installed from ZIP

1. Stop WebUI.
2. Delete the old `extensions/visual-easy-prompt-selector` folder.
3. Install the new version.
4. Restart WebUI.
5. Reload the browser page once.

## reForge Note

On reForge, after updating or on the first launch, Extra Networks may occasionally appear blank before the browser page is refreshed.

If `Checkpoint`, `LoRA`, or `Visual EPS` appears blank:

1. Reload the browser page.
2. If it is still blank, press `Ctrl + F5`.
3. If needed, restart WebUI once more.

`v0.1-test2` reworks the Visual EPS tree rendering so Visual EPS tree errors should not affect other Extra Networks pages.

## First Run

The extension tries to detect Easy Prompt Selector folders next to this extension:

```text
extensions/sdweb-easy-prompt-selector
extensions/sd-easy-prompt-selector
extensions/easy-prompt-selector
```

If no Easy Prompt Selector folder is found, the bundled `sample_esp` folder is used so the tab can still open.

To set a custom folder, edit `config.json`:

```json
{
  "esp_paths": [
    "../sdweb-easy-prompt-selector"
  ]
}
```

Relative paths are resolved from the Visual EPS extension folder.

## Preview Images

Preview images are optional.

Place images under:

```text
previews/
```

You can map prompt text to image filenames with `image_mapping.json`:

```json
{
  "smile": "smile_example.png",
  "long hair": "long_hair_example.png"
}
```

Recommended structure:

```text
previews/imported/
  image_mapping.json
  smile_example.png
  long_hair_example.png
```

If a prompt has no preview image, Visual EPS will show a normal card without a custom preview.

## Files Written by This Extension

Visual EPS writes only inside its own extension folder:

- `config.json`
- `visual_esp_metadata.json`
- `previews/custom/`

It does not modify:

- Easy Prompt Selector YAML files
- model files
- LoRA files
- other extensions
- WebUI settings outside this extension

## Troubleshooting

### The tab only shows sample prompts

Check `config.json`. If `esp_paths` points to `sample_esp`, change it to your Easy Prompt Selector folder.

You can also delete `config.json` and restart WebUI to let Visual EPS regenerate it.

### Checkpoint/LoRA/Visual EPS is blank after launch

Reload the browser page once. If needed, press `Ctrl + F5`.

### WebUI's update button does not update the extension

This usually means the extension was installed manually from ZIP. Install it from the GitHub URL if you want WebUI's updater to work.

### JavaScript or card UI looks old after updating

Restart WebUI and hard-refresh the browser with `Ctrl + F5`.

## Release Notes

### v0.1-test2

- Reworked Visual EPS Tree view rendering for reForge Extra Networks.
- Reduced the chance that Visual EPS interferes with initial Checkpoint/LoRA panel rendering.
- Added a safer fallback so Visual EPS tree errors do not affect other Extra Networks pages.

## License

MIT License. See `LICENSE` for details.
