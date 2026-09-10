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

  let lazyImageObserver = null;

  function loadCardImage(card) {
    const image = q("img.preview[data-veps-src]", card);
    if (!image || image.dataset.vepsLoaded === "1") return;
    image.src = image.dataset.vepsSrc;
    image.dataset.vepsLoaded = "1";
  }

  function ensureLazyImageObserver() {
    if (lazyImageObserver || !("IntersectionObserver" in window)) return lazyImageObserver;
    lazyImageObserver = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        const image = entry.target;
        const card = image.closest(".veps-extra-card") || image;
        loadCardImage(card);
        lazyImageObserver.unobserve(image);
      }
    }, { rootMargin: "360px 0px" });
    return lazyImageObserver;
  }

  function setupLazyImages(root = document) {
    const observer = ensureLazyImageObserver();
    for (const image of qa("img.preview[data-veps-src]", root)) {
      if (image.dataset.vepsLoaded === "1" || image.dataset.vepsObserved === "1") continue;
      image.dataset.vepsObserved = "1";
      if (observer) {
        observer.observe(image);
      } else {
        const card = image.closest(".veps-extra-card");
        if (!card || !card.classList.contains("veps-filter-hidden")) loadCardImage(card || image);
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
    return image ? image.dataset.vepsSrc || image.src : "";
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

  function loadedPromptCount(page) {
    return qa(".card.veps-extra-card", page).length;
  }


  function nativeExtraSearchForPage(page) {
    return page && page.id ? document.getElementById(`${page.id}_extra_search`) : null;
  }

  function setNativeExtraSearch(page, value) {
    const nativeSearch = nativeExtraSearchForPage(page);
    if (!nativeSearch || nativeSearch.value === value) return;
    nativeSearch.value = value;
    nativeSearch.dispatchEvent(new Event("input", { bubbles: true }));
    nativeSearch.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function updateLoadControls(page, { loaded = false, loading = false, message = "" } = {}) {
    const button = q(".veps-load-button", page);
    const status = q(".veps-load-status", page);
    if (button) {
      button.disabled = loading;
      button.textContent = loading ? "Loading Visual EPS..." : loaded ? "Reload Visual EPS" : "Load Visual EPS";
    }
    if (status) status.textContent = message;
  }

  function syncToolbarTags(page) {
    const tagList = q(".veps-tag-list", page);
    if (!tagList) return;
    const tags = uniqueSorted(
      pageCards(page).flatMap((card) =>
        (card.dataset.vepsTags || "")
          .split(",")
          .map((tag) => tag.trim())
          .filter(Boolean)
      )
    );
    tagList.innerHTML = "";
    for (const tag of tags) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = `#${tag}`;
      button.dataset.tag = tag;
      tagList.appendChild(button);
    }
  }

  async function getLoadStatus() {
    const response = await fetch("/visual-eps/status");
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Failed to read Visual EPS status");
    return data;
  }

  function waitForVisualEspRefresh(page, expectedRevision) {
    let attempts = 0;
    const poll = () => {
      const tree = q(".veps-source-tree", page);
      const refreshComplete = tree && tree.dataset.vepsRevision === String(expectedRevision);
      if (refreshComplete) {
        page.dataset.vepsLoading = "0";
        syncToolbarTags(page);
        bindCards();
        updateLoadControls(page, {
          loaded: true,
          message: `${loadedPromptCount(page)} prompts loaded`,
        });
        return;
      }
      attempts += 1;
      if (attempts >= 600) {
        page.dataset.vepsLoading = "0";
        updateLoadControls(page, { loaded: false, message: "Load timed out. Try Load Visual EPS again." });
        return;
      }
      window.setTimeout(poll, 500);
    };
    window.setTimeout(poll, 500);
  }

  async function requestVisualEspLoad(page, force = false) {
    if (!page || page.dataset.vepsLoading === "1") return;
    page.dataset.vepsLoading = "1";
    updateLoadControls(page, { loading: true, message: "Reading EPS data after WebUI startup..." });
    try {
      const response = await fetch("/visual-eps/load", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ force }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Failed to start Visual EPS load");
      const refreshButton = document.getElementById(`${page.id}_extra_refresh_internal`);
      if (!refreshButton) throw new Error("Visual EPS refresh control is unavailable");
      refreshButton.click();
      waitForVisualEspRefresh(page, data.revision);
    } catch (error) {
      page.dataset.vepsLoading = "0";
      updateLoadControls(page, { loaded: false, message: error.message || String(error) });
    }
  }

  async function maybeLoadVisualEspOnOpen(page) {
    if (!page || pageCards(page).length || page.dataset.vepsLoading === "1") return;
    try {
      const status = await getLoadStatus();
      updateLoadControls(page, { loaded: status.loaded, message: status.loaded ? "Ready to display" : "Not loaded" });
      if (status.load_mode === "on_tab_open") await requestVisualEspLoad(page, false);
    } catch (error) {
      updateLoadControls(page, { loaded: false, message: error.message || String(error) });
    }
  }
  function visualEspTreeClickGuard(event) {
    const target = event.target instanceof Element ? event.target : null;
    if (!target) return;
    const content = target.closest(".veps-source-tree .tree-list-content-dir");
    if (!content) return;
    const page = content.closest("[id$='_visual_esp'], [id$='_visual_eps']");
    if (!page) return;
    const clickedChevron = target.closest(".tree-list-item-action--leading, .tree-list-item-action-chevron");
    if (clickedChevron) return;

    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();

    const search = nativeExtraSearchForPage(page);
    if (search) {
      search.value = content.dataset.path || "";
      search.dispatchEvent(new Event("input", { bubbles: true }));
    }
  }

  function buildToolbar(page) {
    if (page.dataset.vepsToolbarBound === "1") {
      syncToolbarTags(page);
      return;
    }
    page.dataset.vepsToolbarBound = "1";

    const toolbar = document.createElement("div");
    toolbar.className = "veps-extra-toolbar";
    toolbar.innerHTML = `
      <div class="veps-load-row">
        <button type="button" class="veps-load-button">Load Visual EPS</button>
        <span class="veps-load-status">Checking load mode...</span>
      </div>
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

    toolbar.addEventListener("click", (event) => {
      if (event.target.closest(".veps-load-button")) {
        event.preventDefault();
        requestVisualEspLoad(page, true);
        return;
      }
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
      for (const page of visualEspPages()) {
        setNativeExtraSearch(page, state.query);
      }
      window.setTimeout(bindCards, 80);
      window.setTimeout(applyFilters, 160);
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
    syncToolbarTags(page);
    getLoadStatus()
      .then((status) => {
        if (page.dataset.vepsLoading === "1") return;
        updateLoadControls(page, {
          loaded: status.loaded || pageCards(page).length > 0,
          message: pageCards(page).length > 0 ? `${loadedPromptCount(page)} prompts loaded` : status.loaded ? "Ready to display" : "Not loaded",
        });
      })
      .catch((error) => updateLoadControls(page, { loaded: false, message: error.message || String(error) }));
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
      setupLazyImages(page);
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


  async function resizeImageFileAsDataUrl(file, maxSize = 256, quality = 0.84) {
    if (!file) return { dataUrl: "", name: "" };
    if (!file.type || !file.type.startsWith("image/")) {
      return { dataUrl: await readFileAsDataUrl(file), name: file.name || "preview" };
    }

    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, maxSize / Math.max(bitmap.width, bitmap.height));
    const width = Math.max(1, Math.round(bitmap.width * scale));
    const height = Math.max(1, Math.round(bitmap.height * scale));
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d");
    context.drawImage(bitmap, 0, 0, width, height);
    if (bitmap.close) bitmap.close();

    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/webp", quality));
    if (!blob) return { dataUrl: await readFileAsDataUrl(file), name: file.name || "preview" };
    const dataUrl = await readFileAsDataUrl(blob);
    const stem = String(file.name || "preview").replace(/\.[^.]+$/, "");
    return { dataUrl, name: `${stem}.webp` };
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

  function refreshVisualEspPages(targetPage = null) {
    for (const page of targetPage ? [targetPage] : visualEspPages()) {
      const button = document.getElementById(`${page.id}_extra_refresh_internal`);
      if (button) button.click();
    }
  }

  async function openEdit(card, trigger) {
    const id = (trigger && trigger.dataset.vepsId) || card.dataset.vepsId;
    if (!id) throw new Error("Visual EPS item id is missing. Reload WebUI and try again.");
    const item = await getItem(id);
    const form = document.createElement("form");
    form.className = "veps-edit-form";
    form.innerHTML = `
      <label>Display name override<input name="display_name_override"></label>
      <label>Original EPS prompt (read only)<textarea name="prompt" readonly></textarea></label>
      <label>Prompt to prepend on insert<textarea name="prepend_prompt" placeholder="e.g. masterpiece, best quality"></textarea></label>
      <label>Prompt to append on insert<textarea name="append_prompt" placeholder="e.g. detailed eyes, soft lighting"></textarea></label>
      <label>Negative prompt to append<textarea name="append_negative" placeholder="e.g. low quality, bad anatomy"></textarea></label>
      <label>Tags<input name="tags" placeholder="e.g. hair, pose"></label>
      <label>Memo<textarea name="memo"></textarea></label>
      <label>Reference image<input name="image" type="file" accept="image/png,image/jpeg,image/webp"></label>
      <label class="veps-inline"><input name="clear_image" type="checkbox"> Clear current reference image link</label>
      <div class="veps-current-image"></div>
      <div class="veps-form-actions">
        <button type="submit">Save</button>
        <button type="button" class="veps-modal-close">Cancel</button>
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
    imageBox.innerHTML = imageSrc ? `<img src="${imageSrc}" alt=""><span>${item.image || ""}</span>` : "<span>No reference image</span>";

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const status = q(".veps-form-status", form);
      status.textContent = "Saving...";
      try {
        const file = form.elements.image.files[0];
        const imagePayload = await resizeImageFileAsDataUrl(file);
        await saveItem({
          id,
          display_name_override: form.elements.display_name_override.value,
          prepend_prompt: form.elements.prepend_prompt.value,
          append_prompt: form.elements.append_prompt.value,
          append_negative: form.elements.append_negative.value,
          tags: form.elements.tags.value,
          memo: form.elements.memo.value,
          clear_image: form.elements.clear_image.checked,
          image_data_url: imagePayload.dataUrl,
          image_name: imagePayload.name,
        });
        status.textContent = "Saved. Refreshing cards...";
        refreshVisualEspPages(pageForCard(card));
        setTimeout(closeModal, 600);
      } catch (error) {
        status.textContent = error.message || String(error);
      }
    });

    openModal(`Visual EPS edit: ${cardTitle(card)}`, form);
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
    setupLazyImages();
    for (const card of qa(".veps-extra-card:not(.veps-filter-hidden)").slice(0, 40)) {
      loadCardImage(card);
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
          openEdit(card, edit).catch((error) => alert(error.message || String(error)));
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


  function bindOnVisualEspInteraction(event) {
    const target = event.target instanceof Element ? event.target : null;
    if (!target) return;
    const tabButton = target.closest("button[id$='_visual_esp-button'], button[id$='_visual_eps-button']");
    if (tabButton) {
      const page = document.getElementById(tabButton.id.replace(/-button$/, ""));
      window.setTimeout(() => maybeLoadVisualEspOnOpen(page), 0);
    }
    if (!target.closest("[id$='_visual_esp'], [id$='_visual_eps'], button, .tab-nav, .tabs")) return;
    window.setTimeout(bindCards, 80);
    window.setTimeout(bindCards, 350);
  }
  document.addEventListener("DOMContentLoaded", bindCards);
  document.addEventListener("gradio:loaded", () => {
    bindCards();
    for (const page of visualEspPages()) {
      const tabButton = document.getElementById(`${page.id}-button`);
      if (tabButton && tabButton.getAttribute("aria-selected") === "true") {
        maybeLoadVisualEspOnOpen(page);
      }
    }
  });
  document.addEventListener("click", bindOnVisualEspInteraction, true);
  document.addEventListener("click", visualEspTreeClickGuard, true);
})();












