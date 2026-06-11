(function () {
  "use strict";

  const state = {
    category: "",
    tag: "",
    image: "all",
    query: "",
    searchMode: "and",
  };

  function q(selector, root = document) {
    return root.querySelector(selector);
  }

  function qa(selector, root = document) {
    return Array.from(root.querySelectorAll(selector));
  }
  function protectToolbarControls(toolbar, selector) {
    for (const control of qa(selector, toolbar)) {
      for (const eventName of ["pointerdown", "mousedown", "click", "keydown"]) {
        control.addEventListener(eventName, (event) => {
          event.stopPropagation();
        });
      }
    }
  }

  function pageForCard(card) {
    return card.closest(".extra-page") || card.closest("[id$='_visual_esp'], [id$='_visual_eps']");
  }

  function visualEspPages() {
    return qa("[id$='_visual_esp'], [id$='_visual_eps']");
  }

  function cardTitle(card) {
    const title = q(".name", card);
    return title ? title.textContent.trim() : card.dataset.name || "Visual EPS";
  }

  function cardDescription(card) {
    const desc = q(".description", card);
    return desc ? desc.textContent.trim() : "";
  }

  function cardImage(card) {
    const image = q("img.preview", card);
    return image ? image.src : "";
  }

  function uniqueSorted(values) {
    return Array.from(new Set(values.filter(Boolean))).sort((a, b) => a.localeCompare(b));
  }

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function parseTokens(query) {
    const tokens = [];
    const re = /"([^"]+)"|(\S+)/g;
    let match;
    while ((match = re.exec(query || ""))) {
      tokens.push(String(match[1] || match[2] || "").toLowerCase().replace(/^#/, ""));
    }
    return tokens.filter(Boolean);
  }

  function cardSearchBlob(card) {
    return [
      card.textContent || "",
      card.dataset.vepsCategory || "",
      card.dataset.vepsSource || "",
      card.dataset.vepsTags || "",
    ]
      .join(" ")
      .toLowerCase();
  }

  function pageCards(page) {
    return qa(".veps-extra-card", page);
  }

  function visualEspTreeClickGuard(event) {
    const content = event.target.closest(".veps-source-tree .tree-list-content-dir");
    if (!content) return;
    const page = content.closest("[id$='_visual_esp'], [id$='_visual_eps']");
    if (!page) return;
    const clickedChevron = event.target.closest(".tree-list-item-action--leading, .tree-list-item-action-chevron");
    if (clickedChevron) return;

    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();

    const tabMatch = page.id.match(/^(txt2img|img2img)_visual_ep[sp]$/);
    const tabname = tabMatch ? tabMatch[1] : "";
    const search = tabname ? document.getElementById(`${tabname}_${page.id.endsWith("_visual_eps") ? "visual_eps" : "visual_esp"}_extra_search`) : null;
    if (search) {
      search.value = content.dataset.path || "";
      search.dispatchEvent(new Event("input", { bubbles: true }));
    }
  }

  function buildToolbar(page) {
    if (page.dataset.vepsToolbarBound === "1") return;
    page.dataset.vepsToolbarBound = "1";

    const cards = pageCards(page);
    const tags = uniqueSorted(
      cards.flatMap((card) =>
        (card.dataset.vepsTags || "")
          .split(",")
          .map((tag) => tag.trim())
          .filter(Boolean)
      )
    );

    const toolbar = document.createElement("div");
    toolbar.className = "veps-extra-toolbar";
    toolbar.innerHTML = `
      <div class="veps-filter-row">
        <input class="veps-local-search" type="search" placeholder="Visual EPS search">
        <select class="veps-search-mode" title="Search mode">
          <option value="and">AND</option>
          <option value="or">OR</option>
        </select>

        <select class="veps-image-select" title="Image filter">
          <option value="all">All images</option>
          <option value="with">Image only</option>
          <option value="without">No image</option>
        </select>
        <button type="button" class="veps-clear-filter">Clear</button>
      </div>
      <div class="veps-active-filter"></div>
      <div class="veps-tag-list"></div>
    `;



    protectToolbarControls(toolbar, ".veps-local-search, .veps-search-mode, .veps-image-select");

    const tagList = q(".veps-tag-list", toolbar);
    for (const tag of tags) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = `#${tag}`;
      button.dataset.tag = tag;
      tagList.appendChild(button);
    }

    toolbar.addEventListener("click", (event) => {
      const tagButton = event.target.closest("[data-tag]");

      if (tagButton) {
        state.tag = tagButton.dataset.tag || "";
        applyFilters();
      }
      if (event.target.closest(".veps-clear-filter")) {
        state.category = "";
        state.tag = "";
        state.image = "all";
        state.query = "";
        state.searchMode = "and";
        const imageSelect = q(".veps-image-select", toolbar);
        if (imageSelect) imageSelect.value = "all";
        const search = q(".veps-local-search", toolbar);
        if (search) search.value = "";
        const searchMode = q(".veps-search-mode", toolbar);
        if (searchMode) searchMode.value = "and";
        applyFilters();
      }
    });

    const search = q(".veps-local-search", toolbar);
    search.addEventListener("input", () => {
      state.query = search.value;
      applyFilters();
    });

    const searchMode = q(".veps-search-mode", toolbar);
    searchMode.addEventListener("change", () => {
      state.searchMode = searchMode.value;
      applyFilters();
    });

    const imageSelect = q(".veps-image-select", toolbar);
    imageSelect.addEventListener("change", () => {
      state.image = imageSelect.value;
      applyFilters();
    });

    page.prepend(toolbar);
    applyFilters();
  }

  function applyFilters() {
    for (const page of visualEspPages()) {
      let visible = 0;
      const cards = pageCards(page);
      for (const card of cards) {
        const tags = (card.dataset.vepsTags || "").split(",").map((tag) => tag.trim());
        const hasImage = card.dataset.vepsHasImage === "1";
        const tokens = parseTokens(state.query);
        const blob = cardSearchBlob(card);
        const tagMatch = !state.tag || tags.includes(state.tag);
        const imageMatch =
          state.image === "all" ||
          (state.image === "with" && hasImage) ||
          (state.image === "without" && !hasImage);
        const searchMatch =
          tokens.length === 0 ||
          (state.searchMode === "or"
            ? tokens.some((token) => blob.includes(token))
            : tokens.every((token) => blob.includes(token)));
        const show = tagMatch && imageMatch && searchMatch;
        card.classList.toggle("veps-filter-hidden", !show);
        if (show) visible += 1;
      }
      const active = q(".veps-active-filter", page);
      if (active) {
        const labels = [];
        if (state.tag) labels.push(`#${state.tag}`);
        if (state.image !== "all") labels.push(state.image === "with" ? "Image only" : "No image");
        if (state.query) labels.push(`${state.searchMode.toUpperCase()}: ${state.query}`);
        active.textContent = `${visible} / ${cards.length} visible${labels.length ? " - " + labels.join(" / ") : ""}`;
      }
    }
  }

  function ensureModal() {
    let modal = q("#veps-modal");
    if (modal) return modal;
    modal = document.createElement("div");
    modal.id = "veps-modal";
    modal.hidden = true;
    modal.innerHTML = `
      <div class="veps-modal-backdrop"></div>
      <div class="veps-modal-panel">
        <div class="veps-modal-head">
          <strong class="veps-modal-title">Visual EPS</strong>
          <button type="button" class="veps-modal-close">Close</button>
        </div>
        <div class="veps-modal-body"></div>
      </div>
    `;
    modal.addEventListener("click", (event) => {
      if (event.target.closest(".veps-modal-close") || event.target.classList.contains("veps-modal-backdrop")) {
        closeModal();
      }
    });
    document.body.appendChild(modal);
    return modal;
  }

  function openModal(title, body) {
    const modal = ensureModal();
    q(".veps-modal-title", modal).textContent = title;
    const modalBody = q(".veps-modal-body", modal);
    modalBody.innerHTML = "";
    modalBody.appendChild(body);
    modal.hidden = false;
  }

  function closeModal() {
    const modal = q("#veps-modal");
    if (modal) modal.hidden = true;
  }

  async function getItem(id) {
    const response = await fetch(`/visual-eps/item?id=${encodeURIComponent(id)}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Failed to load item");
    return data.item;
  }

  function readFileAsDataUrl(file) {
    return new Promise((resolve, reject) => {
      if (!file) {
        resolve("");
        return;
      }
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = () => reject(reader.error || new Error("Failed to read file"));
      reader.readAsDataURL(file);
    });
  }

  async function saveItem(payload) {
    const response = await fetch("/visual-eps/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Failed to save item");
    return data;
  }

  function refreshVisualEspPages() {
    for (const page of visualEspPages()) {
      const button = document.getElementById(`${page.id}_extra_refresh_internal`);
      if (button) button.click();
    }
  }

  async function openEdit(card) {
    const id = card.dataset.vepsId;
    const item = await getItem(id);
    const form = document.createElement("form");
    form.className = "veps-edit-form";
    form.innerHTML = `
      <label>陦ｨ遉ｺ蜷阪・荳頑嶌縺・input name="display_name_override"></label>
      <label>蜈・・ESP繝励Ο繝ｳ繝励ヨ・・ML縺ｯ螟画峩縺励∪縺帙ｓ・・textarea name="prompt" readonly></textarea></label>
      <label>繧ｯ繝ｪ繝・け譎ゅ↓蜑阪∈霑ｽ蜉縺吶ｋ繝励Ο繝ｳ繝励ヨ<textarea name="prepend_prompt" placeholder="萓・ masterpiece, best quality"></textarea></label>
      <label>繧ｯ繝ｪ繝・け譎ゅ↓蠕後ｍ縺ｸ霑ｽ蜉縺吶ｋ繝励Ο繝ｳ繝励ヨ<textarea name="append_prompt" placeholder="萓・ detailed eyes, soft lighting"></textarea></label>
      <label>Negative prompt縺ｸ霑ｽ蜉<textarea name="append_negative" placeholder="萓・ low quality, bad anatomy"></textarea></label>
      <label>Tags<input name="tags" placeholder="螟・ 豬ｷ, 豌ｴ逹"></label>
      <label>Memo<textarea name="memo"></textarea></label>
      <label>蜿り・判蜒・input name="image" type="file" accept="image/png,image/jpeg,image/webp"></label>
      <label class="veps-inline"><input name="clear_image" type="checkbox"> 迴ｾ蝨ｨ縺ｮ蜿り・判蜒上Μ繝ｳ繧ｯ繧貞､悶☆</label>
      <div class="veps-current-image"></div>
      <div class="veps-form-actions">
        <button type="submit">菫晏ｭ・/button>
        <button type="button" class="veps-modal-close">蜿匁ｶ・/button>
      </div>
      <div class="veps-form-status"></div>
    `;

    form.elements.display_name_override.value = item.display_name_override || "";
    form.elements.prompt.value = item.prompt || "";
    form.elements.prepend_prompt.value = item.prepend_prompt || "";
    form.elements.append_prompt.value = item.append_prompt || "";
    form.elements.append_negative.value = item.append_negative || "";
    form.elements.tags.value = Array.isArray(item.tags) ? item.tags.join(", ") : "";
    form.elements.memo.value = item.memo || "";
    const imageBox = q(".veps-current-image", form);
    const imageSrc = cardImage(card);
    imageBox.innerHTML = imageSrc ? `<img src="${imageSrc}" alt=""><span>${item.image || ""}</span>` : "<span>蜿り・判蜒上↑縺・/span>";

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const status = q(".veps-form-status", form);
      status.textContent = "菫晏ｭ倅ｸｭ...";
      try {
        const file = form.elements.image.files[0];
        const imageDataUrl = await readFileAsDataUrl(file);
        await saveItem({
          id,
          display_name_override: form.elements.display_name_override.value,
          prepend_prompt: form.elements.prepend_prompt.value,
          append_prompt: form.elements.append_prompt.value,
          append_negative: form.elements.append_negative.value,
          tags: form.elements.tags.value,
          memo: form.elements.memo.value,
          clear_image: form.elements.clear_image.checked,
          image_data_url: imageDataUrl,
          image_name: file ? file.name : "",
        });
        status.textContent = "菫晏ｭ倥＠縺ｾ縺励◆縲ゅき繝ｼ繝峨ｒ譖ｴ譁ｰ荳ｭ...";
        refreshVisualEspPages();
        setTimeout(closeModal, 600);
      } catch (error) {
        status.textContent = error.message || String(error);
      }
    });

    openModal(`Visual EPS邱ｨ髮・ ${cardTitle(card)}`, form);
  }

  function openPreview(card) {
    const body = document.createElement("div");
    body.className = "veps-preview-modal";
    const imageSrc = cardImage(card);
    body.innerHTML = `
      <div class="veps-large-image">${imageSrc ? `<img src="${imageSrc}" alt="">` : "<div>No Image</div>"}</div>
      <h3>${escapeHtml(cardTitle(card))}</h3>
      <p>${escapeHtml(card.dataset.vepsCategory || "Root")}</p>
      <pre></pre>
    `;
    q("pre", body).textContent = cardDescription(card);
    openModal(cardTitle(card), body);
  }

  function bindCards() {
    for (const page of visualEspPages()) {
      buildToolbar(page);
    }
    for (const card of qa(".veps-extra-card")) {
      if (card.dataset.vepsBound === "1") continue;
      card.dataset.vepsBound = "1";
      const edit = q(".veps-edit-button", card);
      const preview = q(".veps-preview-button", card);
      if (edit) {
        edit.addEventListener("click", (event) => {
          event.preventDefault();
          event.stopPropagation();
          openEdit(card).catch((error) => alert(error.message || String(error)));
        });
      }
      if (preview) {
        preview.addEventListener("click", (event) => {
          event.preventDefault();
          event.stopPropagation();
          openPreview(card);
        });
      }
    }
    applyFilters();
  }

  document.addEventListener("DOMContentLoaded", bindCards);
  document.addEventListener("gradio:loaded", bindCards);
  document.addEventListener("gradio:render", bindCards);
  document.addEventListener("click", visualEspTreeClickGuard, true);
  setInterval(bindCards, 1500);
})();



