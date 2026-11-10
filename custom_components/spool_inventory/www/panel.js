/* Spool Inventory panel: inventory manager for the "Filament" sidebar entry.
 * Plain web component, no build step and no external dependencies.
 * Talks to Home Assistant over the spool_inventory/* websocket commands.
 */

const WS = "spool_inventory";
const DEFAULT_LOW_G = 150; // used until the saved setting arrives
const NO_LOCATION = "No location";
const PROPS = new Set(["value", "checked", "disabled", "selected", "open", "readOnly"]);

/** Tiny DOM builder: h("div", {class: "x", onClick: fn}, child, ...). Text is never parsed as HTML. */
function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
    else if (k.startsWith("on")) el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (PROPS.has(k)) el[k] = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

const num = (v) => {
  const n = parseFloat(String(v).replace(",", "."));
  return Number.isFinite(n) ? n : null;
};
const fmtG = (g) => `${Math.round(g).toLocaleString()} g`;
const ago = (iso) => {
  if (!iso) return "";
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
  return days <= 0 ? "today" : days === 1 ? "yesterday" : days < 60 ? `${days} days ago` : `${Math.round(days / 30)} months ago`;
};
const fmtNum = (v) => v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const REFILL_G = 900; // Prusament sells spool-less refills of 900 g (spools are 1000 g)
const hasRefill = (vendor) => String(vendor || "").trim().toLowerCase() === "prusament";
const fmtKg = (g) => (g >= 1000 ? `${(g / 1000).toFixed(2)} kg` : fmtG(g));
const GLYPHS = { plus: "+", scale: "⚖", "minus-circle-outline": "−", pencil: "✎", "delete-outline": "✕", table: "☰", "view-grid": "▦", "printer-3d": "🖨", "cart-outline": "🛒", cart: "🛒", cog: "⚙", "content-copy": "⧉", "archive-outline": "▣", "archive-arrow-up-outline": "↩", "cart-plus": "🛒+", "download": "⇩", "upload": "⇧", "scale-balance": "⚖", history: "⟲", wrench: "🔧", plus: "+" };
// Home Assistant's own icon element when available, a plain symbol otherwise.
const icon = (name) => (customElements.get("ha-icon") ? h("ha-icon", { icon: `mdi:${name}` }) : h("span", { "aria-hidden": "true" }, GLYPHS[name] || "•"));

const STYLE = `
:host { display:block; min-height:100%; background:var(--primary-background-color); color:var(--primary-text-color);
  font-family:var(--paper-font-body1_-_font-family, Roboto, sans-serif); font-size:14px; }
* { box-sizing:border-box; }
.bar { position:sticky; top:0; z-index:5; display:flex; align-items:center; gap:8px; padding:0 16px; height:56px;
  background:var(--app-header-background-color, var(--primary-color)); color:var(--app-header-text-color, #fff); }
.bar h1 { font-size:20px; font-weight:400; margin:0; flex:1; }
.wrap { max-width:1200px; margin:0 auto; padding:16px; }
button { font:inherit; color:inherit; cursor:pointer; border:1px solid var(--divider-color); background:var(--card-background-color);
  border-radius:8px; padding:7px 12px; display:inline-flex; align-items:center; gap:6px; }
button:hover { border-color:var(--primary-color); }
button.primary { background:var(--primary-color); color:var(--text-primary-color, #fff); border-color:var(--primary-color); }
button.bare { border:none; background:none; padding:6px; border-radius:50%; }
button.bare:hover { background:var(--secondary-background-color); }
button.danger:hover { color:var(--error-color, #db4437); }
button:disabled { opacity:.5; cursor:default; }
.bar button.primary { background:rgba(255,255,255,.18); border-color:rgba(255,255,255,.5); color:inherit; }
ha-icon { --mdc-icon-size:20px; display:inline-flex; }
input, select, textarea { font:inherit; color:var(--primary-text-color); background:var(--card-background-color);
  border:1px solid var(--divider-color); border-radius:8px; padding:8px 10px; min-width:0; }
input:focus, select:focus, textarea:focus { outline:2px solid var(--primary-color); outline-offset:-1px; }
input[type=checkbox] { width:18px; height:18px; padding:0; flex:none; accent-color:var(--primary-color); }
.row2 > input[type=checkbox] { flex:none; }
input[type=color] { padding:2px; width:44px; height:38px; cursor:pointer; }
.stats { display:grid; grid-template-columns:repeat(auto-fit, minmax(240px, 1fr)); gap:12px; margin-bottom:16px; }
.stat { background:var(--card-background-color); border-radius:12px; padding:12px 16px; box-shadow:var(--ha-card-box-shadow, none);
  border:1px solid var(--divider-color); }
.stat b { display:block; font-size:24px; font-weight:500; }
.stat span { color:var(--secondary-text-color); }
.stat.warn b { color:var(--warning-color, #ffa600); }
.stat { position:relative; } .stat.click { cursor:pointer; user-select:none; } .stat.click:hover { border-color:var(--primary-color); }
.stat.on { outline:2px solid var(--primary-color); outline-offset:-1px; }
.stat .gear { position:absolute; top:4px; right:4px; }
button.bare.on { color:var(--primary-color); }
.chip.info { background:var(--primary-color); color:var(--text-primary-color, #fff); }
.filterbar { display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin-bottom:12px; }
.loc { margin-bottom:16px; } .loc h2 { font-size:16px; font-weight:500; margin:0 0 8px; display:flex; gap:10px; align-items:baseline; flex-wrap:wrap; }
.loc h2 small { color:var(--secondary-text-color); font-weight:400; font-size:13px; }
.loc select { padding:4px 8px; max-width:170px; }
.loc table { table-layout:fixed; } .loc td:nth-child(1) { width:50%; } .loc td:nth-child(2) { width:28%; }
@media (max-width:600px) { .loc table { table-layout:auto; } }
textarea { width:100%; min-height:90px; resize:vertical; }
.catlist { max-height:170px; overflow:auto; border:1px solid var(--divider-color); border-radius:8px; }
.catlist .row { display:flex; justify-content:space-between; align-items:center; padding:2px 8px; gap:8px; }
.toolbar { display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin-bottom:12px; }
.toolbar .grow { flex:1; }
.tabs { display:flex; flex-wrap:wrap; gap:4px; margin-right:8px; }
.tabs button { border-radius:20px; }
.tabs button.on { background:var(--primary-color); color:var(--text-primary-color, #fff); border-color:var(--primary-color); }
.seg { display:inline-flex; } .seg button { border-radius:0; } .seg button:first-child { border-radius:8px 0 0 8px; }
.seg button:last-child { border-radius:0 8px 8px 0; margin-left:-1px; }
.seg button.on { background:var(--primary-color); color:var(--text-primary-color, #fff); border-color:var(--primary-color); }
.panel { background:var(--card-background-color); border-radius:12px; border:1px solid var(--divider-color); overflow:hidden; }
.scroll { overflow-x:auto; }
table { width:100%; border-collapse:collapse; }
th, td { text-align:left; padding:8px 12px; border-bottom:1px solid var(--divider-color); vertical-align:middle; }
th { color:var(--secondary-text-color); font-weight:500; white-space:nowrap; user-select:none; }
th.sort { cursor:pointer; } th.sort:hover { color:var(--primary-text-color); }
tr:last-child td { border-bottom:none; }
td.num, th.num { text-align:right; white-space:nowrap; }
.swatch { display:inline-block; width:22px; height:22px; border-radius:50%; border:1px solid rgba(128,128,128,.6); flex:none;
  box-shadow:inset 0 0 0 2px rgba(255,255,255,.18); }
.name { display:flex; align-items:center; gap:10px; min-width:200px; }
.name small { display:block; color:var(--secondary-text-color); }
.badge { position:relative; width:30px; height:30px; flex:none; border-radius:8px; background:var(--secondary-background-color);
  display:flex; align-items:center; justify-content:center; font-size:11px; font-weight:600; color:var(--secondary-text-color); overflow:hidden; }
.badge img { position:absolute; inset:0; width:100%; height:100%; object-fit:contain; background:#fff; padding:2px; }
.bar-bg { height:6px; border-radius:3px; background:var(--divider-color); min-width:80px; margin-top:4px; overflow:hidden; }
.bar-fg { height:100%; background:var(--primary-color); } .low .bar-fg { background:var(--warning-color, #ffa600); }
.empty .bar-fg { background:var(--error-color, #db4437); }
.grams { display:inline-flex; align-items:center; gap:4px; }
.grams input { width:78px; text-align:right; padding:5px 8px; }
.chip { display:inline-block; border-radius:10px; padding:1px 8px; margin:1px 4px 1px 0; background:var(--secondary-background-color);
  color:var(--secondary-text-color); font-size:12px; white-space:nowrap; }
.chip.warn { background:var(--warning-color, #ffa600); color:#000; } .chip.err { background:var(--error-color, #db4437); color:#fff; }
.menu { position:fixed; z-index:20; min-width:240px; background:var(--card-background-color); border:1px solid var(--divider-color); border-radius:10px; box-shadow:0 6px 24px rgba(0,0,0,.35); padding:4px; display:grid; }
.mi { border:none; background:none; justify-content:flex-start; border-radius:6px; padding:10px 12px; text-align:left; } .mi:hover, .mi:focus { background:var(--secondary-background-color); outline:none; } .mi.danger { color:var(--error-color, #db4437); }
.actions { display:flex; justify-content:flex-end; white-space:nowrap; }
tfoot td { font-weight:600; background:var(--secondary-background-color); }
.cards { display:grid; grid-template-columns:repeat(auto-fill, minmax(260px, 1fr)); gap:12px; }
.card { background:var(--card-background-color); border:1px solid var(--divider-color); border-radius:12px; padding:14px;
  display:flex; flex-direction:column; gap:10px; }
.card .top { display:flex; gap:12px; align-items:center; }
.card .ring { position:relative; width:76px; height:76px; flex:none; }
.card .ring svg { width:100%; height:100%; transform:rotate(-90deg); }
.card .ring .mid { position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center; line-height:1.15; }
.card .ring .mid b { font-size:16px; } .card .ring .mid span { font-size:11px; color:var(--secondary-text-color); }
.card h3 { margin:0; font-size:15px; font-weight:500; } .card .meta { color:var(--secondary-text-color); font-size:12px; }
.card .row { display:flex; justify-content:space-between; align-items:center; gap:6px; }
.none { padding:32px; text-align:center; color:var(--secondary-text-color); }
.overlay { position:fixed; inset:0; z-index:20; background:rgba(0,0,0,.5); display:flex; align-items:center; justify-content:center; padding:12px; }
.dlg { background:var(--card-background-color); color:var(--primary-text-color); border-radius:16px; width:min(560px, 100%);
  max-height:94vh; display:flex; flex-direction:column; box-shadow:0 8px 32px rgba(0,0,0,.4); }
.dlg header { padding:16px 20px 8px; font-size:18px; font-weight:500; }
.dlg .body { padding:8px 20px; overflow:auto; display:grid; gap:12px; }
.dlg footer { padding:12px 20px 16px; display:flex; gap:8px; justify-content:flex-end; flex-wrap:wrap; }
.field { display:grid; gap:4px; } .field > label, .field > .lab { font-size:12px; color:var(--secondary-text-color); }
.two { display:grid; grid-template-columns:1fr 1fr; gap:12px; } .row2 { display:flex; gap:8px; align-items:center; }
.row2 > :first-child { flex:1; }
.swatches { display:flex; flex-wrap:wrap; gap:6px; } .swatches button { padding:0; width:26px; height:26px; border-radius:50%; }
.hint { font-size:12px; color:var(--secondary-text-color); }
details { border:1px solid var(--divider-color); border-radius:8px; padding:8px 12px; } summary { cursor:pointer; color:var(--secondary-text-color); }
details[open] summary { margin-bottom:10px; } details .grid { display:grid; gap:12px; }
#toasts { position:fixed; left:0; right:0; bottom:24px; z-index:30; display:flex; flex-direction:column; align-items:center; gap:8px; pointer-events:none; }
.toast { background:#323232; color:#fff; padding:10px 18px; border-radius:8px; max-width:90vw; box-shadow:0 4px 16px rgba(0,0,0,.4); }
.wd { display:block; opacity:.75; } .wd.never { opacity:.5; font-style:italic; }
.hist { display:grid; gap:0; max-height:60vh; overflow:auto; } .hrow { display:flex; justify-content:space-between; align-items:center; gap:12px; padding:8px 12px; border-bottom:1px solid var(--divider-color); }
.hrow small { display:block; }
.toastbtn { margin-left:12px; background:none; color:#8ab4f8; border:1px solid #8ab4f8; padding:3px 10px; }
.toast.err { background:var(--error-color, #b00020); }
.foot { margin-top:16px; text-align:center; color:var(--secondary-text-color); font-size:12px; }
@media (max-width:600px) { .stats { grid-template-columns:repeat(2, 1fr); } .wrap { padding:10px; } .two { grid-template-columns:1fr; } .stat b { font-size:20px; } }
`;

class SpoolInventoryPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.s = {
      spools: [], summary: null, catalog: null, loaded: false,
      tab: "spools", view: null, q: "", fVendor: "", fMaterial: "", fLocation: "", fStatus: "", hideEmpty: false,
      settings: null, userCatalog: [], baseCatalog: null, all: [], archived: [], trash: [], equipment: { printers: [], tasks: [], items: [] },
      sortKey: "name", sortDir: 1,
    };
    this._started = false;
    this._badLogos = new Set();
  }

  /* ---------- Home Assistant plumbing ---------- */
  set hass(hass) { this._hass = hass; if (this._menu) this._menu.hass = hass; this._start(); }
  set panel(panel) { this._panel = panel; this._start(); }
  set narrow(narrow) {
    this._narrow = narrow;
    if (this._menu) this._menu.narrow = narrow;
    if (this._started) { this._toolbar(); this._main(); }
  }
  set route(_) {}
  disconnectedCallback() {
    if (this._unsub) this._unsub.then((u) => u && u()).catch(() => {});
    this._unsub = null; this._started = false; this._closeMenu?.();
  }

  get admin() { return !this._hass?.user || this._hass.user.is_admin !== false; }
  get staticUrl() { return this._panel?.config?.static_url || "/spool_inventory_static"; }
  get view() { return this.s.view || (this._narrow ? "cards" : "table"); }

  _start() {
    if (this._started || !this._hass || !this._panel) return;
    this._started = true;
    const root = this.shadowRoot;
    root.replaceChildren(
      h("style", {}, STYLE),
      h("div", { id: "head" }),
      h("div", { class: "wrap" },
        h("div", { id: "stats", class: "stats" }),
        h("div", { id: "toolbar", class: "toolbar" }),
        h("div", { id: "filterbar" }),
        h("div", { id: "main" }),
        h("div", { class: "foot" }, "Color data: Open Filament Database (MIT license)")),
      h("div", { id: "dialogs" }),
      h("div", { id: "toasts" }),
    );
    this._head(); this._stats(); this._toolbar(); this._main();
    this._loadCatalog();
    this._unsub = this._hass.connection.subscribeMessage((msg) => {
      this.s.all = msg.spools; this.s.spools = msg.spools.filter((p) => !p.archived); this.s.archived = msg.spools.filter((p) => p.archived);
      this.s.trash = msg.trash || []; this.s.equipment = msg.equipment || { printers: [], tasks: [], items: [] }; this.s.summary = msg.summary; this.s.loaded = true;
      this.s.settings = msg.settings || null;
      if (JSON.stringify(msg.user_catalog || []) !== JSON.stringify(this.s.userCatalog)) { this.s.userCatalog = msg.user_catalog || []; this._mergeCatalog(); }
      this._stats(); this._main(); this._syncToolbar();
    }, { type: `${WS}/subscribe` });
    this._unsub.catch((err) => this._toast(this._err(err), true));
  }

  async _loadCatalog() {
    try {
      const v = this._panel?.config?.version || "";
      const res = await fetch(`${this.staticUrl}/catalog.json?v=${encodeURIComponent(v)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      this.s.baseCatalog = await res.json();
      this._mergeCatalog();
      this._toolbar();
    } catch (err) {
      this._toast(`Filament catalog not available (${err.message}). Custom entries still work.`, true);
    }
  }

  /** The shipped catalog plus the user's own saved entries (marked user:true). */
  _mergeCatalog() {
    const base = this.s.baseCatalog; if (!base) return;
    const cat = { ...base, vendors: [...base.vendors], catalog: {} };
    for (const [v, mats] of Object.entries(base.catalog)) {
      cat.catalog[v] = {};
      for (const [m, rows] of Object.entries(mats)) cat.catalog[v][m] = [...rows];
    }
    for (const e of this.s.userCatalog) {
      let vendor = cat.vendors.find((x) => x.name.toLowerCase() === e.vendor.toLowerCase());
      if (!vendor) { vendor = { name: e.vendor, code: e.vendor.replace(/[^A-Za-z0-9]/g, "").slice(0, 2).toUpperCase() || "?", logo: null, website: null }; cat.vendors.push(vendor); }
      const mats = (cat.catalog[vendor.name] ||= {});
      const mat = Object.keys(mats).find((m) => m.toLowerCase() === e.material.toLowerCase()) || e.material;
      const rows = (mats[mat] ||= []);
      const row = { name: e.name, hex: e.hex, line: e.line || "", weights: e.weights?.length ? e.weights : [1000], tare: e.tare, user: true };
      const at = rows.findIndex((r) => r.line.toLowerCase() === row.line.toLowerCase() && r.name.toLowerCase() === row.name.toLowerCase());
      if (at >= 0) rows[at] = row; else rows.push(row);
    }
    this.s.catalog = cat;
  }

  /** Value of the filament left: each spool's price times the share still on it. Spools without a price are left out. */
  stockValue(list = this.s.spools) {
    let value = 0, missing = 0;
    for (const p of list) {
      if (typeof p.price === "number" && p.initial_weight > 0) value += p.price * Math.min(1, p.remaining_weight / p.initial_weight); else missing++;
    }
    return { value, missing, any: missing < list.length };
  }

  /** "weighed 3 days ago" or "not weighed yet" for a spool. */
  weighedText(p) { return p.weighed ? `weighed ${ago(p.weighed)}` : "not weighed yet"; }

  get cur() { return this.s.settings?.currency || "RON"; }
  money(v) { return `${fmtNum(v)} ${this.cur}`; }

  get low() { return this.s.settings?.low_threshold ?? DEFAULT_LOW_G; }

  /** Locations offered in dropdowns: the saved ones first, then any that spools use. */
  locations() {
    const out = [...(this.s.settings?.locations || [])];
    for (const p of this.s.spools) if (p.location && !out.some((l) => l.toLowerCase() === p.location.toLowerCase())) out.push(p.location);
    return out;
  }

  _err(err) { return err?.message || err?.error?.message || String(err); }

  async _call(msg) {
    try { return await this._hass.callWS({ ...msg, type: `${WS}/${msg.type}` }); }
    catch (err) { this._toast(this._err(err), true); throw err; }
  }

  _toast(text, isErr = false, action = null) {
    const t = h("div", { class: `toast${isErr ? " err" : ""}`, role: "status" }, text,
      action ? h("button", { class: "toastbtn", "data-toast-action": "", onClick: () => { t.remove(); action.run(); } }, action.label) : null);
    t.style.pointerEvents = "auto";
    this.shadowRoot.getElementById("toasts").append(t);
    setTimeout(() => t.remove(), action ? 10000 : isErr ? 6000 : 2500);
  }

  /* ---------- derived data ---------- */
  vendorInfo(name) {
    const v = (this.s.catalog?.vendors || []).find((x) => x.name.toLowerCase() === String(name).toLowerCase());
    return v || { name, code: String(name).replace(/[^A-Za-z0-9]/g, "").slice(0, 2).toUpperCase() || "?", logo: null };
  }

  filtered() {
    const { q, fVendor, fMaterial, hideEmpty, sortKey, sortDir } = this.s;
    const needle = q.trim().toLowerCase();
    const source = this.s.fStatus === "reorder" ? this.s.all.filter((p) => p.reorder) : this.s.spools;
    const out = source.filter((p) => {
      if (fVendor && p.vendor !== fVendor) return false;
      if (fMaterial && p.material !== fMaterial) return false;
      if (this.s.fLocation && (p.location || NO_LOCATION) !== this.s.fLocation) return false;
      if (this.s.fStatus === "low" && !(p.remaining_weight > 0 && p.remaining_weight < this.low)) return false;
      if (this.s.fStatus === "empty" && p.remaining_weight > 0) return false;
      if (this.s.fStatus === "loaded" && !p.loaded) return false;
      if (this.s.fStatus === "reorder" && !p.reorder) return false;
      if (hideEmpty && p.remaining_weight <= 0 && this.s.fStatus !== "empty") return false;
      if (!needle) return true;
      return [p.name, p.vendor, p.material, p.color_name, p.location, p.notes, p.product].join(" ").toLowerCase().includes(needle);
    });
    const key = {
      name: (p) => p.name.toLowerCase(), material: (p) => `${p.material} ${p.color_name}`.toLowerCase(),
      remaining: (p) => p.remaining_weight, pct: (p) => p.remaining_percent, location: (p) => (p.location || "~").toLowerCase(),
    }[sortKey];
    return out.sort((a, b) => (key(a) > key(b) ? 1 : key(a) < key(b) ? -1 : 0) * sortDir);
  }

  groups() {
    const map = new Map();
    for (const p of this.s.spools) {
      const k = `${p.material}|${p.color_name}`.toLowerCase();
      if (!map.has(k)) map.set(k, { material: p.material, color: p.color_name || "(no color name)", hex: p.color_hex, total: 0, spools: [] });
      const g = map.get(k);
      g.total += p.remaining_weight; g.spools.push(p);
    }
    return [...map.values()].sort((a, b) => a.material.localeCompare(b.material) || a.color.localeCompare(b.color));
  }

  /* ---------- static chrome ---------- */
  _head() {
    const head = this.shadowRoot.getElementById("head");
    this._menu = document.createElement("ha-menu-button");
    this._menu.hass = this._hass; this._menu.narrow = this._narrow;
    head.replaceChildren(h("div", { class: "bar" }, this._menu, h("h1", {}, "Filament inventory"),
      this.admin && h("button", { class: "primary", title: "Alerts, locations and my catalog", onClick: () => this.settingsDialog() }, icon("cog"), "Settings"),
      this.admin && h("button", { class: "primary", onClick: () => this.spoolDialog(null) }, icon("plus"), "Add spool")));
  }

  _stats() {
    const spools = this.s.spools;
    const total = spools.reduce((a, p) => a + p.remaining_weight, 0);
    const low = spools.filter((p) => p.remaining_weight > 0 && p.remaining_weight < this.low).length;
    const empty = spools.filter((p) => p.remaining_weight <= 0).length;
    const reorder = this.s.all.filter((p) => p.reorder).length;
    const loaded = spools.filter((p) => p.loaded).length;
    const val = this.stockValue();
    // Cards with a filter key are clickable: they show only those spools (click again to clear).
    const stat = (value, label, cls = "", key = null, extra = null) => h("div", {
      class: `stat ${cls}${key ? " click" : ""}${key && this.s.fStatus === key ? " on" : ""}`, "data-stat": key || "all",
      role: key ? "button" : null, tabindex: key ? "0" : null, "aria-pressed": key ? String(this.s.fStatus === key) : null,
      onClick: key ? () => this._setStatus(key) : null,
      onKeydown: key ? (e) => { if (e.target === e.currentTarget && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); this._setStatus(key); } } : null,
    }, h("b", {}, value), h("span", {}, label), extra);
    const gear = this.admin ? h("button", { class: "bare gear", title: "Alert settings", "aria-label": "Alert settings",
      onClick: (e) => { e.stopPropagation(); this.settingsDialog(); } }, icon("cog")) : null;
    this.shadowRoot.getElementById("stats").replaceChildren(
      stat(spools.length, "spools"), stat(fmtKg(total), "filament left in total"),
      stat(low, `low (under ${this.low} g)`, low ? "warn" : "", "low", gear), stat(empty, "empty", empty ? "warn" : "", "empty"),
      stat(reorder, "to reorder", reorder ? "warn" : "", "reorder"), stat(loaded, "in the printer", "", "loaded"),
      ...(this.s.equipment.tasks.length ? [(() => { const n = this.s.equipment.tasks.filter((t) => t.state === "overdue").length;
        return h("div", { class: `stat click ${n ? "warn" : ""}`, "data-stat": "maintenance", role: "button", tabindex: "0", title: "Open the Printer tab",
          onClick: () => { this.s.tab = "printer"; this._toolbar(); this._main(); },
          onKeydown: (e) => { if (e.target === e.currentTarget && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); this.s.tab = "printer"; this._toolbar(); this._main(); } } },
        h("b", {}, n), h("span", {}, "maintenance overdue")); })()] : []),
      ...(val.any ? [h("div", { class: "stat", "data-stat": "value", title: val.missing ? `${val.missing} without a price are not counted` : "From the prices you entered" },
        h("b", {}, this.money(val.value)), h("span", {}, "value of filament left"))] : []));
  }

  _setStatus(key) {
    this.s.fStatus = this.s.fStatus === key ? "" : key;
    this.s.tab = "spools"; this._stats(); this._toolbar(); this._main();
  }

  _toolbar() {
    if (!this._started) return;
    const s = this.s;
    const vendors = [...new Set(s.spools.map((p) => p.vendor))].sort();
    const materials = [...new Set(s.spools.map((p) => p.material))].sort();
    const locs = this._locOptions();
    this._tbSig = `${vendors}|${materials}|${locs}|${s.archived.length}|${s.spools.length > 0}|${s.spools.some((p) => p.loaded)}|${this._eqBadge()}`;
    const tab = (id, label) => h("button", { class: s.tab === id ? "on" : "", onClick: () => { s.tab = id; this._toolbar(); this._main(); } }, label);
    const sel = (key, label, opts) => h("select", { "aria-label": label, onChange: (e) => { s[key] = e.target.value; this._main(); } },
      h("option", { value: "" }, label), opts.map((o) => h("option", { value: o, selected: s[key] === o }, o)));
    const nodes = [h("div", { class: "tabs" }, tab("spools", "Spools"), tab("colors", "By color"), tab("locations", "By location"), tab("archive", this.s.archived.length ? `Archive (${this.s.archived.length})` : "Archive"), tab("printer", this._eqBadge()), tab("history", "History"))];
    if (s.tab === "spools") {
      nodes.push(
        h("input", { type: "search", placeholder: "Search…", value: s.q, "aria-label": "Search",
          onInput: (e) => { s.q = e.target.value; this._main(); } }),
        sel("fVendor", "All vendors", vendors), sel("fMaterial", "All materials", materials), sel("fLocation", "All locations", locs),
        h("label", { class: "hint" }, h("input", { type: "checkbox", checked: s.hideEmpty,
          onChange: (e) => { s.hideEmpty = e.target.checked; this._main(); } }), " hide empty"),
        h("span", { class: "grow" }),
        this.admin && s.spools.some((p) => p.loaded) ? h("button", { "data-use-loaded": "", title: "Subtract filament from the spool that is in the printer", onClick: () => this.useLoadedDialog() }, icon("minus-circle-outline"), "Used in printer") : null,
        this.admin && s.spools.length ? h("button", { "data-weigh-session": "", title: "Weigh several spools one after another", onClick: () => this.weighSession() }, icon("scale"), "Weigh session") : null,
        h("div", { class: "seg" },
          h("button", { class: this.view === "table" ? "on" : "", title: "Table", "aria-label": "Table view", onClick: () => { s.view = "table"; this._toolbar(); this._main(); } }, icon("table")),
          h("button", { class: this.view === "cards" ? "on" : "", title: "Cards", "aria-label": "Card view", onClick: () => { s.view = "cards"; this._toolbar(); this._main(); } }, icon("view-grid"))));
    }
    this.shadowRoot.getElementById("toolbar").replaceChildren(...nodes.filter(Boolean));
    this._filterBar();
  }

  _locOptions() { return [...this.locations(), ...(this.s.spools.some((p) => !p.location) ? [NO_LOCATION] : [])]; }

  /** Shows which card filter is active, with a button to clear it (and the shopping list for reorders). */
  _filterBar() {
    const host = this.shadowRoot.getElementById("filterbar"); if (!host) return;
    const { fStatus, tab } = this.s;
    const label = { low: "low spools", empty: "empty spools", loaded: "spools loaded in the printer", reorder: "spools to reorder" }[fStatus];
    if (!fStatus || tab !== "spools") return host.replaceChildren();
    host.replaceChildren(h("div", { class: "filterbar" }, h("span", { class: "chip info" }, `Showing ${label}`),
      h("button", { "data-clear-filter": "", onClick: () => this._setStatus(fStatus) }, "Show all"),
      fStatus === "reorder" ? h("button", { "data-copy-list": "", onClick: () => this.shoppingList() }, icon("content-copy"), "Copy shopping list") : null));
  }

  /** Vendor/material filter lists change only when spools are added/removed; do not touch a focused search box. */
  _syncToolbar() {
    const vendors = [...new Set(this.s.spools.map((p) => p.vendor))].sort();
    const materials = [...new Set(this.s.spools.map((p) => p.material))].sort();
    if (this.s.fVendor && !vendors.includes(this.s.fVendor)) this.s.fVendor = "";
    if (this.s.fMaterial && !materials.includes(this.s.fMaterial)) this.s.fMaterial = "";
    if (this.s.fLocation && !this._locOptions().includes(this.s.fLocation)) this.s.fLocation = "";
    const sig = `${vendors}|${materials}|${this._locOptions()}|${this.s.archived.length}|${this.s.spools.length > 0}|${this.s.spools.some((p) => p.loaded)}|${this._eqBadge()}`;
    if (sig !== this._tbSig && !this.shadowRoot.activeElement?.matches?.("input[type=search]")) this._toolbar();
  }

  /* ---------- main content ---------- */
  _main() {
    if (!this._started) return;
    const main = this.shadowRoot.getElementById("main");
    // keep the cursor in an inline weight box while live updates arrive
    const ae = this.shadowRoot.activeElement;
    if (ae && ae.closest?.("#main") && ae.tagName === "INPUT") { this._pending = true; ae.addEventListener("blur", () => { if (this._pending) { this._pending = false; this._main(); } }, { once: true }); return; }
    if (!this.s.loaded) return main.replaceChildren(h("div", { class: "none" }, "Loading…"));
    main.replaceChildren(this.s.tab === "colors" ? this._colorsTable() : this.s.tab === "locations" ? this._locationsView() : this.s.tab === "archive" ? this._archiveView() : this.s.tab === "printer" ? this._printerView() : this.s.tab === "history" ? this._historyView()
      : this.view === "cards" ? this._cards() : this._table());
  }

  _badge(vendor) {
    const info = this.vendorInfo(vendor);
    const code = h("span", {}, info.code);
    const b = h("div", { class: "badge", title: vendor }, code);
    if (info.logo && !this._badLogos.has(info.logo)) {
      // Optional picture: shown only if the file exists, otherwise the letters stay.
      const img = h("img", { alt: "", src: `${this.staticUrl}/${info.logo}`, style: { visibility: "hidden" } });
      img.addEventListener("load", () => { img.style.visibility = "visible"; code.hidden = true; });
      img.addEventListener("error", () => { this._badLogos.add(info.logo); img.remove(); }); // ask only once
      b.append(img);
    }
    return b;
  }

  _state(p) { return p.remaining_weight <= 0 ? "empty" : p.remaining_weight < this.low ? "low" : ""; }

  /** Small status chips: empty/low, in printer, reorder. */
  _chips(p, withStock = true) {
    return [
      withStock && p.remaining_weight <= 0 ? h("span", { class: "chip err" }, "empty") : null,
      withStock && p.remaining_weight > 0 && p.remaining_weight < this.low ? h("span", { class: "chip warn" }, "low") : null,
      p.loaded ? h("span", { class: "chip info", title: "Loaded in the printer" }, "in printer") : null,
      p.reorder ? h("span", { class: "chip warn", title: "On the reorder list" }, "reorder") : null,
      p.refill ? h("span", { class: "chip", title: "Spool-less refill on a reusable spool" }, "refill") : null,
    ];
  }


  async undelete(id) { try { await this._call({ type: "restore", spool_id: id }); this._toast("Spool restored"); } catch {} }

  async archive(p, on) {
    try {
      await this._call({ type: "archive", spool_id: p.id, archived: on });
      this._toast(on ? `${p.name} moved to the archive` : `${p.name} is back in the inventory`, false, on ? { label: "Undo", run: () => this.archive(p, false) } : null);
    } catch {}
  }

  rebuyDialog(p) {
    this._modal("Bought another?", h("p", {}, `Add a new full spool of “${p.name}”${p.location ? ` in ${p.location}` : ""} and take this one off the reorder list? The old spool stays as it is.`),
      [{ label: "Cancel", run: (c) => c() },
        { label: "Add new spool", primary: true, run: async (c) => { try { await this._call({ type: "rebuy", spool_id: p.id }); c(); this._toast("New spool added"); } catch {} } }]);
  }


  /** One line per event. Rows with a changed amount get a button to put the old amount back. */
  _historyRows(rows, { showName }) {
    const LABEL = { added: "Added", edited: "Edited", weighed: "Weighed", used: "Used filament", deleted: "Deleted", restored: "Restored",
      archived: "Moved to archive", unarchived: "Back from archive", "bought another": "Bought another",
      "maintenance done": "Maintenance done", "task added": "Task added", "item added": "Item added", "item changed": "Item changed", "item deleted": "Item deleted",
      "printer added": "Printer added", "printer deleted": "Printer deleted" };
    const when = (iso) => { const d = new Date(iso); return isNaN(d) ? iso : d.toLocaleString([], { dateStyle: "medium", timeStyle: "short" }); };
    return rows.map((e) => {
      const spool = this.s.all.find((p) => p.id === e.id);
      const hasAmounts = e.before !== null && e.after !== null && Math.abs(e.after - e.before) > 0.04;
      const delta = hasAmounts ? `${fmtG(e.before)} → ${fmtG(e.after)} (${e.after - e.before > 0 ? "+" : "−"}${Math.round(Math.abs(e.after - e.before) * 10) / 10} g)` : e.after !== null && e.action === "added" ? fmtG(e.after) : "";
      const canSetBack = hasAmounts && spool && this.admin && Math.abs(spool.remaining_weight - e.before) > 0.04;
      return h("div", { class: "hrow", "data-history": e.action },
        h("div", {}, h("b", {}, LABEL[e.action] || e.action), showName ? ` · ${e.name}` : "", delta ? ` · ${delta}` : "", e.note && e.action !== "used" ? h("small", {}, ` (${e.note})`) : null,
          h("small", { class: "wd" }, when(e.t))),
        canSetBack ? h("button", { "data-set-back": e.id, title: `Set this spool back to ${fmtG(e.before)}`, onClick: async () => {
          try { await this._call({ type: "update", spool_id: e.id, remaining_weight: e.before }); this._toast(`Set back to ${fmtG(e.before)}`); this._reloadHistory?.(); } catch {} } }, `Set back to ${fmtG(e.before)}`) : null);
    });
  }

  historyDialog(p) {
    const box = h("div", { class: "hist" }, h("div", { class: "none" }, "Loading…"));
    const load = async () => {
      try { const rows = await this._call({ type: "history", spool_id: p.id, limit: 100 });
        box.replaceChildren(...(rows.length ? this._historyRows(rows, { showName: false }) : [h("div", { class: "none" }, "Nothing recorded yet for this spool.")])); } catch {}
    };
    this._reloadHistory = load; load();
    this._modal(`History: ${p.name}`, [box], [{ label: "Close", primary: true, run: (c) => { this._reloadHistory = null; c(); } }]);
  }

  _historyView() {
    const box = h("div", { class: "panel hist" }, h("div", { class: "none" }, "Loading…"));
    const load = async () => {
      try { const rows = await this._call({ type: "history", limit: 200 });
        box.replaceChildren(...(rows.length ? this._historyRows(rows, { showName: true }) : [h("div", { class: "none" }, "Nothing recorded yet. Changes to your spools will show up here.")])); } catch {}
    };
    this._reloadHistory = load; load();
    return box;
  }


  /* ---------- printer tab: maintenance, parts and consumables ---------- */
  _eqBadge() {
    const n = this.s.equipment.tasks.filter((t) => t.state === "overdue").length + this.s.equipment.items.filter((i) => i.low).length;
    return n ? `Printer (${n})` : "Printer";
  }

  _eqDate(iso) { const d = new Date(`${iso}T12:00:00`); return isNaN(d) ? iso : d.toLocaleDateString([], { day: "numeric", month: "short", year: "numeric" }); }

  _dueText(t) {
    if (t.days_left < 0) return `overdue by ${-t.days_left} ${-t.days_left === 1 ? "day" : "days"}`;
    if (t.days_left === 0) return "due today";
    return `due in ${t.days_left} ${t.days_left === 1 ? "day" : "days"}`;
  }

  _printerView() {
    const eq = this.s.equipment;
    const adm = this.admin;
    if (!eq.printers.length && !eq.items.length) {
      return h("div", { class: "panel none" }, h("p", {}, "Keep track of your printer's maintenance, spare nozzles, print sheets and consumables like IPA."),
        adm ? h("button", { class: "primary", "data-add-printer": "", onClick: () => this.printerDialog(null) }, icon("plus"), "Add my printer") : null);
    }
    const sections = eq.printers.map((pr) => {
      const tasks = eq.tasks.filter((t) => t.printer_id === pr.id).sort((a, b) => a.days_left - b.days_left);
      return h("section", { class: "loc", "data-printer": pr.id },
        h("h2", {}, pr.name, pr.model ? h("small", {}, pr.model) : null,
          adm ? h("span", { class: "grow" }) : null,
          adm ? h("button", { class: "bare", title: "Edit printer", "aria-label": "Edit printer", onClick: () => this.printerDialog(pr) }, icon("pencil")) : null,
          adm ? h("button", { class: "bare danger", title: "Delete printer", "aria-label": "Delete printer", onClick: () => this.printerDeleteDialog(pr) }, icon("delete-outline")) : null),
        h("div", { class: "panel" },
          tasks.length ? tasks.map((t) => h("div", { class: "hrow", "data-task": t.id },
            h("div", {}, h("b", {}, t.name), " ", h("span", { class: `chip ${t.state === "overdue" ? "err" : t.state === "soon" ? "warn" : ""}`, "data-task-state": t.state }, this._dueText(t)),
              h("small", { class: "wd" }, `every ${t.interval_days} days · last done ${this._eqDate(t.last_done)}${t.notes ? ` · ${t.notes}` : ""}`)),
            adm ? h("div", { class: "actions" },
              h("button", { class: t.state === "ok" ? "" : "primary", "data-task-done": t.id, onClick: () => this.taskDone(t) }, "Done"),
              h("button", { class: "bare", title: "Edit task", "aria-label": `Edit ${t.name}`, onClick: () => this.taskDialog(pr, t) }, icon("pencil"))) : null))
            : h("div", { class: "none" }, "No maintenance tasks yet."),
          adm ? h("div", { class: "hrow" }, h("button", { "data-add-task": pr.id, onClick: () => this.taskDialog(pr, null) }, icon("plus"), "Add task")) : null));
    });
    const catOrder = ["Nozzle", "Print sheet", "Consumable", "Spare part", "Tool", "Other"];
    const items = [...eq.items].sort((a, b) => (catOrder.indexOf(a.category) + 1 || 99) - (catOrder.indexOf(b.category) + 1 || 99) || a.name.localeCompare(b.name));
    const printerName = (id) => eq.printers.find((x) => x.id === id)?.name || "";
    return h("div", {}, sections,
      adm && eq.printers.length < 5 ? h("div", { class: "filterbar" }, h("button", { "data-add-printer": "", onClick: () => this.printerDialog(null) }, icon("plus"), eq.printers.length ? "Add another printer" : "Add my printer")) : null,
      h("section", { class: "loc", "data-items": "" },
        h("h2", {}, "Parts and consumables", h("small", {}, `${items.length} ${items.length === 1 ? "item" : "items"}`),
          h("span", { class: "grow" }),
          adm ? h("button", { "data-add-item": "", onClick: () => this.itemDialog(null) }, icon("plus"), "Add item") : null),
        h("div", { class: "panel" }, items.length ? items.map((i) => h("div", { class: "hrow", "data-item": i.id },
          h("div", {}, h("b", {}, i.name), " ", h("span", { class: "chip" }, i.category),
            i.low ? h("span", { class: "chip warn", "data-item-low": "" }, "low") : null, i.reorder ? h("span", { class: "chip warn" }, "reorder") : null,
            h("small", { class: "wd" }, [printerName(i.printer_id), i.low_at ? `alert at ${i.low_at} ${i.unit}`.trim() : "", i.notes].filter(Boolean).join(" · "))),
          h("div", { class: "actions" },
            adm ? h("button", { class: "bare", "data-item-minus": i.id, title: "Use one", "aria-label": `Use one ${i.name}`, onClick: () => this.itemAdjust(i, -1) }, "−") : null,
            h("b", { "data-item-qty": i.id, style: { minWidth: "56px", textAlign: "center" } }, `${i.quantity} ${i.unit}`.trim()),
            adm ? h("button", { class: "bare", "data-item-plus": i.id, title: "Add one", "aria-label": `Add one ${i.name}`, onClick: () => this.itemAdjust(i, 1) }, "+") : null,
            adm ? h("button", { class: "bare", title: "Edit", "aria-label": `Edit ${i.name}`, "data-item-edit": i.id, onClick: () => this.itemDialog(i) }, icon("pencil")) : null)))
          : h("div", { class: "none" }, "No parts or consumables yet. Add spare nozzles, print sheets, IPA, wipes and so on."))));
  }

  async taskDone(t) {
    try { await this._call({ type: "task_done", task_id: t.id }); this._toast(`${t.name}: done, next in ${t.interval_days} days`); } catch {}
  }

  async itemAdjust(i, delta) {
    if (i.quantity + delta < 0) return;
    try { await this._call({ type: "item_adjust", item_id: i.id, delta }); } catch {}
  }

  printerDialog(pr) {
    const name = h("input", { type: "text", maxlength: "60", value: pr?.name || "", placeholder: "e.g. Core One+", "data-printer-name": "" });
    const model = h("input", { type: "text", maxlength: "60", value: pr?.model || "", placeholder: "e.g. Prusa Core One+ (optional)" });
    const starter = h("input", { type: "checkbox", checked: true, "data-starter": "" });
    const go = async (c) => {
      if (!name.value.trim()) return this._toast("Enter a name", true);
      try {
        if (pr) await this._call({ type: "printer_update", printer_id: pr.id, name: name.value, model: model.value });
        else await this._call({ type: "printer_add", name: name.value, model: model.value, starter: starter.checked });
        c(); this._toast(pr ? "Printer updated" : "Printer added");
      } catch {}
    };
    name.addEventListener("keydown", (e) => { if (e.key === "Enter") go(close); });
    const close = this._modal(pr ? "Edit printer" : "Add printer", [this.field("Name", name), this.field("Model", model),
      pr ? null : h("label", { class: "row2" }, starter, h("span", {}, "Add a starter list of maintenance tasks (sheet cleaning, nozzle area, rods, belts, fans, general check). You can change or delete any of them."))],
    [{ label: "Cancel", run: (c) => c() }, { label: pr ? "Save" : "Add", primary: true, run: go }]);
  }

  printerDeleteDialog(pr) {
    this._modal("Delete printer?", h("p", {}, `Remove “${pr.name}” and its maintenance tasks? Parts and consumables are kept.`),
      [{ label: "Cancel", run: (c) => c() }, { label: "Delete", primary: true, run: async (c) => { try { await this._call({ type: "printer_delete", printer_id: pr.id }); c(); this._toast("Printer deleted"); } catch {} } }]);
  }

  taskDialog(pr, t) {
    const name = h("input", { type: "text", maxlength: "80", value: t?.name || "", placeholder: "e.g. Lubricate the rods", "data-task-name": "" });
    const days = h("input", { type: "number", min: "1", max: "3650", step: "1", value: String(t?.interval_days || 30), "data-task-days": "" });
    const last = h("input", { type: "date", value: t?.last_done || new Date().toISOString().slice(0, 10), max: new Date().toISOString().slice(0, 10), "data-task-last": "" });
    const notes = h("input", { type: "text", maxlength: "300", value: t?.notes || "", placeholder: "optional" });
    const go = async (c) => {
      const d = num(days.value);
      if (!name.value.trim()) return this._toast("Enter a name", true);
      if (d === null || d < 1 || d > 3650 || !Number.isInteger(d)) return this._toast("Enter the interval in whole days (1 to 3650)", true);
      const msg = { name: name.value, interval_days: d, last_done: last.value, notes: notes.value };
      try {
        if (t) await this._call({ type: "task_update", task_id: t.id, ...msg }); else await this._call({ type: "task_add", printer_id: pr.id, ...msg });
        c(); this._toast(t ? "Task updated" : "Task added");
      } catch {}
    };
    const close = this._modal(t ? "Edit task" : `Add task: ${pr.name}`, [this.field("Task", name), h("div", { class: "two" }, this.field("Repeat every, days", days), this.field("Last done", last)), this.field("Notes", notes)],
      [t ? { label: "Delete", run: async (c) => { try { await this._call({ type: "task_delete", task_id: t.id }); c(); this._toast("Task deleted"); } catch {} } } : null,
        { label: "Cancel", run: (c) => c() }, { label: "Save", primary: true, run: go }].filter(Boolean));
  }

  itemDialog(i) {
    const cats = ["Nozzle", "Print sheet", "Consumable", "Spare part", "Tool", "Other"];
    if (i && !cats.includes(i.category)) cats.push(i.category);
    const name = h("input", { type: "text", maxlength: "80", value: i?.name || "", placeholder: "e.g. Nozzle 0.4 mm hardened", "data-item-name": "" });
    const cat = h("select", { "data-item-cat": "" }, cats.map((c) => h("option", { value: c, selected: (i?.category || "Consumable") === c }, c)));
    const qty = h("input", { type: "number", min: "0", step: "any", value: String(i?.quantity ?? 1), "data-item-quantity": "" });
    const unit = h("input", { type: "text", maxlength: "12", value: i?.unit ?? "pcs", placeholder: "pcs, ml, g" });
    const low = h("input", { type: "number", min: "0", step: "any", value: i?.low_at ? String(i.low_at) : "", placeholder: "0 = no alert", "data-item-low-at": "" });
    const printers = this.s.equipment.printers;
    const prn = h("select", { "data-item-printer": "" }, h("option", { value: "" }, "Any printer"), printers.map((x) => h("option", { value: x.id, selected: i?.printer_id === x.id }, x.name)));
    const notes = h("input", { type: "text", maxlength: "300", value: i?.notes || "", placeholder: "optional, e.g. 0.4 mm, high flow" });
    const reorder = h("input", { type: "checkbox", checked: !!i?.reorder });
    const go = async (c) => {
      const q = num(qty.value), l = num(low.value) ?? 0;
      if (!name.value.trim()) return this._toast("Enter a name", true);
      if (q === null || q < 0) return this._toast("Enter the quantity you have", true);
      if (l < 0) return this._toast("The alert level cannot be negative", true);
      const msg = { name: name.value, category: cat.value, quantity: q, unit: unit.value, low_at: l, printer_id: prn.value, notes: notes.value, reorder: reorder.checked };
      try {
        if (i) await this._call({ type: "item_update", item_id: i.id, ...msg }); else await this._call({ type: "item_add", ...msg });
        c(); this._toast(i ? "Item updated" : "Item added");
      } catch {}
    };
    const close = this._modal(i ? "Edit item" : "Add part or consumable", [this.field("Name", name), h("div", { class: "two" }, this.field("Category", cat), this.field("Printer", prn)),
      h("div", { class: "two" }, this.field("How many do you have", qty), this.field("Unit", unit)),
      this.field("Warn me when it gets down to", low, "A Home Assistant notification and the shopping list use this."), this.field("Notes", notes),
      h("label", { class: "row2" }, reorder, h("span", {}, "On the shopping list"))],
    [i ? { label: "Delete", run: async (c) => { try { await this._call({ type: "item_delete", item_id: i.id }); c(); this._toast("Item deleted"); } catch {} } } : null,
      { label: "Cancel", run: (c) => c() }, { label: "Save", primary: true, run: go }].filter(Boolean));
  }

  _archiveView() {
    const rows = [...this.s.archived].sort((a, b) => String(b.archived_at).localeCompare(String(a.archived_at)));
    if (!rows.length) return h("div", { class: "panel none" }, "Nothing archived. Use the ▣ button on a finished spool to keep it as a record without cluttering the list.");
    return h("div", { class: "panel scroll" }, h("table", {}, h("tbody", {}, rows.map((p) => h("tr", { "data-archived": p.id },
      h("td", {}, h("div", { class: "name" }, this._badge(p.vendor), h("span", { class: "swatch", style: { background: p.color_hex } }),
        h("div", {}, p.name, h("small", {}, `${p.archived_at ? `Finished ${p.archived_at.slice(0, 10)} · ` : ""}${fmtG(p.remaining_weight)} left`), p.reorder ? h("div", {}, this._chips(p, false)) : null))),
      h("td", {}, this.admin ? h("div", { class: "actions" },
        p.reorder ? h("button", { class: "bare", "data-act": "rebuy", title: "Bought another", "aria-label": "Bought another", onClick: () => this.rebuyDialog(p) }, icon("cart-plus")) : null,
        h("button", { class: "bare", "data-act": "unarchive", title: "Put back in the inventory", "aria-label": "Put back in the inventory", onClick: () => this.archive(p, false) }, icon("archive-arrow-up-outline")),
        h("button", { class: "bare danger", title: "Delete", "aria-label": "Delete", onClick: () => this.deleteDialog(p) }, icon("delete-outline"))) : null))))));
  }

  /** Weigh many spools in a row: type the scale reading, press Enter, next spool. */
  weighSession() {
    const locs = this._locOptions();
    const scopes = [["never", "Never weighed"], ["all", "All spools"], ...locs.map((l) => [`loc:${l}`, `Only ${l}`])];
    const scope = h("select", { "aria-label": "Which spools" }, scopes.map(([v, l]) => h("option", { value: v }, l)));
    const pick = () => {
      const v = scope.value;
      return this.s.spools.filter((p) => v === "all" ? true : v === "never" ? !p.weighed : (p.location || NO_LOCATION) === v.slice(4))
        .sort((a, b) => (a.location || "~").localeCompare(b.location || "~") || a.name.localeCompare(b.name));
    };
    const area = h("div", {});
    let queue = [], i = 0, done = 0, lastTare = null;
    const close = () => this._wsClose && this._wsClose();
    const render = () => {
      if (!queue.length) return area.replaceChildren(h("p", {}, "No spools in this selection."));
      if (i >= queue.length) return area.replaceChildren(h("p", { "data-ws-done": "" }, `Done: ${done} ${done === 1 ? "spool" : "spools"} updated.`));
      const p = queue[i];
      const gross = h("input", { type: "number", min: "0", step: "any", placeholder: "scale reading incl. spool", "data-ws-gross": "", inputmode: "decimal" });
      const tare = h("input", { type: "number", min: "0", step: "any", "data-ws-tare": "", value: String(p.spool_weight || lastTare || "") });
      const out = h("span", { class: "hint", "data-ws-out": "" }, "");
      const check = () => {
        const g = num(gross.value), t = num(tare.value) ?? 0;
        if (g === null) { out.textContent = ""; return null; }
        if (g < t) { out.textContent = "⚠ Reading is below the empty spool weight"; return "bad"; }
        const net = g - t;
        out.textContent = `= ${fmtG(net)} of filament (was ${fmtG(p.remaining_weight)})` + (net > p.initial_weight + 50 ? " ⚠ more than a full spool, check the empty spool weight" : "");
        return net > p.initial_weight + 50 ? "warn" : "ok";
      };
      gross.addEventListener("input", check); tare.addEventListener("input", check);
      const save = async () => {
        const g = num(gross.value), t = num(tare.value);
        if (g === null) return this._toast("Enter the scale reading, or press Skip", true);
        if (t === null) return this._toast("Enter the empty spool weight", true);
        if (check() === "bad") return this._toast("Reading is below the empty spool weight", true);
        const msg = { type: "weigh", spool_id: p.id, gross_weight: g }; if (t !== p.spool_weight) msg.spool_weight = t;
        try { await this._call(msg); } catch { return; }
        lastTare = t; done++; i++; render();
      };
      gross.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); save(); } });
      area.replaceChildren(
        h("p", { class: "hint", "data-ws-progress": "" }, `Spool ${i + 1} of ${queue.length}${p.location ? ` · ${p.location}` : ""}`),
        h("div", { class: "name" }, this._badge(p.vendor), h("span", { class: "swatch", style: { background: p.color_hex } }), h("b", { "data-ws-name": "" }, p.name)),
        this.field("Scale reading (spool + filament), g", gross), this.field("Empty spool weight, g", tare), out,
        h("div", { class: "row" }, h("button", { "data-ws-skip": "", onClick: () => { i++; render(); } }, "Skip"), h("button", { class: "primary", "data-ws-save": "", onClick: save }, "Save and next")));
      gross.focus();
    };
    const start = h("button", { class: "primary", "data-ws-start": "", onClick: () => { queue = pick(); i = 0; done = 0; render(); } }, "Start");
    this._wsClose = this._modal("Weigh session", [this.field("Which spools", scope, "Never weighed = spools you have not put on the scale yet."), start, area], [{ label: "Close", primary: true, run: (c) => c() }]);
  }

  async _download(name, text, type) {
    const url = URL.createObjectURL(new Blob([text], { type }));
    const a = h("a", { href: url, download: name }); this.shadowRoot.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
  }

  async backupDownload() {
    try { const data = await this._call({ type: "export" });
      this._download(`spool-inventory-${new Date().toISOString().slice(0, 10)}.json`, JSON.stringify(data, null, 2), "application/json");
      this._toast("Backup file created"); } catch {}
  }

  csvDownload() {
    const cols = ["vendor", "material", "product", "color_name", "color_hex", "diameter", "initial_weight", "spool_weight", "remaining_weight", "price", "location", "notes", "loaded", "reorder", "refill", "archived", "weighed", "created"];
    const esc = (v) => { v = v === null || v === undefined ? "" : String(v); return /[",\n\r;]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v; };
    const text = [cols.join(","), ...this.s.all.map((p) => cols.map((c) => esc(p[c])).join(","))].join("\r\n");
    this._download(`spool-inventory-${new Date().toISOString().slice(0, 10)}.csv`, "﻿" + text, "text/csv");
    this._toast("Spreadsheet file created");
  }

  backupRestore(file) {
    const reader = new FileReader();
    reader.onerror = () => this._toast("Could not read that file", true);
    reader.onload = () => {
      let data; try { data = JSON.parse(reader.result); } catch { return this._toast("That is not a backup file", true); }
      if (!data || data.format !== "spool_inventory_backup" || !Array.isArray(data.spools)) return this._toast("That is not a Spool Inventory backup", true);
      const run = async (replace, c) => { try { const r = await this._call({ type: "import", data, replace });
        c(); this._toast(`${replace ? "Restored" : "Added"} ${r.added} spools${r.skipped ? `, ${r.skipped} entries skipped` : ""}`); } catch {} };
      this._modal("Restore backup", [h("p", {}, `This file has ${data.spools.length} spools.`),
        h("p", { class: "hint" }, "“Add missing” keeps everything you have and only adds spools that are not here yet. “Replace everything” makes the inventory exactly like the file (a safety copy of the current data is kept first).")],
      [{ label: "Cancel", run: (c) => c() }, { label: "Add missing", "data-restore": "merge", run: (c) => run(false, c) }, { label: "Replace everything", primary: true, "data-restore": "replace", run: (c) => run(true, c) }]);
    };
    reader.readAsText(file);
  }

  async _flag(p, key) {
    try { await this._call({ type: "update", spool_id: p.id, [key]: !p[key] }); } catch {}
  }

  _grams(p) {
    const input = h("input", { type: "number", min: "0", step: "any", value: String(Math.round(p.remaining_weight * 10) / 10),
      "aria-label": `Remaining grams of ${p.name}`, disabled: !this.admin });
    const save = async () => {
      const v = num(input.value);
      if (v === null || v < 0 || Math.abs(v - p.remaining_weight) < 0.05) { input.value = String(Math.round(p.remaining_weight * 10) / 10); return; }
      try { await this._call({ type: "update", spool_id: p.id, remaining_weight: v }); } catch { input.value = String(p.remaining_weight); }
    };
    input.addEventListener("change", save);
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") input.blur(); if (e.key === "Escape") { input.value = String(p.remaining_weight); input.blur(); } });
    return h("span", { class: "grams" }, input, "g");
  }

  _buttons(p) {
    if (!this.admin) return null;
    const b = (ic, title, fn, cls = "") => h("button", { class: `bare ${cls}`, title, "aria-label": title, onClick: fn }, icon(ic));
    return h("div", { class: "actions" },
      h("button", { class: `bare${p.loaded ? " on" : ""}`, "data-act": "loaded", "aria-pressed": String(!!p.loaded),
        title: p.loaded ? "Loaded in the printer (click to unload)" : "Mark as loaded in the printer",
        "aria-label": p.loaded ? "Unmark loaded in printer" : "Mark as loaded in printer", onClick: () => this._flag(p, "loaded") }, icon("printer-3d")),
      h("button", { class: `bare${p.reorder ? " on" : ""}`, "data-act": "reorder", "aria-pressed": String(!!p.reorder),
        title: p.reorder ? "On the reorder list (click to remove)" : "Add to the reorder list",
        "aria-label": p.reorder ? "Remove from reorder list" : "Add to reorder list", onClick: () => this._flag(p, "reorder") }, icon("cart-outline")),
      p.reorder ? h("button", { class: "bare", "data-act": "rebuy", title: "Bought another: add a new full spool like this one", "aria-label": "Bought another", onClick: () => this.rebuyDialog(p) }, icon("cart-plus")) : null,
      b("scale", "Weigh spool", () => this.weighDialog(p)), b("minus-circle-outline", "Use filament", () => this.useDialog(p)),
      h("button", { class: "bare", "data-act": "more", title: "More: edit, history, copy, archive, delete", "aria-label": "More actions", "aria-haspopup": "menu",
        onClick: (e) => this._moreMenu(p, e.currentTarget) }, "⋯"));
  }

  /** Small popup with the less common actions, so the row stays tidy. */
  _moreMenu(p, anchor) {
    this._closeMenu?.();
    const item = (ic, label, fn, cls = "") => h("button", { class: `mi ${cls}`, role: "menuitem", title: label, "aria-label": label, onClick: () => { this._closeMenu?.(); fn(); } }, icon(ic), h("span", {}, label));
    const menu = h("div", { class: "menu", role: "menu", "data-menu": p.id },
      item("pencil", "Edit", () => this.spoolDialog(p)),
      item("history", "History of this spool", () => this.historyDialog(p)),
      item("content-copy", "Add another like this one", () => this.spoolDialog(null, p)),
      item("archive-outline", "Finished: move to the archive", () => this.archive(p, true)),
      item("delete-outline", "Delete", () => this.deleteDialog(p), "danger"));
    this.shadowRoot.append(menu);
    const r = anchor.getBoundingClientRect();
    const w = menu.offsetWidth, hgt = menu.offsetHeight;
    menu.style.left = `${Math.max(8, Math.min(window.innerWidth - w - 8, r.right - w))}px`;
    menu.style.top = `${r.bottom + hgt + 8 > window.innerHeight ? Math.max(8, r.top - hgt - 4) : r.bottom + 4}px`;
    const away = (e) => { if (!e.composedPath().includes(menu)) this._closeMenu(); };
    const key = (e) => { if (e.key === "Escape") { this._closeMenu(); anchor.focus(); } };
    this._closeMenu = () => { menu.remove(); document.removeEventListener("pointerdown", away, true); document.removeEventListener("keydown", key, true); this._closeMenu = null; };
    document.addEventListener("pointerdown", away, true); document.addEventListener("keydown", key, true);
    menu.querySelector("button")?.focus();
  }

  _bar(p) { return h("div", { class: `bar-bg ${this._state(p)}` }, h("div", { class: "bar-fg", style: { width: `${p.remaining_percent}%` } })); }

  _table() {
    const rows = this.filtered();
    if (!rows.length) return h("div", { class: "panel none" }, this.s.spools.length ? "No spools match the filter." : "No spools yet. Use “Add spool” to start your inventory.");
    const th = (label, key, cls = "") => h("th", { class: `sort ${cls}`, onClick: () => {
      this.s.sortDir = this.s.sortKey === key ? -this.s.sortDir : 1; this.s.sortKey = key; this._main(); } },
    label, this.s.sortKey === key ? (this.s.sortDir > 0 ? " ▲" : " ▼") : "");
    const body = rows.map((p) => h("tr", { "data-spool": p.id },
      h("td", {}, h("div", { class: "name" }, this._badge(p.vendor), h("span", { class: "swatch", style: { background: p.color_hex }, title: p.color_hex }),
        h("div", {}, p.name, h("small", {}, [p.diameter ? `${p.diameter} mm` : "", p.notes].filter(Boolean).join(" · ")),
          h("small", { class: p.weighed ? "wd" : "wd never", "data-weighed": "" }, this.weighedText(p)),
          p.loaded || p.reorder || p.refill ? h("div", {}, this._chips(p, false)) : null))),
      h("td", {}, p.material),
      h("td", {}, this._grams(p), this._bar(p)),
      h("td", { class: "num" }, `${Math.round(p.remaining_percent)}%`, " ", this._chips(p).slice(0, 2)),
      h("td", {}, p.location || ""),
      h("td", {}, this._buttons(p))));
    return h("div", { class: "panel scroll" }, h("table", {},
      h("thead", {}, h("tr", {}, th("Spool", "name"), th("Material", "material"), th("Remaining", "remaining"), th("%", "pct", "num"), th("Location", "location"), h("th"))),
      h("tbody", {}, body)));
  }

  _cards() {
    const rows = this.filtered();
    if (!rows.length) return h("div", { class: "panel none" }, this.s.spools.length ? "No spools match the filter." : "No spools yet. Use “Add spool” to start your inventory.");
    return h("div", { class: "cards" }, rows.map((p) => {
      const r = 32, c = 2 * Math.PI * r;
      const ring = h("div", { class: "ring" },
        (() => { const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg"); svg.setAttribute("viewBox", "0 0 76 76");
          svg.innerHTML = `<circle cx="38" cy="38" r="${r}" fill="none" stroke="rgba(128,128,128,.25)" stroke-width="8"/>` +
            `<circle cx="38" cy="38" r="${r}" fill="none" stroke="rgba(0,0,0,.55)" stroke-width="10" stroke-dasharray="${(c * p.remaining_percent) / 100} ${c}" stroke-linecap="butt"/>` +
            `<circle class="arc" cx="38" cy="38" r="${r}" fill="none" stroke-width="8" stroke-dasharray="${(c * p.remaining_percent) / 100} ${c}"/>`;
          svg.querySelector(".arc").setAttribute("stroke", p.color_hex); return svg; })(),
        h("div", { class: "mid" }, h("b", {}, `${Math.round(p.remaining_percent)}%`), h("span", {}, p.material)));
      return h("div", { class: `card ${this._state(p)}`, "data-spool": p.id },
        h("div", { class: "top" }, ring, h("div", {}, h("h3", {}, p.color_name || p.name), h("div", { class: "meta" }, `${p.vendor}${p.product ? ` · ${p.product}` : ""}`),
          h("div", { class: "meta" }, [p.location, p.diameter ? `${p.diameter} mm` : ""].filter(Boolean).join(" · ")),
          h("div", { class: `meta wd${p.weighed ? "" : " never"}`, "data-weighed": "" }, this.weighedText(p)))),
        h("div", { class: "row" }, this._badge(p.vendor), this._grams(p), h("span", {}, this._chips(p))),
        this._bar(p), this._buttons(p));
    }));
  }

  _colorsTable() {
    const groups = this.groups();
    if (!groups.length) return h("div", { class: "panel none" }, "No spools yet.");
    const max = Math.max(...groups.map((g) => g.total), 1);
    const total = groups.reduce((a, g) => a + g.total, 0);
    const mats = new Map();
    groups.forEach((g) => mats.set(g.material, (mats.get(g.material) || 0) + g.total));
    return h("div", {},
      h("div", { class: "panel scroll" }, h("table", {},
        h("thead", {}, h("tr", {}, h("th", {}, "Color"), h("th", {}, "Material"), h("th", { class: "num" }, "Spools"), h("th", {}, "Remaining"), h("th", {}, "Per spool"))),
        h("tbody", {}, groups.map((g) => h("tr", { "data-group": `${g.material}|${g.color}` },
          h("td", {}, h("div", { class: "name" }, h("span", { class: "swatch", style: { background: g.hex } }), g.color)),
          h("td", {}, g.material), h("td", { class: "num" }, g.spools.length),
          h("td", {}, h("b", {}, fmtG(g.total)), h("div", { class: "bar-bg" }, h("div", { class: "bar-fg", style: { width: `${(g.total / max) * 100}%` } }))),
          h("td", {}, g.spools.sort((a, b) => b.remaining_weight - a.remaining_weight).map((p) =>
            h("span", { class: `chip ${p.remaining_weight <= 0 ? "err" : p.remaining_weight < this.low ? "warn" : ""}` }, `${p.vendor} ${fmtG(p.remaining_weight)}`)))))),
        h("tfoot", {}, h("tr", {}, h("td", { colspan: "2" }, "Total"), h("td", { class: "num" }, this.s.spools.length), h("td", { colspan: "2" }, fmtKg(total)))))),
      h("p", { class: "hint" }, "By material: ", [...mats].map(([m, g]) => h("span", { class: "chip" }, `${m} ${fmtKg(g)}`))));
  }

  _locationsView() {
    if (!this.s.spools.length) return h("div", { class: "panel none" }, "No spools yet.");
    const map = new Map();
    for (const l of this.locations()) map.set(l, []);
    for (const p of this.s.spools) {
      const k = p.location ? [...map.keys()].find((x) => x.toLowerCase() === p.location.toLowerCase()) || p.location : NO_LOCATION;
      if (!map.has(k)) map.set(k, []);
      map.get(k).push(p);
    }
    const options = [...this.locations(), NO_LOCATION];
    const groups = [...map.entries()].filter(([k, list]) => list.length || k !== NO_LOCATION)
      .sort(([a], [b]) => (a === NO_LOCATION) - (b === NO_LOCATION));
    return h("div", {}, groups.map(([name, list]) => {
      list.sort((a, b) => a.name.localeCompare(b.name));
      const total = list.reduce((a, p) => a + p.remaining_weight, 0);
      const mats = new Map(); list.forEach((p) => mats.set(p.material, (mats.get(p.material) || 0) + p.remaining_weight));
      return h("section", { class: "loc", "data-location": name },
        h("h2", {}, name, h("small", {}, `${list.length} ${list.length === 1 ? "spool" : "spools"} · ${fmtKg(total)}${this.stockValue(list).any ? ` · ${this.money(this.stockValue(list).value)} value` : ""}`),
          [...mats].map(([m, g]) => h("span", { class: "chip" }, `${m} ${fmtKg(g)}`))),
        list.length ? h("div", { class: "panel scroll" }, h("table", {}, h("tbody", {}, list.map((p) => h("tr", { "data-spool": p.id },
          h("td", {}, h("div", { class: "name" }, this._badge(p.vendor), h("span", { class: "swatch", style: { background: p.color_hex } }), h("div", {}, p.name, h("div", {}, this._chips(p))))),
          h("td", {}, this._grams(p), this._bar(p)),
          h("td", {}, this.admin ? h("select", { "aria-label": `Move ${p.name} to another location`, "data-move": p.id, onChange: async (e) => {
            const to = e.target.value === NO_LOCATION ? "" : e.target.value;
            try { await this._call({ type: "update", spool_id: p.id, location: to }); this._toast(`Moved to ${e.target.value}`); } catch {} } },
          h("option", { value: "", disabled: true, selected: true }, "Move to…"), options.filter((o) => o !== name).map((o) => h("option", { value: o }, o))) : null))))))
          : h("div", { class: "panel none" }, "Nothing stored here."));
    }));
  }

  async shoppingList() {
    const rows = this.s.all.filter((p) => p.reorder);
    const extra = this.s.equipment.items.filter((i) => i.to_reorder).map((i) => `- ${i.name}${i.category ? ` (${i.category})` : ""}`);
    const text = [...rows.map((p) => `- ${p.name}${p.refill ? " (refill)" : ""}${p.diameter && p.diameter !== 1.75 ? ` (${p.diameter} mm)` : ""} (${fmtG(p.remaining_weight)} left)`), ...extra].join("\n");
    try { await navigator.clipboard.writeText(text); this._toast("Shopping list copied"); return; } catch {}
    const box = h("textarea", { readOnly: true }, text);
    this._modal("Shopping list", [h("p", { class: "hint" }, "Copy this text:"), box], [{ label: "Close", primary: true, run: (c) => c() }]);
    box.focus(); box.select();
  }

  /* ---------- dialogs ---------- */
  _modal(title, body, buttons) {
    const close = () => { overlay.remove(); };
    const overlay = h("div", { class: "overlay", onMousedown: (e) => { if (e.target === overlay) close(); } },
      h("div", { class: "dlg", role: "dialog", "aria-modal": "true", "aria-label": title, onKeydown: (e) => { if (e.key === "Escape") close(); } },
        h("header", {}, title), h("div", { class: "body" }, body),
        h("footer", {}, buttons.map((b) => h("button", { class: b.primary ? "primary" : "", "data-restore": b["data-restore"] || null, onClick: () => b.run(close) }, b.label)))));
    this.shadowRoot.getElementById("dialogs").append(overlay);
    overlay.querySelector("input:not([type=checkbox]), select")?.focus();
    return close;
  }

  field(label, control, hint) { return h("div", { class: "field" }, h("label", {}, label), control, hint ? h("span", { class: "hint" }, hint) : null); }

  settingsDialog() {
    const st = this.s.settings || { low_threshold: DEFAULT_LOW_G, notify: true, locations: [] };
    const thr = h("input", { type: "number", min: "0", step: "any", value: String(st.low_threshold), "aria-label": "Low stock threshold" });
    const notify = h("input", { type: "checkbox", checked: !!st.notify, "aria-label": "Notify" });
    const curOpts = ["RON", "EUR", "USD", "GBP"];
    const curCur = st.currency || "RON";
    const curText = h("input", { type: "text", maxlength: "8", "data-currency-text": "", value: curOpts.includes(curCur) ? "" : curCur, placeholder: "e.g. CHF", hidden: curOpts.includes(curCur), "aria-label": "Currency (other)" });
    const curPick = h("select", { "data-currency": "", "aria-label": "Currency", onChange: (e) => { curText.hidden = e.target.value !== "__other__"; if (!curText.hidden) curText.focus(); } },
      curOpts.map((c) => h("option", { value: c, selected: c === curCur }, c)), h("option", { value: "__other__", selected: !curOpts.includes(curCur) }, "Other…"));
    const curSel = h("div", { style: { display: "grid", gap: "6px" } }, curPick, curText);
    const locs = h("textarea", { "aria-label": "Locations" }, (st.locations || []).join("\n"));
    const mine = h("div", { class: "catlist" });
    let shown = null;
    const fill = () => {
      const sig = JSON.stringify(this.s.userCatalog); if (sig === shown) return; shown = sig;
      mine.replaceChildren(...(this.s.userCatalog.length ? this.s.userCatalog.map((e) => h("div", { class: "row" },
        h("span", {}, `${e.vendor} · ${e.line ? `${e.line} ` : ""}${e.material} · ${e.name}`),
        h("button", { class: "bare danger", title: "Remove from my catalog", "aria-label": `Remove ${e.name} from my catalog`, "data-remove-entry": e.name,
          onClick: async () => { try { await this._call({ type: "catalog_remove", vendor: e.vendor, material: e.material, line: e.line, name: e.name }); } catch {} } }, icon("delete-outline"))))
        : [h("div", { class: "none" }, "Nothing saved yet. Add a custom spool and keep “Save to my catalog” ticked.")]));
    };
    fill();
    // keep the list current while the dialog is open (entries removed above push an update)
    const timer = setInterval(() => { if (!mine.isConnected) clearInterval(timer); else fill(); }, 600);
    const del = h("div", { class: "catlist" });
    let shownDel = null;
    const fillDel = () => {
      const sig = JSON.stringify(this.s.trash); if (sig === shownDel) return; shownDel = sig;
      del.replaceChildren(...(this.s.trash.length ? this.s.trash.map((t) => h("div", { class: "row" },
        h("span", {}, `${t.name} · ${fmtG(t.remaining_weight)}`),
        h("button", { "data-undelete": t.id, onClick: () => this.undelete(t.id) }, "Restore")))
        : [h("div", { class: "none" }, "Nothing deleted recently.")]));
    };
    fillDel();
    const timer2 = setInterval(() => { if (!del.isConnected) clearInterval(timer2); else fillDel(); }, 600);
    const fileIn = h("input", { type: "file", accept: ".json,application/json", hidden: true, "data-restore-file": "",
      onChange: (e) => { const f = e.target.files[0]; e.target.value = ""; if (f) this.backupRestore(f); } });
    this._modal("Settings", [
      this.field("Low stock threshold, g", thr, "A spool under this is “low”. Empty spools are always flagged."),
      h("label", { class: "row2" }, notify, h("span", {}, "Show a Home Assistant notification when a spool gets low or empty")),
      h("p", { class: "hint" }, "Home Assistant also fires the events spool_inventory_low and spool_inventory_empty, so an automation can send a phone message."),
      this.field("Currency for prices", curSel, "Shown on the value card and next to prices."),
      this.field("My locations (one per line)", locs, "Offered when you add or move a spool."),
      this.field("My catalog entries", mine),
      this.field("Recently deleted", del, "The last 25 deleted spools can be brought back."),
      this.field("Backup", h("div", { class: "row" },
        h("button", { "data-backup": "", onClick: () => this.backupDownload() }, icon("download"), "Download backup"),
        h("button", { "data-restore-pick": "", onClick: () => fileIn.click() }, icon("upload"), "Restore from file"),
        h("button", { "data-csv": "", onClick: () => this.csvDownload() }, icon("download"), "Spreadsheet (CSV)"), fileIn),
      "Home Assistant also keeps an automatic daily copy inside its .storage folder.")],
    [{ label: "Cancel", run: (c) => c() }, { label: "Save", primary: true, run: async (c) => {
      const v = num(thr.value); if (v === null || v < 0) return this._toast("Enter a threshold in grams", true);
      const currency = curPick.value === "__other__" ? curText.value.trim() : curPick.value;
      if (!currency) return this._toast("Enter a currency", true);
      try { await this._call({ type: "settings", low_threshold: v, notify: notify.checked, currency, locations: locs.value.split("\n") }); c(); this._toast("Settings saved"); } catch {} } }]);
  }

  deleteDialog(p) {
    this._modal("Delete spool?", h("p", {}, `Remove “${p.name}” (${fmtG(p.remaining_weight)} left) from the inventory? You can undo it for a while. If the spool is just finished, use the archive button instead.`),
      [{ label: "Cancel", run: (c) => c() },
        { label: "Delete", primary: true, run: async (c) => { try { await this._call({ type: "delete", spool_id: p.id }); c(); this._toast("Spool deleted", false, { label: "Undo", run: () => this.undelete(p.id) }); } catch {} } }]);
  }

  /** One button for "I printed something": subtract grams from the spool marked as loaded. */
  useLoadedDialog() {
    const loaded = this.s.spools.filter((p) => p.loaded);
    if (!loaded.length) return this._toast("No spool is marked as loaded in the printer", true);
    const pick = h("select", { "data-loaded-pick": "", "aria-label": "Which spool" }, loaded.map((p) => h("option", { value: p.id }, `${p.name} (${fmtG(p.remaining_weight)} left)`)));
    const grams = h("input", { type: "number", min: "0", step: "any", placeholder: "e.g. 37.5", "data-loaded-grams": "" });
    const hint = h("span", { class: "hint" }, "");
    const sel = () => loaded.find((p) => p.id === pick.value) || loaded[0];
    const upd = () => { const g = num(grams.value), p = sel(); hint.textContent = g !== null && g > p.remaining_weight ? `Only ${fmtG(p.remaining_weight)} is left on this spool, it will go to 0.` : ""; };
    grams.addEventListener("input", upd); pick.addEventListener("change", upd);
    const go = async (c) => { const v = num(grams.value); if (v === null || v < 0) return this._toast("Enter the grams used", true);
      const p = sel(); try { await this._call({ type: "consume", spool_id: p.id, grams: v }); c(); this._toast(`Subtracted ${v} g from ${p.name}`); } catch {} };
    grams.addEventListener("keydown", (e) => { if (e.key === "Enter") go(close); });
    const close = this._modal("Used in the printer", [loaded.length > 1 ? this.field("Which spool is it", pick) : h("p", {}, h("b", {}, sel().name), ` (${fmtG(sel().remaining_weight)} left)`),
      this.field("Grams used", grams), hint], [{ label: "Cancel", run: (c) => c() }, { label: "Subtract", primary: true, run: go }]);
    grams.focus();
  }

  useDialog(p) {
    const grams = h("input", { type: "number", min: "0", step: "any", placeholder: "e.g. 37.5" });
    const go = async (c) => { const v = num(grams.value); if (v === null || v < 0) return this._toast("Enter the grams used", true);
      try { await this._call({ type: "consume", spool_id: p.id, grams: v }); c(); this._toast(`Subtracted ${v} g`); } catch {} };
    grams.addEventListener("keydown", (e) => { if (e.key === "Enter") go(close); });
    const close = this._modal(`Use filament: ${p.name}`, [this.field("Grams used", grams, `${fmtG(p.remaining_weight)} left`)],
      [{ label: "Cancel", run: (c) => c() }, { label: "Subtract", primary: true, run: go }]);
  }

  weighDialog(p) {
    const gross = h("input", { type: "number", min: "0", step: "any", placeholder: "scale reading incl. spool" });
    const tare = h("input", { type: "number", min: "0", step: "any", value: p.spool_weight ? String(p.spool_weight) : "" });
    const out = h("span", { class: "hint" }, "");
    const upd = () => { const g = num(gross.value), t = num(tare.value) ?? 0; out.textContent = g === null ? "" : g < t ? "Scale reading is below the empty spool weight" : `= ${fmtG(g - t)} of filament`; };
    gross.addEventListener("input", upd); tare.addEventListener("input", upd);
    const go = async (c) => { const g = num(gross.value), t = num(tare.value);
      if (g === null) return this._toast("Enter the scale reading", true);
      if (t === null) return this._toast("Enter the empty spool weight", true);
      const msg = { type: "weigh", spool_id: p.id, gross_weight: g }; if (t !== p.spool_weight) msg.spool_weight = t;
      try { await this._call(msg); c(); this._toast("Weight updated"); } catch {} };
    gross.addEventListener("keydown", (e) => { if (e.key === "Enter") go(close); });
    const close = this._modal(`Weigh: ${p.name}`, [this.field("Scale reading (spool + filament), g", gross), this.field("Empty spool weight, g", tare), out],
      [{ label: "Cancel", run: (c) => c() }, { label: "Set weight", primary: true, run: go }]);
  }

  /** Remember a custom spool's brand/material/color so it can be picked from the catalog next time. */
  async _saveToCatalog(m) {
    if (!m.color_name) return;
    const line = m.product || "";
    const rows = this.s.catalog?.catalog?.[m.vendor]?.[m.material] || [];
    // already listed (shipped or saved) with the same line and color name: nothing to add
    if (rows.some((r) => r.line.toLowerCase() === line.toLowerCase() && r.name.toLowerCase() === m.color_name.toLowerCase())) return;
    const entry = { type: "catalog_add", vendor: m.vendor, material: m.material, line, name: m.color_name, hex: m.color, weights: [m.initial_weight || 1000] };
    if (m.spool_weight) entry.tare = m.spool_weight;
    try { await this._call(entry); this._toast("Saved to your catalog"); } catch {}
  }

  /** Last known empty-spool weight for a vendor/material from the user's own spools. */
  lastTare(vendor, material) {
    const hit = this.s.spools.filter((p) => p.vendor.toLowerCase() === vendor.toLowerCase() && p.material === material && p.spool_weight > 0)
      .sort((a, b) => String(b.updated).localeCompare(String(a.updated)))[0];
    return hit ? hit.spool_weight : null;
  }

  catalogRows(f) { return this.s.catalog?.catalog?.[f.vendor]?.[f.material] || []; }

  /** Keep the catalog selections consistent after any change and copy color/weights from the chosen entry. */
  applyCatalog(f) {
    const cat = this.s.catalog; if (!cat) return;
    const mats = Object.keys(cat.catalog[f.vendor] || {}).sort((a, b) => (cat.materials.indexOf(a) + 1 || 99) - (cat.materials.indexOf(b) + 1 || 99) || a.localeCompare(b));
    f._mats = mats; if (!mats.includes(f.material)) f.material = mats[0] || "";
    const rows = this.catalogRows(f);
    f._lines = [...new Set(rows.map((r) => r.line))]; // catalog order: standard first, then the common lines
    if (!f._lines.includes(f.line)) f.line = f._lines.includes("") ? "" : f._lines[0] ?? "";
    f._colors = rows.filter((r) => r.line === f.line);
    const entry = f._colors.find((r) => r.name === f.color);
    if (!entry) f.color = "";
    f._entry = entry || null;
    if (entry) {
      f.hex = entry.hex;
      if (!entry.weights.includes(Number(f.initial))) f.initial = String(entry.weights[0]);
    }
    if (!hasRefill(f.vendor)) f.refill = false;
    if (f.refill) f.initial = String(REFILL_G);
    if (!f.tareTouched) {
      const t = this.lastTare(f.vendor, f.material) ?? entry?.tare ?? null;
      f.tare = t === null ? "" : String(t);
      f.tareHint = t === null ? "" : this.lastTare(f.vendor, f.material) !== null ? "from your other spools of this brand" : "typical for this spool type";
    }
  }

  spoolDialog(spool, copyOf = null) {
    const edit = !!spool, cat = this.s.catalog;
    const f = copyOf
      ? { mode: "custom", vendor: copyOf.vendor, material: copyOf.material, line: "", product: copyOf.product || "", color: copyOf.color_name, hex: copyOf.color_hex,
        diameter: String(copyOf.diameter), initial: String(copyOf.initial_weight), tare: copyOf.spool_weight ? String(copyOf.spool_weight) : "", tareHint: "", tareTouched: true,
        start: "full", startValue: "", price: copyOf.price ?? "", location: copyOf.location, notes: "", tag: "", loaded: false, reorder: false, refill: !!copyOf.refill && hasRefill(copyOf.vendor), saveCatalog: false }
      : edit
      ? { vendor: spool.vendor, material: spool.material, product: spool.product || "", color: spool.color_name, hex: spool.color_hex,
        diameter: String(spool.diameter), initial: String(spool.initial_weight), tare: spool.spool_weight ? String(spool.spool_weight) : "",
        remaining: String(Math.round(spool.remaining_weight * 10) / 10), price: spool.price ?? "", location: spool.location, notes: spool.notes, tag: spool.tag_id,
        loaded: !!spool.loaded, reorder: !!spool.reorder, refill: !!spool.refill }
      : { mode: cat ? "catalog" : "custom", vendor: cat?.vendors?.[0]?.name || "", material: "PETG", line: "", product: "", color: "", hex: "#808080",
        diameter: "1.75", initial: "1000", tare: "", tareHint: "", tareTouched: false, start: "full", startValue: "", price: "", location: "", notes: "", tag: "", loaded: false, reorder: false, refill: false, saveCatalog: true };
    if (!edit && f.mode === "catalog") this.applyCatalog(f);
    const body = h("div", { style: { display: "grid", gap: "12px" } });
    let close;

    const text = (key, { after, ...attrs } = {}) => h("input", { type: "text", value: f[key] ?? "", ...attrs, onInput: (e) => { f[key] = e.target.value; after?.(); } });
    const numIn = (key, attrs = {}) => h("input", { type: "number", min: "0", step: "any", value: f[key] ?? "", ...attrs, onInput: (e) => { f[key] = e.target.value; if (key === "tare") f.tareTouched = true; preview(); } });
    // A dropdown with an "Other…" entry that reveals a text box. Unlike <datalist>, it works on phones.
    const combo = (key, options, { blank = "", placeholder = "" } = {}) => {
      const cur = String(f[key] ?? "");
      const match = options.find((o) => o.toLowerCase() === cur.toLowerCase());
      const other = f[`_other_${key}`] ?? (cur !== "" && !match);
      const pick = other ? "__other__" : match ?? "";
      const sel = h("select", { "data-combo": key, "aria-label": key, onChange: (e) => {
        if (e.target.value === "__other__") { f[`_other_${key}`] = true; f[key] = ""; } else { f[`_other_${key}`] = false; f[key] = e.target.value; }
        render(); } },
      h("option", { value: "", selected: pick === "" }, blank),
      options.map((o) => h("option", { value: o, selected: pick === o }, o)),
      h("option", { value: "__other__", selected: pick === "__other__" }, "Other…"));
      return h("div", { style: { display: "grid", gap: "6px" } }, sel,
        other ? h("input", { type: "text", "data-combo-text": key, value: cur, placeholder, "aria-label": `${key} (other)`, onInput: (e) => { f[key] = e.target.value; } }) : null);
    };
    const select = (key, options, onChange) => h("select", { onChange: (e) => { f[key] = e.target.value; onChange?.(); } },
      options.map(([v, l]) => h("option", { value: v, selected: String(f[key]) === String(v) }, l)));
    const preview = () => { const el = body.querySelector("[data-preview]"); if (!el) return;
      const g = num(f.startValue), t = num(f.tare) ?? 0;
      el.textContent = f.start === "gross" && g !== null ? (g < t ? "Scale reading is below the empty spool weight" : `= ${fmtG(g - t)} of filament`) : ""; };

    // Only Prusament sells refills (900 g without a spool), so the choice is offered for that brand only.
    const formatField = () => !hasRefill(f.vendor) ? null : this.field("Format", h("select", { "data-format": "", "aria-label": "Format", onChange: (e) => {
      f.refill = e.target.value === "refill";
      if (!edit) { if (f.refill) f.initial = String(REFILL_G); else if (f._entry) f.initial = String(f._entry.weights[0]); else if (Number(f.initial) === REFILL_G) f.initial = "1000"; }
      if (!edit && f.mode === "catalog") this.applyCatalog(f);
      render(); } },
    h("option", { value: "spool", selected: !f.refill }, "Spool"), h("option", { value: "refill", selected: !!f.refill }, `Refill (${REFILL_G} g, on a reusable spool)`)),
    f.refill ? "A refill has no spool of its own. The empty spool weight is that of the reusable spool you put it on." : null);

    const colorBlock = () => {
      const hex = h("input", { type: "color", value: f.hex, "aria-label": "Color", onInput: (e) => { f.hex = e.target.value; sw.style.background = f.hex; } });
      const sw = h("span", { class: "swatch", style: { background: f.hex } });
      return { hex, sw };
    };

    const render = () => {
      const parts = [];
      const was = body.querySelector("details"); if (was) f._more = was.open; // keep "More fields" as the user left it
      if (!edit) parts.push(h("div", { class: "seg" },
        h("button", { class: f.mode === "catalog" ? "on" : "", disabled: !cat, onClick: () => { f.mode = "catalog"; this.applyCatalog(f); render(); } }, "From catalog"),
        h("button", { class: f.mode === "custom" ? "on" : "", onClick: () => { f.mode = "custom"; render(); } }, "Custom")));

      if (!edit && f.mode === "catalog") {
        const { hex, sw } = colorBlock();
        parts.push(
          h("div", { class: "two" },
            this.field("Vendor", select("vendor", cat.vendors.map((v) => [v.name, v.name]), () => { f.tareTouched = false; this.applyCatalog(f); render(); })),
            this.field("Material", select("material", f._mats.map((m) => [m, m]), () => { f.tareTouched = false; this.applyCatalog(f); render(); }))),
          f._lines.length > 1 ? this.field("Product line", select("line", f._lines.map((l) => [l, l || "Standard"]), () => { this.applyCatalog(f); render(); })) : null,
          formatField(),
          this.field(`Color (${f._colors.length} available)`, h("div", { class: "row2" },
            select("color", [["", "Choose a color…"], ...f._colors.map((c) => [c.name, c.user ? `★ ${c.name}` : c.name])], () => { this.applyCatalog(f); render(); }), sw)),
          f._entry?.user ? h("div", { class: "row2" }, h("span", { class: "hint" }, "★ saved in your own catalog"),
            h("button", { "data-remove-from-catalog": "", onClick: async () => {
              try { await this._call({ type: "catalog_remove", vendor: f.vendor, material: f.material, line: f.line, name: f.color }); f.color = ""; this.applyCatalog(f); render(); } catch {} } },
            "Remove from my catalog")) : null,
          f._colors.length === 0 ? h("p", { class: "hint" }, "Nothing listed for this combination. Switch to “Custom” to enter it yourself.") : null,
          h("div", { class: "two" },
            this.field("Net weight when new, g", f._entry && f._entry.weights.length > 1 && !f.refill
              ? select("initial", f._entry.weights.map((w) => [w, `${w} g`]))
              : numIn("initial")),
            this.field("Empty spool weight, g", numIn("tare"), f.tareHint)),
          h("details", {}, h("summary", {}, "Pick a different color code"), h("div", { class: "row2" }, hex, h("span", { class: "hint" }, f.hex))));
      } else {
        const { hex, sw } = colorBlock();
        const dl = (id, items) => h("datalist", { id }, items.map((i) => h("option", { value: i })));
        const vendors = [...new Set([...(cat?.vendors || []).map((v) => v.name), ...this.s.spools.map((p) => p.vendor)])];
        const std = cat?.standard_colors || [];
        parts.push(
          h("div", { class: "two" },
            this.field("Vendor", combo("vendor", vendors, { blank: "Choose…", placeholder: "e.g. Prusament" })),
            this.field("Material", combo("material", cat?.materials || ["PLA", "PETG", "ABS", "ASA", "TPU"], { blank: "Choose…", placeholder: "e.g. PETG" }))),
          this.field("Product line (optional)", text("product", { placeholder: "e.g. Matte PETG" })),
          formatField(),
          this.field("Color name", h("div", { class: "row2" }, text("color", { list: "dl-c", placeholder: "e.g. Pistachio Green",
            after: () => { const m = std.find((c) => c.name.toLowerCase() === f.color.trim().toLowerCase()); if (m) { f.hex = m.hex; hex.value = m.hex; sw.style.background = m.hex; } } }), hex, sw)),
          dl("dl-c", std.map((c) => c.name)),
          std.length ? h("div", { class: "swatches", "aria-label": "Standard colors" }, std.map((c) => h("button", { title: c.name, "aria-label": c.name, style: { background: c.hex },
            onClick: () => { f.hex = c.hex; hex.value = c.hex; sw.style.background = c.hex; if (!f.color) { f.color = c.name; render(); } } }))) : null,
          h("div", { class: "two" }, this.field("Net weight when new, g", numIn("initial")), this.field("Empty spool weight, g", numIn("tare"))),
          edit ? null : h("label", { class: "row2" }, h("input", { type: "checkbox", "data-save-catalog": "", checked: f.saveCatalog,
            onChange: (e) => { f.saveCatalog = e.target.checked; } }), h("span", {}, "Save to my catalog (so it is in the dropdown next time)")));
      }

      if (edit) {
        parts.push(h("div", { class: "two" }, this.field("Remaining filament, g", numIn("remaining")), this.field("Diameter, mm", select("diameter", [["1.75", "1.75"], ["2.85", "2.85"]]))));
      } else {
        parts.push(
          this.field("Starting amount", select("start", [["full", "New, full spool"], ["remaining", "I know the filament left (g)"], ["gross", "I weighed it on a scale (spool + filament)"]], () => { render(); })),
          f.start === "full" ? null : this.field(f.start === "gross" ? "Scale reading, g" : "Filament left, g", numIn("startValue")),
          h("span", { class: "hint", "data-preview": "" }, ""));
      }
      const known = this.locations();
      parts.push(h("details", { open: !!(f._more ?? (f.price || f.location || f.notes || f.tag || f.loaded || f.reorder)) },
        h("summary", {}, "More fields (location, printer, reorder, price, notes, tag)"),
        h("div", { class: "grid" },
          edit ? null : this.field("Diameter, mm", select("diameter", [["1.75", "1.75"], ["2.85", "2.85"]])),
          this.field("Location", combo("location", known, { blank: "No location", placeholder: "e.g. Garage" })),
          h("label", { class: "row2" }, h("input", { type: "checkbox", "data-flag": "loaded", checked: f.loaded, onChange: (e) => { f.loaded = e.target.checked; } }), h("span", {}, "Loaded in the printer")),
          h("label", { class: "row2" }, h("input", { type: "checkbox", "data-flag": "reorder", checked: f.reorder, onChange: (e) => { f.reorder = e.target.checked; } }), h("span", {}, "Needs reordering")),
          this.field(`Price (${this.cur})`, numIn("price")), this.field("Notes", text("notes")), this.field("NFC tag ID", text("tag"), "Optional, for later NFC use"))));
      body.replaceChildren(...parts.filter(Boolean));
      preview();
    };

    const payload = () => {
      const m = {};
      const need = (v, label) => { if (!String(v).trim()) throw new Error(`${label} is required`); return String(v).trim(); };
      m.vendor = need(f.vendor, "Vendor"); m.material = need(f.material, "Material");
      if (!edit && f.mode === "catalog" && !f.color) throw new Error("Choose a color, or switch to “Custom”");
      const product = edit || f.mode === "custom" ? f.product.trim()
        : !f.line ? "" : f.line.toLowerCase().includes(f.material.toLowerCase()) ? f.line : `${f.line} ${f.material}`;
      m.product = product; m.color_name = String(f.color).trim(); m.color = f.hex;
      const d = num(f.diameter); if (d) m.diameter = d;
      const init = num(f.initial); if (init) m.initial_weight = init;
      const tare = num(f.tare); if (tare !== null) m.spool_weight = tare;
      if (num(f.price) !== null) m.price = num(f.price);
      m.location = f.location.trim(); m.notes = f.notes.trim(); m.tag_id = String(f.tag).trim();
      m.loaded = !!f.loaded; m.reorder = !!f.reorder; m.refill = hasRefill(f.vendor) && !!f.refill;
      if (edit) { const r = num(f.remaining); if (r !== null) m.remaining_weight = r; }
      else if (f.start !== "full") {
        const v = num(f.startValue); if (v === null) throw new Error(f.start === "gross" ? "Enter the scale reading" : "Enter the filament left");
        if (f.start === "gross") { if (tare === null) throw new Error("Enter the empty spool weight to use a scale reading"); m.gross_weight = v; } else m.remaining_weight = v;
      }
      return m;
    };
    const save = (again) => async (c) => {
      let m; try { m = payload(); } catch (err) { return this._toast(err.message, true); }
      try {
        if (edit) await this._call({ type: "update", spool_id: spool.id, ...m }); else await this._call({ type: "add", ...m });
        if (!edit && f.mode === "custom" && f.saveCatalog) await this._saveToCatalog(m);
        this._toast(edit ? "Spool updated" : `Added ${m.vendor} ${m.color_name}`.trim());
        if (again) { f.color = ""; f.startValue = ""; f.hex = "#808080"; if (f.mode === "catalog") this.applyCatalog(f); render(); } else c();
      } catch {}
    };
    render();
    close = this._modal(edit ? "Edit spool" : copyOf ? "Add another like this one" : "Add spool", body, [
      { label: "Cancel", run: (c) => c() },
      ...(edit ? [] : [{ label: "Save & add another", run: save(true) }]),
      { label: edit ? "Save" : "Add spool", primary: true, run: save(false) }]);
  }
}

customElements.define("spool-inventory-panel", SpoolInventoryPanel);
