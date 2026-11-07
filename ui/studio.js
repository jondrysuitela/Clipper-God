/* ============================================================
   ClipperGod Studio — lapisan data nyata.
   Tampilan, token, dan DOM berasal dari prototipe interaktif;
   file ini hanya mengganti data palsu dengan API lokal.
   ============================================================ */

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const pad = n => String(n).padStart(2, "0");
const tcode = s => `${pad(Math.floor(s / 60))}:${pad(Math.floor(s % 60))}.${pad(Math.floor((s % 1) * 100))}`;
const mmss = s => `${pad(Math.floor(s / 60))}:${pad(Math.floor(s % 60))}`;

const CAPTION_TEMPLATES = {
  punch:   { color: "#FFFFFF", highlight: "#FFD84D", outlineColor: "#000000", outline: 6, shadow: 3, uppercase: true, karaoke: true, box: false },
  karaoke: { color: "#FFFFFF", highlight: "#5FE3F0", outlineColor: "#000000", outline: 4, shadow: 2, uppercase: true, karaoke: true, box: false },
  boxed:   { color: "#FFFFFF", highlight: "#FFD84D", outlineColor: "#000000", outline: 2, shadow: 1, uppercase: true, karaoke: true, box: true },
  minimal: { color: "#FFFFFF", highlight: "#FFFFFF", outlineColor: "#000000", outline: 0, shadow: 0, uppercase: false, karaoke: false, box: false },
  neon:    { color: "#E9FCFF", highlight: "#5FE3F0", outlineColor: "#5FE3F0", outline: 3, shadow: 5, uppercase: true, karaoke: true, box: false },
  marker:  { color: "#FFFFFF", highlight: "#CBF24C", outlineColor: "#000000", outline: 5, shadow: 2, uppercase: true, karaoke: true, box: false },
  news:    { color: "#FFFFFF", highlight: "#FF8A65", outlineColor: "#000000", outline: 2, shadow: 2, uppercase: true, karaoke: true, box: true },
  classic: { color: "#FFFFFF", highlight: "#FFFFFF", outlineColor: "#000000", outline: 2, shadow: 1, uppercase: false, karaoke: false, box: false },
  gold:    { color: "#FFF4D6", highlight: "#FFB547", outlineColor: "#4A2100", outline: 6, shadow: 4, uppercase: true, karaoke: true, box: false },
};

const state = {
  projectId: null,
  projects: [],
  project: null, clips: [], words: [], clipId: null,
  playing: false, t: 0, filter: "all", tab: "caption",
  hl: "#FFD84D", style: "punch", font: "Arial Black", fontSize: 96,
  captionX: 50, captionY: 66, captionFonts: [],
  faces: true, karaoke: true, layout: "fill", outputFormat: "portrait", timelineZoom: 1,
  guides: false, sourceFile: null, sourcePreview: false, previewSource: false,
  health: null, poll: null, job: null, videoClip: null, lastHooks: null,
  ollamaHooks: true, ollamaModel: "llama3.2", clipAsrModel: "small",
};

try {
  const saved = JSON.parse(localStorage.getItem("clippergod.preferences") || "{}");
  state.projectId = localStorage.getItem("clippergod.activeProject") || null;
  if (Object.hasOwn(CAPTION_TEMPLATES, saved.style)) state.style = saved.style;
  if (/^#[0-9a-f]{6}$/i.test(saved.hl || "")) state.hl = saved.hl;
  if (typeof saved.font === "string" && saved.font.trim()) state.font = saved.font.trim();
  if (Number.isInteger(saved.captionX) && saved.captionX >= 10 && saved.captionX <= 90) {
    state.captionX = saved.captionX;
  }
  if (Number.isInteger(saved.captionY) && saved.captionY >= 10 && saved.captionY <= 90) {
    state.captionY = saved.captionY;
  }
  if (Number.isInteger(saved.fontSize) && saved.fontSize >= 68 && saved.fontSize <= 132) {
    state.fontSize = saved.fontSize;
  }
  if (typeof saved.faces === "boolean") state.faces = saved.faces;
  if (typeof saved.karaoke === "boolean") state.karaoke = saved.karaoke;
  if (["fill", "split", "three", "screenshare"].includes(saved.layout)) state.layout = saved.layout;
  if (["portrait", "square", "landscape"].includes(saved.outputFormat)) {
    state.outputFormat = saved.outputFormat;
  }
  if (typeof saved.ollamaHooks === "boolean") state.ollamaHooks = saved.ollamaHooks;
  if (typeof saved.ollamaModel === "string" && saved.ollamaModel.trim()) {
    state.ollamaModel = saved.ollamaModel.trim();
  }
  if (["small", "medium", "large-v3-turbo"].includes(saved.clipAsrModel)) {
    state.clipAsrModel = saved.clipAsrModel;
  }
} catch { /* preferensi rusak diabaikan */ }

function savePreferences() {
  try {
    localStorage.setItem("clippergod.preferences", JSON.stringify({
      style: state.style, hl: state.hl, font: state.font, fontSize: state.fontSize,
      captionX: state.captionX, captionY: state.captionY,
      faces: state.faces, karaoke: state.karaoke, layout: state.layout,
      outputFormat: state.outputFormat, ollamaHooks: state.ollamaHooks,
      ollamaModel: state.ollamaModel, clipAsrModel: state.clipAsrModel,
    }));
  } catch { /* penyimpanan lokal tidak wajib untuk menjalankan studio */ }
}

function captionSettings() {
  const template = CAPTION_TEMPLATES[state.style];
  return {
    font: state.font, size: state.fontSize,
    color: template.color, highlight: state.hl, outline_color: template.outlineColor,
    outline: template.outline, shadow: template.shadow,
    position_x: state.captionX, position_y: state.captionY,
    uppercase: template.uppercase, karaoke: state.karaoke, box: template.box,
  };
}

const NO_CUE_END = new Set(["yang","di","ke","dari","dan","atau","tapi","untuk","sama",
  "karena","padahal","kalau","itu","ini","sih","kan","banget"]);

const LAYOUT_LABEL = { fill: "Isi", split: "Split", three: "Tiga", screenshare: "Layar" };
const STATUS_LABEL = { candidate: "Kandidat", approved: "Disetujui", rejected: "Ditolak" };

/* ---------- util ---------- */
function api(path, options) {
  const { projectId, ...requestOptions } = options || {};
  const headers = new Headers(requestOptions.headers || {});
  const selectedProject = projectId || state.projectId;
  if (selectedProject) headers.set("X-ClipperGod-Project", selectedProject);
  return fetch(path, { ...requestOptions, headers }).then(async response => {
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    return data;
  });
}

function saveActiveProject() {
  try { localStorage.setItem("clippergod.activeProject", state.projectId); }
  catch { /* penyimpanan lokal tidak wajib untuk menjalankan studio */ }
}

async function loadWorkspaces() {
  const result = await api("/api/projects");
  state.projects = result.projects || [];
  if (!state.projects.length) throw new Error("Daftar proyek kosong.");
  if (!state.projects.some(project => project.id === state.projectId)) {
    state.projectId = result.default_id;
  }
  saveActiveProject();
  const select = $("#projectSelect");
  select.replaceChildren(...state.projects.map(project => {
    const option = document.createElement("option");
    option.value = project.id;
    option.textContent = project.name;
    option.selected = project.id === state.projectId;
    return option;
  }));
}

async function loadCaptionFonts() {
  const result = await api("/api/fonts");
  state.captionFonts = result.fonts || [];
  if (!state.captionFonts.length) {
    throw new Error("Font bawaan Windows yang didukung tidak ditemukan.");
  }
  if (!state.captionFonts.includes(state.font)) {
    state.font = state.captionFonts.includes("Arial Black")
      ? "Arial Black" : state.captionFonts[0];
    savePreferences();
  }
  const select = $("#fontSelect");
  select.replaceChildren(...state.captionFonts.map(font => {
    const option = document.createElement("option");
    option.value = font;
    option.textContent = font;
    option.style.fontFamily = `"${font}", sans-serif`;
    option.selected = font === state.font;
    return option;
  }));
}

async function switchWorkspace(projectId) {
  if (!projectId || projectId === state.projectId) return;
  clearTimeout(jobPoll);
  state.projectId = projectId;
  saveActiveProject();
  state.job = null;
  state.jobProjectId = null;
  $("#cancelActiveJobBtn").hidden = true;
  state.clipId = null;
  state.videoClip = null;
  state.previewSource = false;
  state.sourceFile = null;
  $("#sourceFile").value = "";
  $("#videoPath").value = "";
  $("#startJobBtn").disabled = false;
  $("#processClipBtn").disabled = false;
  $("#renderClipBtn").disabled = false;
  if (importBackdrop.classList.contains("open")) importBackdrop.classList.remove("open");
  await loadWorkspaces();
  await loadProject();
  pollJob(projectId);
}

$("#projectSelect").addEventListener("change", event => {
  switchWorkspace(event.target.value).catch(error => toast(error.message));
});

$("#createProjectBtn").addEventListener("click", async () => {
  const name = window.prompt("Nama proyek baru:");
  if (name === null) return;
  try {
    const project = await api("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    state.projectId = project.id;
    saveActiveProject();
    state.job = null;
    state.jobProjectId = null;
    $("#cancelActiveJobBtn").hidden = true;
    state.clipId = null;
    state.videoClip = null;
    state.previewSource = false;
    state.sourceFile = null;
    $("#sourceFile").value = "";
    $("#videoPath").value = "";
    $("#startJobBtn").disabled = false;
    $("#processClipBtn").disabled = false;
    $("#renderClipBtn").disabled = false;
    if (importBackdrop.classList.contains("open")) importBackdrop.classList.remove("open");
    await loadWorkspaces();
    await loadProject();
    pollJob(project.id);
  } catch (error) {
    toast(error.message);
  }
});

const wordText = text => String(text || "").replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, "");

function current() {
  return state.clips.find(c => c.id === state.clipId) || state.clips[0] || null;
}

function bucketOf(clip) {
  if (clip.status === "rejected") return "drop";
  if (clip.score >= 75) return "strong";
  return "review";
}

function flagOf(clip) {
  if (clip.status === "rejected") return "Ditolak";
  if (clip.status === "approved") return "Disetujui";
  if (bucketOf(clip) === "review") return "Perlu review";
  return null;
}

function cueGroups(words) {
  const out = [];
  let i = 0;
  while (i < words.length) {
    let n = Math.min(3, words.length - i);
    while (n < 5 && i + n < words.length && NO_CUE_END.has(wordText(words[i + n - 1].w).toLowerCase())) n++;
    out.push([i, i + n]);
    i += n;
  }
  return out;
}

/* ============================================================
   Muat proyek
   ============================================================ */
function mapProject(project) {
  state.project = project;
  const projectFormat = project.settings?.export?.format;
  const outputFormat = project.empty
    ? state.outputFormat
    : ["portrait", "square", "landscape"].includes(projectFormat)
      ? projectFormat : "portrait";
  state.outputFormat = outputFormat;
  $("#formatSel").value = outputFormat;
  state.words = (project.words || []).map(w => ({
    text: wordText(w.t), start: Number(w.s) || 0, end: Number(w.e) || 0,
    speaker: w.sp || null,
  }));

  state.clips = (project.clips || []).map(c => {
    const start = Number(c.start) || 0;
    const end = Number(c.end) || start;
    const dur = Math.max(0.001, end - start);
    const words = state.words
      .filter(w => w.end > start && w.start < end)
      .map(w => ({
        w: w.text,
        s: Math.max(0, w.start - start),
        e: Math.min(dur, w.end - start),
        sp: w.speaker,
      }));
    return {
      id: c.id, start, end, dur,
      title: c.title || "(tanpa judul)",
      score: c.score == null ? null : Math.round(c.score),
      status: c.status || "candidate",
      layout: c.layout || "fill",
      outputFormat,
      video: c.video || null,
      vps: c.vps || null,
      metrics: c.metrics || null,
      words,
    };
  });

  if (state.clipId && !state.clips.some(c => c.id === state.clipId)) state.clipId = null;
  if (!state.clipId && state.clips.length) state.clipId = state.clips[0].id;
}

async function loadProject() {
  let project;
  try {
    project = await api("/api/project");
  } catch (error) {
    $("#projName").textContent = "Proyek tidak bisa dibuka";
    $("#projMeta").textContent = error.message;
    return;
  }
  mapProject(project);
  const name = project.name || (project.empty ? "Proyek baru" : "Proyek");
  $("#projName").textContent = name;
  $("#projMeta").textContent = project.empty
    ? "belum ada video"
    : `${mmss(project.media?.duration || 0)} · ${state.words.length} kata · ${state.clips.length} klip`;
  $("#exportLbl").textContent = `Ekspor ${state.clips.length || ""}`.trim();

  state.t = 0;
  resetPlayer();
  renderAll();
}

/* ============================================================
   Kandidat
   ============================================================ */
function ringSvg(score) {
  const r = 19, c = 2 * Math.PI * r;
  return `<svg width="44" height="44" viewBox="0 0 44 44" aria-hidden="true">
    <circle class="track" cx="22" cy="22" r="${r}" fill="none" stroke-width="2.5"/>
    <circle class="val" cx="22" cy="22" r="${r}" fill="none" stroke-width="2.5"
      stroke-dasharray="${c.toFixed(1)}" stroke-dashoffset="${(c * (1 - score / 100)).toFixed(1)}"/>
  </svg><span class="num">${score}</span>`;
}

function renderClips() {
  const list = $("#clipList");
  const count = $("#clipCount");
  if (!list) return;

  if (!state.clips.length) {
    count.textContent = "0";
    list.innerHTML = `
      <div class="empty">
        <div class="empty-ico" aria-hidden="true">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M4 12h16M4 17h10"/></svg>
        </div>
        <h3>Belum ada klip</h3>
        <p>Pilih video podcast, lalu mesin memotongnya jadi klip vertikal di komputer ini.</p>
        <button class="btn primary" data-empty-action>Buat klip</button>
      </div>`;
    return;
  }

  const items = state.clips.filter(c => state.filter === "all" ? true : bucketOf(c) === state.filter);
  count.textContent = `${items.length} / ${state.clips.length}`;

  if (!items.length) {
    list.innerHTML = `
      <div class="empty">
        <div class="empty-ico" aria-hidden="true">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M4 12h16M4 17h10"/></svg>
        </div>
        <h3>Tidak ada klip di filter ini</h3>
        <p>Semua kandidat lolos batas aman. Klip yang ditolak mesin akan muncul di sini beserta alasannya.</p>
        <button class="btn" data-empty-action>Tampilkan semua</button>
      </div>`;
    return;
  }

  list.innerHTML = items.map(clip => {
    const flag = flagOf(clip);
    const cls = clip.status === "rejected" ? "danger" : "";
    const score = clip.score == null ? 0 : clip.score;
    return `
      <button class="clip" role="option" aria-selected="${clip.id === state.clipId}" data-clip="${clip.id}">
        <span class="score-ring ${score < 55 ? "low" : ""}">${ringSvg(score)}</span>
        <span class="clip-body">
          <span class="clip-title">${escapeHtml(clip.title)}</span>
          <span class="clip-meta">${tcode(clip.dur).slice(0, 5)} ${flag ? `<span class="clip-flag ${cls}">${flag}</span>` : ""}</span>
        </span>
      </button>`;
  }).join("");
}

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, ch => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));
}

/* ============================================================
   Panggung + pemutar
   ============================================================ */
function resetPlayer() {
  const player = $("#player");
  if (!player) return;
  player.pause?.();
  state.playing = false;
  state.videoClip = null;
  state.sourcePreview = false;
  state.previewSource = false;
  syncPlayIcon();
}

function bindVideo(clip) {
  const player = $("#player");
  const img = $("#frameImg");
  const capLayer = $(".cap-layer");
  const note = $("#stageNote");
  const frame = $("#ytFrame");
  const mediaPath = state.project?.media?.path || "";
  const sourceUrl = state.project?.extra?.source_url
    || (/^https?:\/\//i.test(mediaPath) ? mediaPath : "");
  const localSourceAvailable = Boolean(state.project?.media?.local_available)
    || Boolean(mediaPath && !/^https?:\/\//i.test(mediaPath));

  frame.hidden = true;
  frame.removeAttribute("src");

  if (clip && clip.video && !state.previewSource) {
    if (state.videoClip !== clip.id) {
      player.src = `/api/clip?id=${encodeURIComponent(clip.id)}&project_id=${encodeURIComponent(state.projectId)}`;
      state.videoClip = clip.id;
    }
    state.sourcePreview = false;
    player.hidden = false;
    img.hidden = true;
    capLayer.hidden = true;
    note.hidden = true;
    return;
  }

  if (clip && localSourceAvailable) {
    const sourceKey = `source:${clip.id}`;
    if (state.videoClip !== sourceKey) {
      player.pause?.();
      player.src = `/api/source?project_id=${encodeURIComponent(state.projectId)}`;
      state.videoClip = sourceKey;
    }
    state.sourcePreview = true;
    player.hidden = false;
    img.hidden = true;
    capLayer.hidden = false;
    note.hidden = true;
    return;
  }

  player.pause?.();
  player.removeAttribute("src");
  player.hidden = true;
  state.videoClip = null;

  state.sourcePreview = false;
  if (clip && sourceUrl) {
    img.hidden = true;
    capLayer.hidden = true;
    note.hidden = false;
  } else {
    img.hidden = false;
    capLayer.hidden = false;
    note.hidden = true;
  }
}

function renderStage() {
  const clip = current();
  const title = $("#stageTitle");
  const badge = $("#clipStatus");

  if (!clip) {
    $("#processClipBtn").hidden = true;
    $("#sourcePreviewBtn").hidden = true;
    $("#renderClipBtn").hidden = true;
    $("#phone").dataset.format = "portrait";
    title.textContent = state.project?.empty ? "Belum ada video" : "Belum ada klip";
    badge.textContent = "";
    badge.className = "badge";
    $("#tTot").textContent = "00:00.00";
    $("#tNow").textContent = "00:00.00";
    $("#sumDur").textContent = "—";
    $("#sumWords").textContent = "—";
    $("#sumSpeakers").textContent = "—";
    $("#sumTag").hidden = true;
    $("#transcript").innerHTML = `<span class="row-sub">Transkrip akan muncul setelah klip pertama selesai.</span>`;
    $("#cap").innerHTML = "";
    bindVideo(null);
    return;
  }

  $("#phone").dataset.format = clip.outputFormat || "portrait";
  bindVideo(clip);
  $("#processClipBtn").hidden = Boolean(clip.video);
  $("#sourcePreviewBtn").hidden = !(clip.video && state.project?.media?.local_available);
  $("#sourcePreviewBtn").textContent = state.previewSource ? "Preview hasil" : "Preview sumber";
  $("#renderClipBtn").hidden = false;
  $("#renderClipBtn").textContent = clip.video ? "Render ulang" : "Render final";
  title.textContent = clip.title;
  badge.textContent = STATUS_LABEL[clip.status] || clip.status;
  badge.className = "badge " + (clip.status === "approved" ? "ok" : clip.status === "rejected" ? "danger" : "warn");

  const dur = clip.dur;
  $("#tTot").textContent = tcode(dur);
  $("#sumDur").textContent = clip.dur.toFixed(1).replace(".", ",") + " s";
  $("#sumWords").textContent = clip.words.length + " kata";

  const speakers = new Set(clip.words.map(w => w.sp).filter(Boolean));
  $("#sumSpeakers").textContent = speakers.size ? `${speakers.size} pembicara` : "1 pembicara";
  const tag = $("#sumTag");
  if (clip.metrics && clip.metrics.lufs != null) {
    tag.hidden = false;
    tag.textContent = "audio terukur";
  } else {
    tag.hidden = true;
  }

  const metrics = clip.metrics || {};
  $("#dCut").textContent = metrics.cut_rate == null ? "—" : metrics.cut_rate;
  $("#dLufs").textContent = metrics.lufs == null ? "—" : String(metrics.lufs).replace(".", ",") + " LUFS";
  $("#dSsim").textContent = metrics.loop_ssim == null ? "—" : String(metrics.loop_ssim).replace(".", ",");
  $("#dWps").textContent = (clip.words.length / dur).toFixed(2).replace(".", ",");

  $("#bStart").textContent = `${mmss(clip.start)} · ${LAYOUT_LABEL[clip.layout] || clip.layout}`;
  $("#bEnd").textContent = `${mmss(clip.end)} · ${(clip.end - clip.start).toFixed(1)} s`;

  renderTranscript(clip);
  renderOverlayCaption(clip);
  updateTimeUi(clip);
}

function renderTranscript(clip) {
  const active = clip.words.findIndex(w => state.t >= w.s && state.t < w.e);
  const speaker = clip.words.find(w => w.sp)?.sp;
  $("#tSpeaker").textContent = "Transkrip" + (speaker ? ` · ${speaker}` : "");
  $("#transcript").innerHTML = clip.words.length
    ? clip.words.map((w, i) => `<span class="word ${i === active ? "on" : ""}" data-i="${i}">${escapeHtml(w.w)}</span>`).join(" ")
    : `<span class="row-sub">Kata tidak tersimpan untuk klip ini.</span>`;

  if (active >= 0) {
    requestAnimationFrame(() => {
      const el = $(`#transcript .word[data-i="${active}"]`);
      if (el) el.scrollIntoView({ block: "nearest", inline: "nearest" });
    });
  }
}

function renderOverlayCaption(clip) {
  const cap = $("#cap");
  if (!clip.words.length) { cap.innerHTML = ""; cap.tabIndex = -1; return; }
  const template = CAPTION_TEMPLATES[state.style];
  const cues = cueGroups(clip.words);
  const active = clip.words.findIndex(w => state.t >= w.s && state.t < w.e);
  let ci = cues.findIndex(([a, b]) => active >= a && active < b);
  if (ci < 0) ci = active < 0 ? cues.length - 1 : 0;
  const [a, b] = cues[ci];

  cap.dataset.style = state.style;
  cap.dataset.case = template.uppercase ? "upper" : "sentence";
  cap.style.setProperty("--cap-hl", template.box ? "#111" : state.hl);
  cap.style.color = template.color;
  cap.style.webkitTextStroke = `${template.outline ? Math.min(template.outline, 6) / 3 : 0}px ${template.outlineColor}`;
  cap.style.textShadow = template.shadow
    ? `0 ${Math.max(1, template.shadow / 2)}px ${template.shadow}px ${template.outlineColor}`
    : "none";
  cap.style.background = template.box ? "rgba(0,0,0,.82)" : "transparent";
  cap.style.padding = template.box ? "3px 6px" : "0";
  cap.style.borderRadius = template.box ? "4px" : "0";
  cap.style.fontFamily = state.font;
  cap.style.fontSize = `${15 + (state.fontSize - 68) / 64 * 9}px`;
  cap.style.left = `${state.captionX}%`;
  cap.style.top = `${state.captionY}%`;
  cap.tabIndex = 0;
  cap.setAttribute("aria-label", "Caption. Seret untuk mengubah posisinya.");
  cap.innerHTML = clip.words.slice(a, b).map((w, k) => {
    const on = state.karaoke && (a + k) === active;
    return `<span class="w ${on ? "on" : ""}">${escapeHtml(w.w)}</span>`;
  }).join(" ");

  if (template.box) {
    cap.querySelectorAll(".w.on").forEach(el => {
      el.style.background = state.hl;
      el.style.color = "#0B0B0B";
      el.style.padding = "0 4px";
      el.style.borderRadius = "3px";
    });
  }
}

function updateCaptionPositionFromPointer(event) {
  const layer = $(".cap-layer");
  const bounds = layer.getBoundingClientRect();
  if (!bounds.width || !bounds.height) return;
  state.captionX = Math.round(Math.max(10, Math.min(90,
    (event.clientX - bounds.left) / bounds.width * 100)));
  state.captionY = Math.round(Math.max(10, Math.min(90,
    (event.clientY - bounds.top) / bounds.height * 100)));
  const caption = $("#cap");
  caption.style.left = `${state.captionX}%`;
  caption.style.top = `${state.captionY}%`;
}

$("#cap").addEventListener("pointerdown", event => {
  event.preventDefault();
  event.currentTarget.setPointerCapture(event.pointerId);
  event.currentTarget.dataset.dragging = "true";
  updateCaptionPositionFromPointer(event);
});
$("#cap").addEventListener("pointermove", event => {
  if (event.currentTarget.dataset.dragging === "true") {
    updateCaptionPositionFromPointer(event);
  }
});
function finishCaptionDrag(event) {
  if (event.currentTarget.dataset.dragging !== "true") return;
  event.currentTarget.dataset.dragging = "false";
  savePreferences();
  renderStage();
}
$("#cap").addEventListener("pointerup", finishCaptionDrag);
$("#cap").addEventListener("pointercancel", finishCaptionDrag);
$("#cap").addEventListener("keydown", event => {
  const steps = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
  const step = steps[event.key];
  if (!step) return;
  event.preventDefault();
  const amount = event.shiftKey ? 5 : 1;
  state.captionX = Math.max(10, Math.min(90, state.captionX + step[0] * amount));
  state.captionY = Math.max(10, Math.min(90, state.captionY + step[1] * amount));
  savePreferences();
  renderStage();
});

function updateTimeUi(clip) {
  $("#tNow").textContent = tcode(state.t);
  const head = $("#playhead");
  if (head) {
    const view = timelineView();
    head.style.left = ((clip.start + state.t - view.start) / view.duration * 100).toFixed(3) + "%";
  }
}

function syncPlayIcon() {
  $("#playBtn").setAttribute("aria-pressed", String(state.playing));
  $("#playBtn").setAttribute("aria-label", state.playing ? "Jeda pratinjau" : "Putar pratinjau");
  $("#playIcon").innerHTML = state.playing
    ? '<path d="M7 5h4v14H7zM13 5h4v14h-4z"/>'
    : '<path d="M8 5v14l11-7z"/>';
}

let raf = null, last = 0;
function loop(ts) {
  if (!state.playing) return;
  const clip = current();
  if (!clip) { state.playing = false; syncPlayIcon(); return; }
  if (!last) last = ts;
  state.t += Math.min(0.1, (ts - last) / 1000);
  last = ts;
  if (state.t >= clip.dur) state.t = 0;
  renderTranscript(clip);
  renderOverlayCaption(clip);
  updateTimeUi(clip);
  raf = requestAnimationFrame(loop);
}

function togglePlay() {
  const clip = current();
  if (!clip) return;
  if (!clip.video && !state.sourcePreview && state.project?.extra?.source_url) {
    toast("Video belum diunduh — pakai Pratinjau di YouTube");
    return;
  }
  const player = $("#player");
  if ((clip.video || state.sourcePreview) && !player.hidden) {
    if (player.paused) {
      if (state.t >= clip.dur) {
        state.t = 0;
        player.currentTime = state.sourcePreview ? clip.start : 0;
      }
      player.play().catch(() => {});
    }
    else player.pause();
    return;
  }
  state.playing = !state.playing;
  last = 0;
  syncPlayIcon();
  if (state.playing) raf = requestAnimationFrame(loop);
  else if (raf) cancelAnimationFrame(raf);
}

/* ============================================================
   Skor
   ============================================================ */
function renderScore() {
  const clip = current();
  const body = $("#scoreBody");
  if (!body) return;

  if (!clip) {
    body.innerHTML = `<p class="score-note">Belum ada klip untuk dinilai.</p>`;
    return;
  }
  if (!clip.vps) {
    body.innerHTML = `
      <div class="score-hero"><span class="score-big">${clip.score == null ? "—" : clip.score}</span>
      <span class="score-cap">dari 100 · potensi, bukan probabilitas</span></div>
      <p class="score-note">Proyek ini dibuat sebelum skor rinci disimpan. Render ulang untuk melihat komponen H/R/C/A/L/P beserta alasannya.</p>
      ${hookAiMarkup(clip)}`;
    return;
  }

  const vps = clip.vps;
  const comps = vps.components || {};
  const reasons = vps.reasons || {};
  const gates = vps.gates_failed || [];
  const unmeasured = vps.unmeasured || [];

  const gate = gates.length
    ? `<div class="gate"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 8v5M12 16.5v.5"/><path d="M10.3 3.9 2.6 17a1.8 1.8 0 0 0 1.6 2.7h15.6A1.8 1.8 0 0 0 21.4 17L13.7 3.9a1.8 1.8 0 0 0-3.4 0Z"/></svg>
      <p><b>Skor ditahan di 40.</b> ${escapeHtml(gates.join(" · "))}</p></div>`
    : "";

  const order = ["H", "R", "C", "A", "L", "P"];
  const rows = order.filter(k => k in comps).map(k => {
    const value = Math.round(comps[k]);
    const reason = (reasons[k] || []).join(" · ");
    return `
      <div class="comp">
        <span class="comp-k">${k}</span>
        <span class="bar"><i class="${value < 50 ? "dim" : ""}" style="width:${value}%"></i></span>
        <span class="comp-v">${value}</span>
        <span class="comp-reason">${escapeHtml(reason)}</span>
      </div>`;
  }).join("");

  const missing = unmeasured.length
    ? `<p class="score-note">Belum diukur: ${unmeasured.join(", ")}. Komponen itu tidak ikut menilai.</p>`
    : "";

  body.innerHTML = `
    ${gate}
    <div class="score-hero">
      <span class="score-big">${Math.round(vps.score)}</span>
      <span class="score-cap">dari 100 · potensi, bukan probabilitas</span>
    </div>
    <p class="score-note">Skor mengurutkan kandidat, bukan meramal jumlah tayangan.</p>
    ${rows}${missing}${hookAiMarkup(clip)}`;
}

function hookAiMarkup(clip) {
  const analysis = state.project?.extra?.hook_ai?.[clip.id];
  if (!analysis) return `<p class="score-note">AI lokal belum dijalankan. Skor utama tetap memakai heuristik aplikasi.</p>`;
  const reasons = Array.isArray(analysis.reasons)
    ? analysis.reasons.map(reason => `<li>${escapeHtml(reason)}</li>`).join("")
    : "";
  return `<div class="detail">
    <div class="detail-label">AI lokal · ${escapeHtml(analysis.model || "Ollama")}</div>
    <div class="score-hero"><span class="score-big">${Math.round(Number(analysis.score) || 0)}</span>
    <span class="score-cap">dari 100 · penilaian model, bukan prediksi views</span></div>
    <ul class="score-note">${reasons}</ul>
  </div>`;
}

function renderTranscriptReview() {
  const container = $("#transcriptReviewOutput");
  if (!container) return;
  const projectWords = state.project?.words || [];
  const reviewButton = $("#reviewTranscriptBtn");
  if (reviewButton) {
    const available = Boolean(
      projectWords.length
      && (state.project?.media?.local_available || state.project?.extra?.source_url)
    );
    reviewButton.disabled = !available
      || (state.job?.kind === "transcript_review" && state.job.status === "running");
  }
  const review = state.project?.extra?.transcript_review;
  if (!review) {
    container.innerHTML = "";
    $("#transcriptReviewStatus").textContent = projectWords.length
      ? "Dengar ulang dengan ASR kedua; Ollama menandai bagian berbeda. Transkrip asli dan timestamp tidak diubah."
      : "Belum ada transkrip yang bisa diperiksa.";
    return;
  }
  const differences = Array.isArray(review.differences) ? review.differences : [];
  if (!differences.length) {
    container.innerHTML = `<p class="score-note">Tidak ada perbedaan kata pada pemeriksaan ${escapeHtml(review.asr_model || "ASR")}.</p>`;
    return;
  }
  const labels = {
    possible_missed_words: "Mungkin ada kata terlewat/berubah",
    minor_difference: "Perbedaan kecil",
    no_clear_issue: "Belum bisa dipastikan",
  };
  container.innerHTML = `<div class="detail">
    <div class="detail-label">${differences.length} bagian berbeda · ASR ${escapeHtml(review.asr_model || "")} + Ollama ${escapeHtml(review.model || "")}</div>
    ${differences.map(item => `<details class="score-note" style="margin-top:8px">
      <summary>${mmss(Number(item.start) || 0)} · ${escapeHtml(labels[item.assessment] || "Perlu ditinjau")}</summary>
      <p><b>Transkrip saat ini:</b> ${escapeHtml(item.primary || "(tidak dikenali)")}</p>
      <p><b>Dengar ulang:</b> ${escapeHtml(item.second_pass || "(tidak dikenali)")}</p>
      <p>${escapeHtml(item.note || "")}</p>
    </details>`).join("")}
    <p class="score-note">Ollama tidak mendengar audio. Ini hanya penanda perbedaan ASR; dengarkan bagian tersebut sebelum mengubah caption.</p>
  </div>`;
}

/* ============================================================
   Linimasa
   ============================================================ */
function niceStep(total) {
  const target = Math.max(1, total / 9);
  const steps = [2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800];
  return steps.find(s => s >= target) || 3600;
}

function timelineView() {
  const total = Math.max(1, state.project?.media?.duration || 1);
  const duration = total / state.timelineZoom;
  const clip = current();
  const center = clip ? (clip.start + clip.end) / 2 : total / 2;
  const start = Math.max(0, Math.min(total - duration, center - duration / 2));
  return { total, duration, start, end: start + duration };
}

function speakerLanes() {
  const lanes = new Map();
  let run = null;
  for (const w of state.words) {
    if (!w.speaker) { run = null; continue; }
    if (run && run.sp === w.speaker && w.start - run.e < 3) {
      run.e = Math.max(run.e, w.end);
      continue;
    }
    run = { sp: w.speaker, s: w.start, e: w.end };
    if (!lanes.has(w.speaker)) lanes.set(w.speaker, []);
    lanes.get(w.speaker).push(run);
  }
  return lanes;
}

function renderTimeline() {
  const view = timelineView();
  const { duration, start, end } = view;
  const ruler = $("#ruler");
  if (!ruler) return;

  const step = niceStep(duration);
  let ticks = "";
  for (let t = Math.ceil(start / step) * step; t <= end; t += step) {
    const left = ((t - start) / duration * 100).toFixed(3);
    const label = step >= 60 ? `${Math.round(t / 60)}m` : `${Math.round(t)}s`;
    ticks += `<div class="tick" style="left:${left}%"><span>${label}</span></div>`;
  }
  ruler.innerHTML = ticks;
  $("#tlTotal").textContent = `${state.timelineZoom}×`;

  const lanes = speakerLanes();
  const names = [...lanes.keys()].slice(0, 2);
  const [n1, n2] = [names[0] || "—", names[1] || "—"];
  $("#leg1").textContent = n1;
  $("#leg2").textContent = n2;
  $("#g1").textContent = n1;
  $("#g2").textContent = n2;

  const draw = (id, spans, cls) => {
    const el = $(id);
    if (!el) return;
    el.innerHTML = spans.filter(s => s.e >= start && s.s <= end).map(s => {
      const left = Math.max(0, (s.s - start) / duration * 100);
      const right = Math.min(100, (s.e - start) / duration * 100);
      const width = Math.max(0.12, right - left);
      return `<div class="blk ${cls}" style="left:${left.toFixed(3)}%;width:${width.toFixed(3)}%"></div>`;
    }).join("");
  };
  draw("#lane1", lanes.get(names[0]) || [], "s1");
  draw("#lane2", lanes.get(names[1]) || [], "s2");
  draw("#lane3", state.clips.map(c => ({ s: c.start, e: c.end })), "");

  const clip = current();
  const sel = $("#sel");
  if (sel && clip) {
    const left = Math.max(0, (clip.start - start) / duration * 100);
    const right = Math.min(100, (clip.end - start) / duration * 100);
    sel.style.left = left.toFixed(3) + "%";
    sel.style.width = Math.max(0, right - left).toFixed(3) + "%";
    $("#tlRange").textContent = `klip ${state.clips.indexOf(clip) + 1} · ${mmss(clip.start)}–${mmss(clip.end)}`;
  } else if (sel) {
    sel.style.width = "0%";
    $("#tlRange").textContent = "—";
  }
}

/* ============================================================
   Inspector: pembicara & layout
   ============================================================ */
function renderSpeakers() {
  const box = $("#spkRows");
  if (!box) return;
  const counts = new Map();
  for (const w of state.words) if (w.speaker) counts.set(w.speaker, (counts.get(w.speaker) || 0) + 1);
  const names = [...counts.keys()];
  $("#spkCount").textContent = names.length ? `${names.length} terdeteksi` : "belum ada label";
  box.innerHTML = names.slice(0, 6).map((name, i) => `
    <div class="spk-row">
      <span class="spk-dot" style="background:var(--spk-${i % 2 + 1})"></span>
      <div><div class="spk-name">${escapeHtml(name)}</div>
      <div class="spk-role">${counts.get(name)} kata</div></div>
      <span class="badge">${i < 2 ? "aktif" : "review"}</span>
    </div>`).join("") || `<div class="row-sub">Transkrip ini tidak punya label pembicara.</div>`;
}

function renderFraming() {
  const clip = current();
  $$("[data-layout]").forEach(btn => btn.setAttribute("aria-pressed", String(btn.dataset.layout === state.layout)));
  $("#layoutNote").textContent = clip && clip.layout !== state.layout
    ? `Klip ini memakai ${LAYOUT_LABEL[clip.layout] || clip.layout}; ${LAYOUT_LABEL[state.layout]} dipakai untuk proses berikutnya.`
    : `Layout ${LAYOUT_LABEL[state.layout]} dipakai untuk proses berikutnya.`;
  renderSpeakers();
}

/* ============================================================
   Render keseluruhan
   ============================================================ */
function renderAll() {
  renderClips();
  renderStage();
  renderScore();
  renderTranscriptReview();
  renderFraming();
  renderTimeline();
}

$("#zoomOutBtn").addEventListener("click", () => {
  state.timelineZoom = Math.max(1, state.timelineZoom / 2);
  renderTimeline();
});
$("#zoomInBtn").addEventListener("click", () => {
  state.timelineZoom = Math.min(32, state.timelineZoom * 2);
  renderTimeline();
});
$("#track").addEventListener("click", event => {
  const clip = current();
  if (!clip) return;
  const bounds = event.currentTarget.getBoundingClientRect();
  const fraction = Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width));
  const view = timelineView();
  state.t = Math.max(0, Math.min(clip.dur, view.start + fraction * view.duration - clip.start));
  const player = $("#player");
  if ((clip.video || state.sourcePreview) && !player.hidden) {
    player.currentTime = state.sourcePreview ? clip.start + state.t : state.t;
  }
  renderStage();
});

/* ============================================================
   Interaksi dasar (dari prototipe, disambungkan ke state nyata)
   ============================================================ */
$("#clipList").addEventListener("click", event => {
  const empty = event.target.closest("[data-empty-action]");
  if (empty) {
    if (!state.clips.length) openImport();
    else setFilter("all");
    return;
  }
  const btn = event.target.closest("[data-clip]");
  if (!btn) return;
  state.clipId = btn.dataset.clip;
  state.t = 0;
  resetPlayer();
  renderAll();
  if (window.innerWidth <= 1040) $("#app").dataset.cand = "closed";
});

function setFilter(filter) {
  state.filter = filter;
  $$(".filter").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.filter === filter)));
  renderClips();
}
$$(".filter").forEach(b => b.addEventListener("click", () => setFilter(b.dataset.filter)));

$("#playBtn").addEventListener("click", togglePlay);
$("#player").addEventListener("play", () => { state.playing = true; syncPlayIcon(); });
$("#player").addEventListener("pause", () => { state.playing = false; syncPlayIcon(); });
$("#player").addEventListener("timeupdate", () => {
  const clip = current();
  if (!clip) return;
  state.t = Math.max(0, ($("#player").currentTime || 0) - (state.sourcePreview ? clip.start : 0));
  if (state.sourcePreview && state.t >= clip.dur) {
    $("#player").pause();
    state.t = clip.dur;
  }
  renderTranscript(clip);
  renderOverlayCaption(clip);
  updateTimeUi(clip);
});
$("#player").addEventListener("loadedmetadata", () => {
  const clip = current();
  if (!clip) return;
  if (state.sourcePreview) $("#player").currentTime = clip.start + state.t;
  $("#tTot").textContent = tcode(clip.dur);
});

document.addEventListener("keydown", event => {
  if (event.target.matches("input, textarea, select")) return;
  if (event.code === "Space") { event.preventDefault(); togglePlay(); }
  if (event.key === "Escape") { closeModal(); closeImport(); }
});

const tabs = $$(".tab");
function selectTab(id) {
  state.tab = id;
  tabs.forEach(tab => {
    const on = tab.id === "tab-" + id;
    tab.setAttribute("aria-selected", String(on));
    tab.tabIndex = on ? 0 : -1;
    const panel = $("#panel-" + tab.id.replace("tab-", ""));
    if (panel) panel.hidden = !on;
  });
}
tabs.forEach(tab => {
  tab.addEventListener("click", () => selectTab(tab.id.replace("tab-", "")));
  tab.addEventListener("keydown", event => {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    event.preventDefault();
    const index = tabs.indexOf(tab);
    const next = tabs[(index + (event.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
    next.focus();
    selectTab(next.id.replace("tab-", ""));
  });
});

$$("[data-nav]").forEach(button => button.addEventListener("click", () => {
  const action = button.dataset.nav;
  $$(".rail-btn").forEach(item => item.removeAttribute("aria-current"));
  button.setAttribute("aria-current", "page");
  if (action === "studio") {
    $("#app").dataset.inspector = "closed";
    $("#app").dataset.cand = "closed";
  } else if (action === "clips") {
    setFilter("all");
    $("#app").dataset.cand = "open";
    $("#app").dataset.inspector = "closed";
  } else if (action === "export") {
    openModal();
  } else if (action === "caption" || action === "settings") {
    $("#app").dataset.inspector = "open";
    $("#app").dataset.cand = "closed";
    selectTab(action === "caption" ? "caption" : "framing");
  }
}));

$$(".preset").forEach(preset => preset.addEventListener("click", () => {
  state.style = preset.dataset.style;
  const template = CAPTION_TEMPLATES[state.style];
  state.hl = template.highlight;
  state.karaoke = template.karaoke;
  $$(".preset").forEach(x => x.setAttribute("aria-pressed", String(x === preset)));
  $$(".swatch").forEach(x => x.setAttribute("aria-pressed", String(x.dataset.hl === state.hl)));
  $$("[data-toggle='karaoke']").forEach(button => button.setAttribute("aria-checked", String(state.karaoke)));
  savePreferences();
  const clip = current();
  if (clip?.video) toast("Gaya caption tersimpan untuk render berikutnya — video ini sudah dibakar.");
  else renderStage();
}));

$$(".swatch").forEach(swatch => swatch.addEventListener("click", () => {
  state.hl = swatch.dataset.hl;
  $$(".swatch").forEach(x => x.setAttribute("aria-pressed", String(x === swatch)));
  savePreferences();
  renderStage();
}));

$("#sizeRange").addEventListener("input", event => {
  state.fontSize = Number(event.target.value);
  $("#sizeVal").textContent = String(state.fontSize);
  savePreferences();
  renderStage();
});

$$(".switch").forEach(sw => sw.addEventListener("click", () => {
  const on = sw.getAttribute("aria-checked") !== "true";
  sw.setAttribute("aria-checked", String(on));
  if (sw.dataset.toggle === "faces") state.faces = on;
  if (sw.dataset.toggle === "karaoke") state.karaoke = on;
  savePreferences();
  renderStage();
}));

$("#formatSel").addEventListener("change", event => {
  state.outputFormat = event.target.value;
  savePreferences();
});

$("#clipAsrModel").addEventListener("change", event => {
  state.clipAsrModel = event.target.value;
  savePreferences();
});

$("#fontSelect").addEventListener("change", event => {
  state.font = event.target.value;
  savePreferences();
  renderStage();
  if (current()?.video) toast("Font dipilih untuk proses berikutnya; video saat ini perlu dirender ulang.");
});

$("#resetCaptionPositionBtn").addEventListener("click", () => {
  state.captionX = 50;
  state.captionY = 66;
  savePreferences();
  renderStage();
});

$$("[data-layout]").forEach(button => button.addEventListener("click", () => {
  state.layout = button.dataset.layout;
  savePreferences();
  renderFraming();
  toast(`Layout ${LAYOUT_LABEL[state.layout]} dipilih untuk proses berikutnya.`);
}));

$("#guideBtn").addEventListener("click", () => {
  state.guides = !state.guides;
  $("#guideBtn").setAttribute("aria-pressed", String(state.guides));
  $("#guides").classList.toggle("show", state.guides);
});

/* ============================================================
   Status klip
   ============================================================ */
async function setStatus(status) {
  const clip = current();
  if (!clip) return;
  try {
    await api("/api/clips", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: clip.id, status }),
    });
    clip.status = status;
    renderClips();
    renderStage();
    toast(`Klip ditandai ${STATUS_LABEL[status].toLowerCase()}`);
  } catch (error) {
    toast(error.message);
  }
}
$("#approveBtn").addEventListener("click", () => setStatus("approved"));
$("#rejectBtn").addEventListener("click", () => setStatus("rejected"));

/* ============================================================
   Mesin lokal
   ============================================================ */
async function loadHealth() {
  try {
    const health = await api("/api/health");
    state.health = health;
    const set = (dot, label, ok, text) => {
      const d = $(dot), l = $(label);
      if (d) d.className = "dot" + (ok ? "" : " warn");
      if (l) { l.textContent = text || (ok ? "siap" : "belum"); l.className = "mdl-state" + (ok ? "" : " miss"); }
    };
    set("#hDotFf", "#hFf", Boolean(health.ffmpeg), health.ffmpeg ? "siap" : "tidak ada");
    set("#hDotAsr", "#hAsr", Boolean(health.faster_whisper));
    set("#hDotFace", "#hFace", Boolean(health.face_model), health.face_model ? "siap" : "unduh dulu");
    if (health.encoder) {
      $("#engineFoot").textContent = `Encoder: ${health.encoder}${health.encoder_license ? " · " + health.encoder_license : ""}`;
    }
  } catch { /* biarkan status awal */ }
}

const pop = $("#enginePop"), eng = $("#engineBtn");
eng.addEventListener("click", event => {
  event.stopPropagation();
  const open = !pop.classList.contains("open");
  pop.classList.toggle("open", open);
  eng.setAttribute("aria-expanded", String(open));
});
document.addEventListener("click", event => {
  if (!pop.contains(event.target) && !eng.contains(event.target)) {
    pop.classList.remove("open");
    eng.setAttribute("aria-expanded", "false");
  }
});

/* ============================================================
   Modal hasil ekspor
   ============================================================ */
const backdrop = $("#backdrop");
function openModal() {
  const project = state.project || {};
  const exportCfg = project.settings?.export || {};
  $("#expCount").textContent = `${state.clips.length} klip` +
    (state.clips.filter(c => c.status === "approved").length
      ? ` · ${state.clips.filter(c => c.status === "approved").length} disetujui` : "");
  $("#expRes").textContent = `${exportCfg.width || 1080} × ${exportCfg.height || 1920} · ${exportCfg.fps || 30} fps`;
  $("#expEncoder").textContent = state.health?.encoder
    ? `${state.health.encoder}${state.health.encoder_license ? " · " + state.health.encoder_license : ""}`
    : "—";
  $("#expDest").textContent = project.out_dir || "—";
  $("#expDest").title = project.out_dir || "";
  backdrop.classList.add("open");
}
function closeModal() { backdrop.classList.remove("open"); }
$("#exportBtn").addEventListener("click", openModal);
$("#closeModal").addEventListener("click", closeModal);
$("#cancelBtn").addEventListener("click", closeModal);
backdrop.addEventListener("click", event => { if (event.target === backdrop) closeModal(); });

$("#revealBtn").addEventListener("click", async () => {
  try {
    await api("/api/reveal", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    toast("Folder hasil dibuka");
  } catch (error) { toast(error.message); }
});

/* ============================================================
   Modal buat klip + job
   ============================================================ */
const importBackdrop = $("#importBackdrop");
let jobPoll = null;
let uploadRequest = null;

function openImport() {
  importBackdrop.classList.add("open");
  $("#importError").hidden = true;
  $("#jobBox").hidden = true;
  $("#startJobBtn").disabled = false;
  $("#videoPath").focus();
}
function closeImport() {
  if (uploadRequest) uploadRequest.abort();
  importBackdrop.classList.remove("open");
}
$("#newBtn").addEventListener("click", openImport);
$("#importClose").addEventListener("click", closeImport);

let jobStartPending = false;
let cancelWhenJobStarts = false;

async function requestJobCancellation(job, projectId) {
  try {
    const result = await api("/api/jobs/cancel", {
      projectId,
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: job.id }),
    });
    if (result.project_deleted) {
      const wasActive = projectId === state.projectId;
      clearTimeout(jobPoll);
      state.job = null;
      state.jobProjectId = null;
      $("#cancelReviewBtn").hidden = true;
      $("#reviewTranscriptBtn").disabled = false;
      $("#cancelActiveJobBtn").hidden = true;
      if (wasActive) {
        importBackdrop.classList.remove("open");
        state.projectId = result.replacement_id;
        saveActiveProject();
      }
      await loadWorkspaces();
      if (wasActive) {
        await loadProject();
        pollJob(state.projectId);
      }
      toast("Job dihentikan dan proyek dibuang");
      return;
    }
    if (projectId === state.projectId) {
      state.job = { ...job, stage: "membatalkan", message: "Permintaan pembatalan diterima" };
      $("#cancelActiveJobBtn").disabled = true;
      $("#cancelActiveJobBtn").textContent = "Membatalkan…";
      if (job.kind === "transcript_review") {
        $("#cancelReviewBtn").disabled = true;
        $("#transcriptReviewStatus").textContent = "Pembatalan diminta…";
      } else {
        setJobUi(state.job);
      }
    }
    toast("Pembatalan job diminta");
  } catch (error) {
    toast(error.message);
    if (projectId === state.projectId) {
      $("#cancelActiveJobBtn").disabled = false;
      if (job.kind === "transcript_review") {
        $("#cancelReviewBtn").disabled = false;
      } else {
        $("#importCancel").disabled = false;
      }
    }
  }
}

$("#importCancel").addEventListener("click", async () => {
  if (uploadRequest) {
    closeImport();
    return;
  }
  if (jobStartPending) {
    cancelWhenJobStarts = true;
    $("#importCancel").disabled = true;
    $("#importCancel").textContent = "Membatalkan…";
    $("#jobMsg").textContent = "Permintaan pembatalan menunggu job dimulai…";
    return;
  }
  if (state.job?.status === "running" && state.job.kind !== "transcript_review") {
    $("#importCancel").disabled = true;
    await requestJobCancellation(state.job, state.jobProjectId || state.projectId);
    return;
  }
  closeImport();
});
importBackdrop.addEventListener("click", event => { if (event.target === importBackdrop) closeImport(); });

$("#pickBtn").addEventListener("click", async () => {
  $("#sourceFile").click();
});

$("#sourceFile").addEventListener("change", event => {
  const file = event.target.files?.[0] || null;
  state.sourceFile = file;
  if (!file) return;
  $("#videoPath").value = file.name;
  $("#urlMeta").textContent = `${file.name} · ${(file.size / 1048576).toFixed(1)} MB · akan disalin ke folder proyek`;
  $("#importError").hidden = true;
});

/* Metadata URL: tampil sebelum unduh apa pun. */
const URL_HINT = $("#urlMeta").textContent;
let probeTimer = null;
$("#videoPath").addEventListener("input", () => {
  if (state.sourceFile && $("#videoPath").value !== state.sourceFile.name) {
    state.sourceFile = null;
    $("#sourceFile").value = "";
  }
  clearTimeout(probeTimer);
  const value = $("#videoPath").value.trim();
  if (!/^https?:\/\//i.test(value)) {
    $("#urlMeta").textContent = URL_HINT;
    return;
  }
  $("#urlMeta").textContent = "membaca metadata…";
  probeTimer = setTimeout(async () => {
    try {
      const meta = await api("/api/probe?url=" + encodeURIComponent(value));
      $("#urlMeta").textContent = `${meta.title} · ${mmss(meta.duration)} · ${meta.uploader}`;
    } catch {
      $("#urlMeta").textContent = URL_HINT;
    }
  }, 500);
});

$("#ytPreview").addEventListener("click", () => {
  const clip = current();
  const extra = state.project?.extra || {};
  const source = extra.source_url || "";
  if (!clip || !source) return;
  const id = extra.source_id || (source.match(/(?:v=|youtu\.be\/)([\w-]{6,})/) || [])[1];
  if (!id) { toast("ID video tidak diketahui"); return; }
  const start = Math.max(0, Math.floor(clip.start));
  const end = Math.ceil(clip.end);
  const frame = $("#ytFrame");
  frame.src = `https://www.youtube.com/embed/${id}?start=${start}&end=${end}&autoplay=1&rel=0`;
  frame.hidden = false;
  $(".cap-layer").hidden = false;
  $("#stageNote").hidden = true;
  state.t = 0;
  renderOverlayCaption(clip);
  toast("Preview YouTube tidak menampilkan framing lokal atau sinkronisasi caption.");
});

function setJobUi(job) {
  $("#jobBox").hidden = false;
  $("#processClipBtn").disabled = job.status === "running";
  $("#renderClipBtn").disabled = job.status === "running";
  $("#importCancel").textContent = job.status === "running" ? "Batalkan proses" : "Tutup";
  $("#importCancel").disabled = job.stage === "membatalkan";
  const percent = job.percent == null ? 0 : job.percent;
  $("#jobBar").style.width = percent + "%";
  $("#jobText").textContent = job.status === "done" ? "100%" : Math.round(percent) + "%";
  const stageSeconds = Number(job.stage_seconds);
  const elapsed = Number.isFinite(stageSeconds)
    ? ` · tahap ${Math.floor(stageSeconds / 60)}:${String(Math.floor(stageSeconds % 60)).padStart(2, "0")}`
    : "";
  $("#jobMsg").textContent = (job.error || job.message || "") + elapsed;

  const stage = job.stage || "";
  const first = ["metadata", "audio", "download", "import", "audio_extract"].includes(stage);
  const index = first ? 0 : ["model_load", "transcribe", "transcribe_clip"].includes(stage) ? 1 : 2;
  [["#js1", 0], ["#js2", 1], ["#js3", 2]].forEach(([sel, i]) => {
    const el = $(sel);
    if (!el) return;
    el.style.opacity = i <= index ? "1" : ".35";
    el.classList.toggle("run", i === index && job.status === "running");
    el.classList.toggle("done", i < index || job.status === "done" || job.status === "ready");
  });
}

async function pollJob(projectId = state.projectId) {
  if (projectId !== state.projectId) return;
  clearTimeout(jobPoll);
  try {
    const job = await api("/api/jobs/current", { projectId });
    if (projectId !== state.projectId) return;
    if (job.status === "idle") return;
    state.job = job;
    state.jobProjectId = projectId;
    $("#cancelActiveJobBtn").hidden = job.status !== "running"
      || job.kind === "transcript_review";
    $("#cancelActiveJobBtn").disabled = job.stage === "membatalkan";
    $("#cancelActiveJobBtn").textContent = job.stage === "membatalkan"
      ? "Membatalkan…" : "Batalkan job";
    if (job.kind === "transcript_review") {
      $("#reviewTranscriptBtn").disabled = job.status === "running";
      $("#cancelReviewBtn").hidden = job.status !== "running";
      $("#cancelReviewBtn").disabled = job.stage === "membatalkan";
      $("#transcriptReviewStatus").textContent = job.status === "running"
        ? `${job.message || "Memeriksa…"}${job.percent == null ? "" : ` · ${Math.round(job.percent)}%`}`
        : job.error || job.message || "Pemeriksaan selesai.";
    } else {
      setJobUi(job);
    }
    if (job.status === "running" && job.stage === "hooks" && state.lastHooks !== job.id) {
      state.lastHooks = job.id;
      toast("Hook siap — video menyusul");
      loadProject().catch(() => {});
    }
    if (job.status === "running") {
      jobPoll = setTimeout(() => pollJob(projectId), 700);
      return;
    }
    $("#startJobBtn").disabled = false;
    if (job.status === "cancelled") {
      if (job.kind === "transcript_review") {
        $("#reviewTranscriptBtn").disabled = false;
        $("#cancelReviewBtn").hidden = true;
        $("#transcriptReviewStatus").textContent = "Pemeriksaan dibatalkan.";
        return;
      }
      if (importBackdrop.classList.contains("open")) {
        $("#jobMsg").textContent = "Proses dibatalkan.";
        toast("Proses dibatalkan");
      }
      return;
    }
    if (job.status === "ready") {
      if (importBackdrop.classList.contains("open")) closeImport();
      await loadProject();
      toast(job.warning || job.message || "Kandidat siap — tinjau pilihan Ollama sebelum render.");
      return;
    }
    if (job.status === "done") {
      if (job.kind === "transcript_review") {
        await loadProject();
        if (projectId !== state.projectId) return;
        $("#reviewTranscriptBtn").disabled = false;
        $("#cancelReviewBtn").hidden = true;
        $("#transcriptReviewStatus").textContent = job.message || "Pemeriksaan selesai.";
        toast(job.message || "Pemeriksaan transkrip selesai");
        return;
      }
      if (importBackdrop.classList.contains("open")) closeImport();
      toast(job.warning || `${job.clips} klip siap`);
      await loadProject();
    } else {
      if (job.kind === "transcript_review") {
        $("#reviewTranscriptBtn").disabled = false;
        $("#cancelReviewBtn").hidden = true;
        $("#transcriptReviewStatus").textContent = `Gagal: ${job.error || "pemeriksaan gagal"}`;
        return;
      }
      $("#importError").hidden = false;
      $("#importError").textContent = job.error || "job gagal";
    }
  } catch {
    jobPoll = setTimeout(() => pollJob(projectId), 1500);
  }
}

async function processSelected(render) {
  const clip = current();
  if (!clip) return;
  const projectId = state.projectId;
  $("#processClipBtn").disabled = true;
  $("#renderClipBtn").disabled = true;
  try {
    const job = await api("/api/jobs/process", {
      projectId,
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        clip_id: clip.id,
        target: $("#targetSel").value,
        limit: 1,
        render,
        layout: state.layout,
        output_format: $("#formatSel").value || clip.outputFormat || "portrait",
        caption: captionSettings(),
        model: state.clipAsrModel,
        avoid_faces: state.faces,
      }),
    });
    if (projectId !== state.projectId) return;
    state.job = job;
    state.jobProjectId = projectId;
    pollJob(projectId);
  } catch (error) {
    if (projectId !== state.projectId) return;
    toast(error.message);
    $("#processClipBtn").disabled = false;
    $("#renderClipBtn").disabled = false;
  }
}

$("#processClipBtn").addEventListener("click", () => processSelected(false));
$("#renderClipBtn").addEventListener("click", () => processSelected(true));
$("#sourcePreviewBtn").addEventListener("click", () => {
  state.previewSource = !state.previewSource;
  $("#player").pause();
  state.videoClip = null;
  state.t = 0;
  renderStage();
});
$("#analyzeHookBtn").addEventListener("click", async () => {
  const clip = current();
  if (!clip) {
    $("#hookAiStatus").textContent = "Pilih kandidat klip terlebih dahulu.";
    return;
  }
  const button = $("#analyzeHookBtn");
  button.disabled = true;
  $("#hookAiStatus").textContent = "Menghubungi Ollama lokal…";
  try {
    const analysis = await api("/api/hooks/analyze", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ clip_id: clip.id, model: $("#hookModel").value.trim() }),
    });
    state.project.extra = state.project.extra || {};
    state.project.extra.hook_ai = state.project.extra.hook_ai || {};
    state.project.extra.hook_ai[clip.id] = analysis;
    $("#hookAiStatus").textContent = `Selesai · ${analysis.model}`;
    renderScore();
  } catch (error) {
    $("#hookAiStatus").textContent = `Gagal: ${error.message}`;
    toast(error.message);
  } finally {
    button.disabled = false;
  }
});

$("#reviewTranscriptBtn").addEventListener("click", async () => {
  const projectId = state.projectId;
  const button = $("#reviewTranscriptBtn");
  button.disabled = true;
  $("#transcriptReviewStatus").textContent = "Memulai dengar ulang audio dan pemeriksaan Ollama…";
  try {
    const job = await api("/api/transcript/review", {
      projectId,
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ollama_model: $("#hookModel").value.trim(),
        asr_model: $("#reviewAsrModel").value,
      }),
    });
    if (projectId !== state.projectId) return;
    state.job = job;
    state.jobProjectId = projectId;
    pollJob(projectId);
  } catch (error) {
    if (projectId !== state.projectId) return;
    button.disabled = false;
    $("#transcriptReviewStatus").textContent = `Gagal memulai pemeriksaan: ${error.message}`;
    toast(error.message);
  }
});

$("#cancelReviewBtn").addEventListener("click", async () => {
  if (state.job?.status !== "running" || state.job.kind !== "transcript_review") return;
  $("#cancelReviewBtn").disabled = true;
  await requestJobCancellation(state.job, state.jobProjectId || state.projectId);
});

$("#cancelActiveJobBtn").addEventListener("click", async () => {
  if (state.job?.status !== "running") return;
  $("#cancelActiveJobBtn").disabled = true;
  await requestJobCancellation(state.job, state.jobProjectId || state.projectId);
});

$("#ollamaHooks").addEventListener("change", event => {
  state.ollamaHooks = event.target.checked;
  savePreferences();
});
$("#ollamaModel").addEventListener("input", event => {
  state.ollamaModel = event.target.value.trim();
  $("#hookModel").value = event.target.value;
  savePreferences();
});
$("#hookModel").addEventListener("input", event => {
  state.ollamaModel = event.target.value.trim();
  $("#ollamaModel").value = event.target.value;
  savePreferences();
});

$("#startJobBtn").addEventListener("click", async () => {
  const projectId = state.projectId;
  let video = $("#videoPath").value.trim();
  if (!video) {
    $("#importError").hidden = false;
    $("#importError").textContent = "Isi path video dulu.";
    return;
  }
  if ($("#ollamaHooks").checked && !$("#ollamaModel").value.trim()) {
    $("#importError").hidden = false;
    $("#importError").textContent = "Isi nama model Ollama atau nonaktifkan penilaian Ollama.";
    return;
  }
  $("#importError").hidden = true;
  $("#startJobBtn").disabled = true;
  try {
    if (state.sourceFile) {
      $("#jobBox").hidden = false;
      $("#jobMsg").textContent = `Mengunggah ${state.sourceFile.name}…`;
      video = await uploadSource(state.sourceFile, projectId);
      if (projectId === state.projectId) {
        state.sourceFile = null;
        $("#sourceFile").value = "";
        $("#videoPath").value = video;
      }
    }
    jobStartPending = true;
    const job = await api("/api/jobs", {
      projectId,
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        video,
        target: $("#targetSel").value,
        limit: Number($("#limitNum").value) || 3,
        render: false,
        defer_video: true,
        layout: state.layout,
        output_format: $("#formatSel").value,
        ollama_model: $("#ollamaHooks").checked ? $("#ollamaModel").value.trim() : null,
        model: state.clipAsrModel,
        caption: captionSettings(),
        avoid_faces: state.faces,
      }),
    });
    jobStartPending = false;
    const cancelImmediately = cancelWhenJobStarts && job.status === "running";
    cancelWhenJobStarts = false;
    if (projectId !== state.projectId) {
      if (cancelImmediately) await requestJobCancellation(job, projectId);
      return;
    }
    state.job = job;
    state.jobProjectId = projectId;
    $("#importCancel").disabled = false;
    if (cancelImmediately) await requestJobCancellation(job, projectId);
    setJobUi(state.job);
    pollJob(projectId);
  } catch (error) {
    jobStartPending = false;
    cancelWhenJobStarts = false;
    $("#importCancel").disabled = false;
    $("#importCancel").textContent = "Tutup";
    $("#startJobBtn").disabled = false;
    if (!importBackdrop.classList.contains("open")) return;
    $("#importError").hidden = false;
    $("#importError").textContent = error.message;
  }
});

function uploadSource(file, projectId = state.projectId) {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    uploadRequest = request;
    request.open("POST", `/api/upload?filename=${encodeURIComponent(file.name)}`);
    request.setRequestHeader("Content-Type", "application/octet-stream");
    if (projectId) request.setRequestHeader("X-ClipperGod-Project", projectId);
    request.upload.addEventListener("progress", event => {
      if (!event.lengthComputable) return;
      const percent = event.loaded / event.total * 100;
      if (projectId !== state.projectId) return;
      $("#jobBar").style.width = `${percent}%`;
      $("#jobText").textContent = `${Math.round(percent)}%`;
      $("#jobMsg").textContent = `Mengunggah ${file.name}…`;
    });
    request.addEventListener("load", () => {
      uploadRequest = null;
      let data = {};
      try { data = JSON.parse(request.responseText); }
      catch { reject(new Error("Respons upload tidak valid")); return; }
      if (request.status < 200 || request.status >= 300) {
        reject(new Error(data.error || `Upload gagal (HTTP ${request.status})`));
        return;
      }
      resolve(data.path);
    });
    request.addEventListener("error", () => {
      uploadRequest = null;
      reject(new Error("Upload gagal karena koneksi lokal terputus"));
    });
    request.addEventListener("abort", () => {
      uploadRequest = null;
      reject(new Error("Upload dibatalkan"));
    });
    request.send(file);
  });
}

/* ============================================================
   Toast, panel mobile, boot
   ============================================================ */
let toastTimer = null;
function toast(message) {
  $("#toastText").textContent = message;
  $("#toast").classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $("#toast").classList.remove("show"), 4200);
}

$("#inspToggle").addEventListener("click", () => {
  const app = $("#app");
  app.dataset.inspector = app.dataset.inspector === "open" ? "closed" : "open";
  app.dataset.cand = "closed";
});
$("#candToggle").addEventListener("click", () => {
  const app = $("#app");
  app.dataset.cand = app.dataset.cand === "open" ? "closed" : "open";
  app.dataset.inspector = "closed";
});

$("#sizeRange").value = String(state.fontSize);
$("#sizeVal").textContent = String(state.fontSize);
$("#formatSel").value = state.outputFormat;
$("#clipAsrModel").value = state.clipAsrModel;
$("#ollamaHooks").checked = state.ollamaHooks;
$("#ollamaModel").value = state.ollamaModel;
$("#hookModel").value = state.ollamaModel;
$$(".preset").forEach(button => button.setAttribute("aria-pressed", String(button.dataset.style === state.style)));
$$(".swatch").forEach(button => button.setAttribute("aria-pressed", String(button.dataset.hl === state.hl)));
$$("[data-toggle='faces']").forEach(button => button.setAttribute("aria-checked", String(state.faces)));
$$("[data-toggle='karaoke']").forEach(button => button.setAttribute("aria-checked", String(state.karaoke)));

loadHealth();
loadCaptionFonts().catch(error => toast(error.message));
loadWorkspaces().then(() => loadProject()).then(() => {
  pollJob(state.projectId);
  if (!state.clips.length) setTimeout(openImport, 350);
}).catch(error => {
  $("#projName").textContent = "Proyek tidak bisa dibuka";
  $("#projMeta").textContent = error.message;
});
