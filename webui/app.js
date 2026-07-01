"use strict";

const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("file-input");
const fileListEl = document.getElementById("file-list");
const outputDirEl = document.getElementById("output-dir");
const headingEl = document.getElementById("heading-level");
const bookTitleEl = document.getElementById("book-title");
const titleField = document.getElementById("title-field");
const convertBtn = document.getElementById("convert-btn");
const browseBtn = document.getElementById("browse-btn");
const resultsEl = document.getElementById("results");
const logWrap = document.getElementById("log-wrap");
const logEl = document.getElementById("log");
const pandocBanner = document.getElementById("pandoc-banner");

/** Selected files, keyed by name+size to dedupe drops. */
let selected = [];

function fmtSize(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / 1024 / 1024).toFixed(1) + " MB";
}

function keyOf(f) {
  return f.name + ":" + f.size;
}

function addFiles(files) {
  for (const f of files) {
    if (!/\.(epub|fb2)$/i.test(f.name)) continue;
    if (selected.some((s) => keyOf(s) === keyOf(f))) continue;
    selected.push(f);
  }
  renderFileList();
}

function removeFile(key) {
  selected = selected.filter((f) => keyOf(f) !== key);
  renderFileList();
}

function renderFileList() {
  fileListEl.innerHTML = "";
  for (const f of selected) {
    const li = document.createElement("li");
    li.className = "file-list__item";
    li.innerHTML = `
      <span>📄</span>
      <span class="file-list__name"></span>
      <span class="file-list__size">${fmtSize(f.size)}</span>
      <button class="file-list__remove" title="Убрать">✕</button>`;
    li.querySelector(".file-list__name").textContent = f.name;
    li.querySelector(".file-list__remove").addEventListener("click", () =>
      removeFile(keyOf(f))
    );
    fileListEl.appendChild(li);
  }
  // Single-file title override only makes sense for one book.
  titleField.style.display = selected.length === 1 ? "" : "none";
  convertBtn.disabled = selected.length === 0;
}

/* ----------------------------- Drag & drop ----------------------------- */
["dragenter", "dragover"].forEach((evt) =>
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.add("dropzone--drag");
  })
);
["dragleave", "drop"].forEach((evt) =>
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    if (evt === "dragleave" && dropzone.contains(e.relatedTarget)) return;
    dropzone.classList.remove("dropzone--drag");
  })
);
dropzone.addEventListener("drop", (e) => addFiles(e.dataTransfer.files));
dropzone.addEventListener("click", () => fileInput.click());
dropzone.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") fileInput.click();
});
fileInput.addEventListener("change", () => addFiles(fileInput.files));

/* ------------------------------ Browse --------------------------------- */
browseBtn.addEventListener("click", async () => {
  browseBtn.disabled = true;
  try {
    const res = await fetch("/api/pick-folder", { method: "POST" });
    const data = await res.json();
    if (data.path) outputDirEl.value = data.path;
  } catch (err) {
    /* dialog cancelled or unavailable — ignore */
  } finally {
    browseBtn.disabled = false;
  }
});

/* ----------------------------- Convert --------------------------------- */
convertBtn.addEventListener("click", async () => {
  if (selected.length === 0) return;
  convertBtn.classList.add("btn--busy");
  convertBtn.disabled = true;
  resultsEl.innerHTML = "";
  logEl.textContent = "";
  logWrap.hidden = true;

  const fd = new FormData();
  for (const f of selected) fd.append("books", f, f.name);
  fd.append("output_dir", outputDirEl.value.trim());
  fd.append("heading_level", headingEl.value);
  if (selected.length === 1) fd.append("book_title", bookTitleEl.value.trim());

  try {
    const res = await fetch("/api/convert", { method: "POST", body: fd });
    const data = await res.json();
    if (data.error) {
      renderError(data.error);
    } else {
      renderResults(data.results);
    }
  } catch (err) {
    renderError(String(err));
  } finally {
    convertBtn.classList.remove("btn--busy");
    convertBtn.disabled = false;
  }
});

function renderError(msg) {
  const div = document.createElement("div");
  div.className = "result-card result-card--err";
  div.innerHTML = `<div class="result-card__title">⚠ Ошибка</div>
    <div class="result-card__err"></div>`;
  div.querySelector(".result-card__err").textContent = msg;
  resultsEl.appendChild(div);
}

function renderResults(results) {
  const allLogs = [];
  for (const r of results) {
    allLogs.push(`===== ${r.book} =====`, ...(r.log || []), "");
    const card = document.createElement("div");
    card.className = "result-card" + (r.ok ? "" : " result-card--err");

    if (r.ok) {
      card.innerHTML = `
        <div class="result-card__title">✅ <span></span></div>
        <div class="result-card__meta">${r.count} заметок · <span class="result-card__path"></span></div>
        <button class="btn btn--ghost result-card__open">Открыть папку</button>`;
      card.querySelector(".result-card__title span").textContent = r.book;
      card.querySelector(".result-card__path").textContent = r.output_path;
      card.querySelector(".result-card__open").addEventListener("click", () =>
        openFolder(r.output_path)
      );
    } else {
      card.innerHTML = `
        <div class="result-card__title">❌ <span></span></div>
        <div class="result-card__err"></div>`;
      card.querySelector(".result-card__title span").textContent = r.book;
      card.querySelector(".result-card__err").textContent = r.error;
    }
    resultsEl.appendChild(card);
  }
  logEl.textContent = allLogs.join("\n");
  logWrap.hidden = false;
}

async function openFolder(path) {
  try {
    await fetch("/api/open-folder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
  } catch (err) {
    /* ignore */
  }
}

/* ------------------------------ Health --------------------------------- */
(async function init() {
  try {
    const res = await fetch("/api/health");
    const data = await res.json();
    if (!data.pandoc) pandocBanner.classList.remove("banner--hidden");
    if (data.default_output && !outputDirEl.value) {
      outputDirEl.placeholder = data.default_output;
    }
  } catch (err) {
    /* ignore */
  }
})();
