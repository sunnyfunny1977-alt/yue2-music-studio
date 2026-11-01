"""Optik der App: dunkles „Studio“-Theme, CSS und HTML-Bausteine."""
import html

import gradio as gr

from i18n import STRINGS, t
from lyrics_tools import estimate_seconds, fmt_duration, lint, parse_sections
from yue_engine import PHASES

VIOLET, CYAN = "#8b5cf6", "#22d3ee"
GRADIENT = "linear-gradient(135deg, #7c3aed 0%, #4f46e5 45%, #06b6d4 100%)"
GRADIENT_HOVER = "linear-gradient(135deg, #8b5cf6 0%, #6366f1 45%, #22d3ee 100%)"
BACKDROP = ("radial-gradient(1100px 620px at 8% -12%, rgba(124,58,237,.30), transparent 62%), "
            "radial-gradient(900px 560px at 100% 0%, rgba(6,182,212,.20), transparent 60%), "
            "radial-gradient(800px 600px at 50% 120%, rgba(79,70,229,.18), transparent 60%), #07070d")

THEME = gr.themes.Base(
    primary_hue=gr.themes.colors.violet,
    secondary_hue=gr.themes.colors.cyan,
    neutral_hue=gr.themes.colors.slate,
    font=[gr.themes.GoogleFont("Inter"), "ui-sans-serif", "system-ui", "sans-serif"],
    font_mono=[gr.themes.GoogleFont("JetBrains Mono"), "ui-monospace", "Consolas", "monospace"],
    radius_size=gr.themes.sizes.radius_lg,
).set(
    body_background_fill=BACKDROP, body_background_fill_dark=BACKDROP,
    body_text_color="#e8e7f5", body_text_color_dark="#e8e7f5",
    body_text_color_subdued="#9b99bd", body_text_color_subdued_dark="#9b99bd",
    background_fill_primary="#0d0d18", background_fill_primary_dark="#0d0d18",
    background_fill_secondary="#12121f", background_fill_secondary_dark="#12121f",
    border_color_primary="rgba(255,255,255,0.09)", border_color_primary_dark="rgba(255,255,255,0.09)",
    border_color_accent=VIOLET, border_color_accent_dark=VIOLET,
    color_accent=VIOLET, color_accent_soft="rgba(139,92,246,0.18)", color_accent_soft_dark="rgba(139,92,246,0.18)",
    block_background_fill="transparent", block_background_fill_dark="transparent",
    block_border_width="0px", block_shadow="none", block_shadow_dark="none", block_padding="6px 2px",
    block_label_background_fill="transparent", block_label_background_fill_dark="transparent",
    block_label_text_color="#a9a6d6", block_label_text_color_dark="#a9a6d6", block_label_border_width="0px",
    block_title_text_color="#a9a6d6", block_title_text_color_dark="#a9a6d6", block_title_text_weight="600",
    panel_background_fill="transparent", panel_background_fill_dark="transparent",
    panel_border_color="rgba(255,255,255,0.08)", panel_border_color_dark="rgba(255,255,255,0.08)",
    input_background_fill="rgba(6,6,14,0.72)", input_background_fill_dark="rgba(6,6,14,0.72)",
    input_background_fill_focus="rgba(10,10,22,0.9)", input_background_fill_focus_dark="rgba(10,10,22,0.9)",
    input_border_color="rgba(255,255,255,0.10)", input_border_color_dark="rgba(255,255,255,0.10)",
    input_border_color_focus=VIOLET, input_border_color_focus_dark=VIOLET,
    input_shadow_focus="0 0 0 3px rgba(139,92,246,0.25)", input_shadow_focus_dark="0 0 0 3px rgba(139,92,246,0.25)",
    button_primary_background_fill=GRADIENT, button_primary_background_fill_dark=GRADIENT,
    button_primary_background_fill_hover=GRADIENT_HOVER, button_primary_background_fill_hover_dark=GRADIENT_HOVER,
    button_primary_text_color="#ffffff", button_primary_text_color_dark="#ffffff",
    button_primary_border_color="transparent", button_primary_border_color_dark="transparent",
    button_primary_shadow="0 8px 30px -8px rgba(124,58,237,0.65)",
    button_primary_shadow_hover="0 10px 38px -6px rgba(34,211,238,0.55)",
    button_secondary_background_fill="rgba(255,255,255,0.05)", button_secondary_background_fill_dark="rgba(255,255,255,0.05)",
    button_secondary_background_fill_hover="rgba(255,255,255,0.10)",
    button_secondary_background_fill_hover_dark="rgba(255,255,255,0.10)",
    button_secondary_border_color="rgba(255,255,255,0.10)", button_secondary_border_color_dark="rgba(255,255,255,0.10)",
    button_secondary_text_color="#e8e7f5", button_secondary_text_color_dark="#e8e7f5",
    button_cancel_background_fill="rgba(244,63,94,0.12)", button_cancel_background_fill_dark="rgba(244,63,94,0.12)",
    button_cancel_background_fill_hover="rgba(244,63,94,0.22)",
    button_cancel_background_fill_hover_dark="rgba(244,63,94,0.22)",
    button_cancel_text_color="#fda4af", button_cancel_text_color_dark="#fda4af",
    button_cancel_border_color="rgba(244,63,94,0.35)", button_cancel_border_color_dark="rgba(244,63,94,0.35)",
    button_large_radius="14px",
    slider_color=VIOLET, slider_color_dark=VIOLET,
    checkbox_background_color_selected=VIOLET, checkbox_background_color_selected_dark=VIOLET,
    checkbox_border_color_selected=VIOLET, checkbox_border_color_selected_dark=VIOLET,
    layout_gap="14px",
)

# Die App ist auf das dunkle Studio-Design ausgelegt – Dunkelmodus erzwingen.
FORCE_DARK_JS = """
() => {
  const url = new URL(window.location);
  if (url.searchParams.get('__theme') !== 'dark') {
    url.searchParams.set('__theme', 'dark');
    window.location.replace(url.href);
  }
}
"""

CSS = """
body { background-attachment: fixed !important; }
/* Scrollleiste immer einplanen: sonst ändert sich beim Wachsen/Schrumpfen der Seite die Breite aller Spalten
   und die Textfelder im Feinschliff brechen neu um. */
html { overflow-y: scroll; scrollbar-gutter: stable; }
.gradio-container { width: 100% !important; max-width: 1760px !important; margin: 0 auto !important; padding: 20px 22px 40px !important;
  box-sizing: border-box !important; }
footer { display: none !important; }

/* ---------- Kopfbereich ---------- */
.hero { display: flex; align-items: center; justify-content: space-between; gap: 24px; flex-wrap: wrap;
  padding: 22px 26px; border-radius: 24px; position: relative; overflow: hidden;
  background: linear-gradient(120deg, rgba(124,58,237,.22), rgba(6,182,212,.10) 60%, rgba(255,255,255,.02));
  border: 1px solid rgba(255,255,255,.09); box-shadow: 0 20px 60px -30px rgba(124,58,237,.6); }
.hero::after { content: ""; position: absolute; inset: -40% -10% auto auto; width: 420px; height: 420px;
  background: radial-gradient(circle, rgba(34,211,238,.18), transparent 65%); pointer-events: none; }
.hero-left { display: flex; align-items: center; gap: 18px; z-index: 1; flex: 1 1 380px; min-width: 0; }
.logo { display: block; width: 120px; height: 120px; flex: 0 0 auto; border-radius: 22%;
  box-shadow: 0 12px 34px -10px rgba(124,58,237,.85), 0 0 26px -12px rgba(34,211,238,.7); }
.hero h1 { margin: 0 !important; font-size: 30px !important; font-weight: 800 !important; letter-spacing: -.02em;
  line-height: 1.1 !important; color: #fff !important; }
.hero h1 span { background: linear-gradient(90deg, #c4b5fd, #67e8f9); -webkit-background-clip: text;
  background-clip: text; color: transparent; }
.hero p { margin: 6px 0 0 !important; color: #b9b7da !important; font-size: 14.5px !important; }
.chips { display: flex; gap: 8px; flex-wrap: wrap; z-index: 1; }
.chip { display: inline-flex; align-items: center; gap: 7px; padding: 7px 12px; border-radius: 999px; font-size: 12.5px;
  font-weight: 600; background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.10); color: #dcdaf2;
  white-space: nowrap; }
.chip .dot { width: 8px; height: 8px; border-radius: 50%; background: #94a3b8; }
.chip.ok .dot { background: #34d399; box-shadow: 0 0 10px #34d399; }
.chip.warn .dot { background: #fbbf24; box-shadow: 0 0 10px #fbbf24; }
.chip.err .dot { background: #fb7185; box-shadow: 0 0 10px #fb7185; }
.chip.accent { background: rgba(139,92,246,.16); border-color: rgba(139,92,246,.35); color: #ddd6fe; }

/* ---------- Karten & Schritte ---------- */
/* Kein backdrop-filter auf Karten: er macht die Karte zum Bezugsrahmen für position:fixed und
   verschiebt dadurch Gradios Dropdown-Listen nach unten. Stattdessen ein deckenderer Hintergrund. */
.card { background: linear-gradient(180deg, rgba(20,20,36,.86), rgba(14,14,26,.86)) !important;
  border: 1px solid rgba(255,255,255,.08) !important;
  border-radius: 20px !important; padding: 16px 18px 18px !important;
  box-shadow: 0 24px 60px -36px rgba(0,0,0,.9); }
.card .form, .card .gr-form { background: transparent !important; border: none !important; box-shadow: none !important;
  gap: 10px !important; }
.card .block { background: transparent !important; }
#main-row { gap: 16px !important; }
#main-row > .column { gap: 16px !important; }
/* Feste Spaltenanteile (4 : 5 : 4) per Grid: minmax(0, …) verhindert, dass Inhalte – z. B. die sich ständig
   ändernde Fortschrittsanzeige – eine Spalte verbreitern und die anderen zusammendrücken. */
@media (min-width: 1100px) {
  #main-row { display: grid !important; grid-template-columns: minmax(0, 4fr) minmax(0, 5fr) minmax(0, 4fr);
    align-items: start; }
  #main-row > .column { min-width: 0 !important; width: auto !important; }
}
.card .block:has(> .label-wrap) { overflow: visible !important; }
.step { display: flex; align-items: center; gap: 12px; margin-bottom: 2px; }
.step-num { font-family: var(--font-mono); font-size: 12px; font-weight: 700; color: #fff; width: 32px; height: 32px;
  border-radius: 10px; display: flex; align-items: center; justify-content: center; background: """ + GRADIENT + """;
  box-shadow: 0 6px 20px -6px rgba(124,58,237,.8); flex-shrink: 0; }
.step-title { font-size: 16.5px; font-weight: 750; color: #fff; letter-spacing: -.01em; }
.step-sub { font-size: 12.5px; color: #9b99bd; margin-top: 1px; }
.card [data-testid="block-info"] { font-size: 11px !important; font-weight: 650 !important;
  letter-spacing: .07em; text-transform: uppercase; color: #a9a6d6 !important; }
.card textarea, .card input[type=text], .card input[type=number] { font-size: 14px !important; }
#lyrics-box textarea { font-family: var(--font-mono) !important; font-size: 13px !important; line-height: 1.6 !important; }
#style-box textarea, #concept-box textarea { font-size: 13.5px !important; line-height: 1.5 !important; }
#idea-box textarea { font-size: 15px !important; line-height: 1.55 !important; }
/* Checkboxen ohne Rahmen-Block: Denkmodus, Zufalls-Seed, Überschreiben */
#think-cb { padding: 0 2px !important; }
.card label:has(> input[type=checkbox]) { font-size: 13px !important; }

/* ---------- Segment-Schalter (Modus, Format) ---------- */
.seg .wrap { display: grid !important; grid-auto-flow: column; grid-auto-columns: 1fr; gap: 4px !important;
  background: rgba(0,0,0,.35); padding: 4px; border-radius: 14px; border: 1px solid rgba(255,255,255,.08); }
.seg label { justify-content: center !important; border-radius: 10px !important; padding: 8px 12px !important;
  font-size: 13.5px !important;
  background: transparent !important; border: 1px solid transparent !important; box-shadow: none !important;
  font-weight: 650 !important; color: #b9b7da !important; cursor: pointer; transition: all .18s ease; }
.seg label:hover { background: rgba(255,255,255,.05) !important; color: #fff !important; }
.seg label.selected { background: """ + GRADIENT + """ !important; color: #fff !important;
  box-shadow: 0 8px 24px -10px rgba(124,58,237,.9) !important; }
.seg input[type=radio] { display: none !important; }
#mode-switch label { font-size: 14px !important; padding: 9px 12px !important; }
.seg-sm label { padding: 6px 10px !important; font-size: 13px !important; }

/* ---------- Buttons ---------- */
#gen-btn { min-height: 48px; font-size: 15.5px !important; font-weight: 750 !important; letter-spacing: .01em;
  background-size: 200% 200% !important; animation: shine 6s ease infinite; }
@keyframes shine { 0%,100% { background-position: 0% 50% } 50% { background-position: 100% 50% } }
.create-btn { min-height: 42px; font-size: 14.5px !important; font-weight: 700 !important; }
.ghost-btn { font-weight: 600 !important; }
.card button.sm { font-size: 13px !important; padding: 7px 10px !important; min-height: 34px; white-space: nowrap; }
.model-row { align-items: flex-end !important; }
.correct-row { align-items: flex-end !important; }
.correct-row button { min-height: 40px; white-space: nowrap; }
/* Lange Ollama-Modellnamen nicht mehrfach umbrechen: Liste und Einträge breiter als das Feld */
#model-dd ul.options { min-width: 380px !important; }
#model-dd ul.options li { width: auto !important; }
.icon-btn { min-width: 40px !important; max-width: 40px !important; min-height: 40px; font-size: 16px !important; }

/* ---------- Fortschritt ---------- */
.prog { padding: 13px 15px; border-radius: 16px; background: rgba(0,0,0,.30); border: 1px solid rgba(255,255,255,.08); }
.prog-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 10px; }
.prog-stage { font-weight: 700; color: #fff; font-size: 15px; }
.prog-pct { font-family: var(--font-mono); font-weight: 700; color: #c4b5fd; font-size: 15px; }
.prog-bar { height: 10px; border-radius: 999px; background: rgba(255,255,255,.07); overflow: hidden; }
.prog-fill { height: 100%; border-radius: 999px; background: linear-gradient(90deg, #7c3aed, #6366f1, #22d3ee, #7c3aed);
  background-size: 300% 100%; animation: flow 2.2s linear infinite; transition: width .8s ease;
  box-shadow: 0 0 18px rgba(139,92,246,.7); }
@keyframes flow { from { background-position: 0% 0 } to { background-position: 300% 0 } }
.prog-steps { display: flex; gap: 5px; margin: 12px 0 10px; flex-wrap: nowrap; }
.ps { flex: 1 1 0; text-align: center; font-size: 11px; font-weight: 650; padding: 6px 3px; border-radius: 9px;
  color: #77759a; background: rgba(255,255,255,.03); border: 1px solid rgba(255,255,255,.05); min-width: 0;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ps.done { color: #a7f3d0; background: rgba(52,211,153,.10); border-color: rgba(52,211,153,.25); }
.ps.active { color: #fff; background: rgba(139,92,246,.22); border-color: rgba(139,92,246,.55);
  animation: pulse 1.6s ease-in-out infinite; }
@keyframes pulse { 0%,100% { box-shadow: 0 0 0 0 rgba(139,92,246,.0) } 50% { box-shadow: 0 0 0 4px rgba(139,92,246,.18) } }
.prog.idle { display: flex; gap: 14px; align-items: center; color: #9b99bd; font-size: 14px; }
/* Feste Mindesthöhen: Bereit → Fortschritt → Ergebnis und leerer → geladener Player springen nicht mehr */
#gen-status { min-height: 158px; }
#gen-status { contain: inline-size; min-width: 0; max-width: 100%; overflow: hidden; }
#player { contain: inline-size; min-width: 0; max-width: 100%; }
#gen-status .prog, #gen-status .result { min-height: 158px; box-sizing: border-box; }
#gen-status .prog.idle { justify-content: center; }
#gen-status .prog .chips { flex-wrap: nowrap; overflow: hidden; }
#gen-status .prog-stage { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
#gen-status .prog-head { gap: 10px; }
#gen-status .prog-pct { flex-shrink: 0; white-space: nowrap; }
#gen-status .result-head > div:last-child { min-width: 0; }
#gen-status .result-title, #gen-status .result-sub { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
#player { min-height: 180px; }
.prog.idle .big { font-size: 26px; }

/* ---------- Ergebnis & Hinweise ---------- */
.result { padding: 14px; border-radius: 16px; border: 1px solid rgba(52,211,153,.28);
  background: linear-gradient(135deg, rgba(52,211,153,.10), rgba(34,211,238,.06)); }
.result-head { display: flex; gap: 14px; align-items: center; margin-bottom: 12px; }
.result-icon { width: 40px; height: 40px; border-radius: 12px; display: flex; align-items: center; justify-content: center;
  font-size: 22px; background: """ + GRADIENT + """; color: #fff; flex-shrink: 0; }
.result-title { font-size: 16.5px; font-weight: 750; color: #fff; }
.result-sub { font-size: 13px; color: #a7f3d0; }
.notice { padding: 10px 14px; border-radius: 12px; font-size: 13.5px; line-height: 1.5; border: 1px solid; }
.notice b { display: block; margin-bottom: 2px; }
.notice.ok { background: rgba(52,211,153,.09); border-color: rgba(52,211,153,.28); color: #bbf7d0; }
.notice.info { background: rgba(139,92,246,.10); border-color: rgba(139,92,246,.30); color: #ddd6fe; }
.notice.warn { background: rgba(251,191,36,.09); border-color: rgba(251,191,36,.30); color: #fde68a; }
.notice.err { background: rgba(244,63,94,.10); border-color: rgba(244,63,94,.32); color: #fecdd3; }
.notice code { font-family: var(--font-mono); font-size: 12.5px; background: rgba(0,0,0,.3); padding: 2px 6px;
  border-radius: 6px; word-break: break-all; }
.lint { display: flex; flex-direction: column; gap: 8px; }
.lint-row { display: flex; gap: 8px; flex-wrap: wrap; }
.lint-item { display: flex; gap: 10px; align-items: flex-start; font-size: 13px; padding: 7px 11px; border-radius: 10px; }
.lint-item.err { background: rgba(244,63,94,.10); color: #fecdd3; border: 1px solid rgba(244,63,94,.25); }
.lint-item.warn { background: rgba(251,191,36,.08); color: #fde68a; border: 1px solid rgba(251,191,36,.22); }
.lint-item.ok { background: rgba(52,211,153,.08); color: #bbf7d0; border: 1px solid rgba(52,211,153,.22); }
.block.html-slot, .block.html-slot > .html-container { padding: 0 !important; }
.html-slot .pending, .html-slot.pending, .prose.pending { opacity: 1 !important; }

/* ---------- Diverses ---------- */
.card .label-wrap { font-weight: 650; }
.card audio, .card .waveform-container { border-radius: 14px; }
.card ::part(scroll) { scrollbar-width: none !important; }  /* WaveSurfer (Shadow-DOM) ohne Scrollleiste */
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-thumb { background: rgba(139,92,246,.35); border-radius: 10px; }
::-webkit-scrollbar-track { background: transparent; }
/* ---------- Live-Systemanzeige im Kopfbereich ---------- */
.sysmon { z-index: 1; display: grid; gap: 7px; width: 400px; max-width: 100%; margin-right: 128px;
  padding: 12px 16px; border-radius: 16px; background: rgba(0,0,0,.28); border: 1px solid rgba(255,255,255,.08); }
.mon-row { display: grid; grid-template-columns: 70px 1fr 112px; align-items: center; gap: 10px; }
.mon-label { font-size: 11.5px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: #a9a6d6; }
.mon-bar { height: 8px; border-radius: 999px; background: rgba(255,255,255,.08); overflow: hidden; }
.mon-fill { height: 100%; width: 0%; border-radius: 999px; transition: width .9s ease, background .6s ease;
  background: linear-gradient(90deg, #7c3aed, #22d3ee); box-shadow: 0 0 12px rgba(139,92,246,.55); }
.mon-row.warn .mon-fill { background: linear-gradient(90deg, #f59e0b, #fbbf24); box-shadow: 0 0 12px rgba(251,191,36,.5); }
.mon-row.high .mon-fill { background: linear-gradient(90deg, #f43f5e, #fb7185); box-shadow: 0 0 12px rgba(244,63,94,.55); }
.mon-row.na .mon-bar { opacity: .35; }
.mon-value { font-family: var(--font-mono); font-size: 12px; color: #e8e7f5; text-align: right; white-space: nowrap; }
@media (max-width: 1250px) { .sysmon { margin-right: 0; width: 100%; } }
#sysmon-data { display: none !important; }

/* ---------- Reiter Studio | Bibliothek ---------- */
#main-tabs { margin-top: 4px; }
#main-tabs > .tab-wrapper, #main-tabs .tab-container { gap: 6px; }
#main-tabs button[role="tab"] { font-size: 14.5px !important; font-weight: 700 !important; padding: 9px 18px !important;
  border-radius: 12px 12px 0 0 !important; color: #b9b7da !important; }
#main-tabs button[role="tab"].selected { color: #fff !important; background: rgba(139,92,246,.18) !important; }
#main-tabs > div[role="tabpanel"], #main-tabs .tabitem { padding: 14px 0 0 !important; border: none !important;
  background: transparent !important; }

/* ---------- Bibliothek ---------- */
#lib-row { gap: 16px !important; align-items: start; }
@media (min-width: 1100px) {
  #lib-row { display: grid !important; grid-template-columns: minmax(0, 7fr) minmax(0, 5fr); }
  #lib-row > .column { min-width: 0 !important; width: auto !important; }
}
.lib-tools { align-items: flex-end !important; }
.lib-count { font-size: 12.5px; color: #9b99bd; padding: 0 4px 2px; }
#lib-gallery { min-height: 420px; }
#lib-gallery .thumbnail-item, #lib-gallery button.thumbnail-item { border-radius: 14px !important; overflow: hidden; }
#lib-gallery .caption-label { font-size: 11.5px !important; font-weight: 650 !important; white-space: pre-line !important;
  line-height: 1.35 !important; overflow: hidden; max-width: 100%; display: -webkit-box; -webkit-line-clamp: 2;
  -webkit-box-orient: vertical; text-overflow: ellipsis; }
#lib-gallery .caption-label::first-line { color: #fff; font-weight: 750; }
#lib-cover { max-width: 300px; margin: 0 auto; }
#lib-cover img { border-radius: 16px; box-shadow: 0 18px 40px -18px rgba(0,0,0,.9); }
.lib-head { display: flex; flex-direction: column; gap: 6px; }
.lib-title { font-size: 20px; font-weight: 800; color: #fff; letter-spacing: -.01em; }
.lib-files { font-size: 12px; color: #9b99bd; font-family: var(--font-mono); word-break: break-all; }
.lib-pick { padding: 40px 10px; text-align: center; color: #9b99bd; font-size: 14px; }
.cover-prog { padding: 12px 14px; border-radius: 14px; background: rgba(0,0,0,.30); border: 1px solid rgba(255,255,255,.08);
  margin-top: 8px; }
.cover-prog .prog-head { display: flex; justify-content: space-between; margin-bottom: 8px; gap: 10px; }
#lib-player { min-height: 150px; }
.reuse-row button { white-space: nowrap; }

/* ---------- Mashup ---------- */
.mash-songs { gap: 16px !important; }
.song-a .step-num { background: linear-gradient(135deg, #7c3aed, #a78bfa) !important; }
.song-b .step-num { background: linear-gradient(135deg, #0891b2, #22d3ee) !important; }
.song-a.card { border-color: rgba(167,139,250,.35) !important; }
.song-b.card { border-color: rgba(34,211,238,.35) !important; }
.timeline { display: flex; flex-direction: column; gap: 8px; }
.tl-bar { display: flex; gap: 3px; height: 34px; border-radius: 12px; overflow: hidden; }
.tl-seg { display: flex; align-items: center; justify-content: center; min-width: 18px; overflow: hidden;
  font-size: 11px; font-weight: 700; color: #fff; white-space: nowrap; text-overflow: ellipsis; }
.tl-seg span { overflow: hidden; text-overflow: ellipsis; padding: 0 4px; }
.tl-seg.a { background: linear-gradient(180deg, #8b5cf6, #6d28d9); }
.tl-seg.b { background: linear-gradient(180deg, #22d3ee, #0e7490); }
.tl-legend { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; font-size: 12.5px; color: #c9c7e6; }
.tl-dot { width: 10px; height: 10px; border-radius: 3px; display: inline-block; margin-left: 10px; }
.tl-dot.a { background: #8b5cf6; } .tl-dot.b { background: #22d3ee; }
.mash-slot { border-radius: 16px !important; padding: 10px 12px !important; gap: 6px !important;
  background: rgba(0,0,0,.22) !important; border: 1px solid rgba(255,255,255,.08) !important;
  border-left: 4px solid #8b5cf6 !important; }
.mash-slot:has(.slot-head.b) { border-left-color: #22d3ee !important; background: rgba(34,211,238,.05) !important; }
.mash-slot:has(.slot-head.a) { background: rgba(139,92,246,.06) !important; }
.slot-row { align-items: center !important; gap: 10px !important; }
.slot-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.slot-num { font-family: var(--font-mono); font-size: 11px; font-weight: 700; color: #9b99bd; }
.slot-tag { font-weight: 750; color: #fff; font-size: 14.5px; }
.slot-src { font-size: 12px; font-weight: 650; padding: 3px 9px; border-radius: 999px; }
.slot-head.a .slot-src { background: rgba(139,92,246,.22); color: #ddd6fe; }
.slot-head.b .slot-src { background: rgba(34,211,238,.18); color: #a5f3fc; }
.slot-note { font-size: 11.5px; color: #9b99bd; }
.slot-stale { font-size: 11.5px; color: #fde68a; background: rgba(251,191,36,.12); padding: 2px 8px; border-radius: 999px; }
.slot-ab label { padding: 4px 14px !important; font-size: 12.5px !important; }
.slot-ab label:first-child.selected { background: linear-gradient(135deg, #7c3aed, #a78bfa) !important; }
.slot-ab label:last-child.selected { background: linear-gradient(135deg, #0891b2, #22d3ee) !important; }
.slot-text textarea { font-family: var(--font-mono) !important; font-size: 13px !important; line-height: 1.55 !important; }
.abc-staff { width: 100%; overflow-x: auto; padding: 4px 2px 0; }
.task-prog .prog-steps { flex-wrap: nowrap; }
.task-prog .ps { flex: 1 1 0; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.abc-staff svg { max-width: 100%; height: auto; display: block; }

/* ---------- Song-Info (Remake) ---------- */
.track { display: flex; gap: 16px; align-items: center; padding: 14px; border-radius: 18px;
  background: linear-gradient(135deg, rgba(124,58,237,.14), rgba(6,182,212,.07));
  border: 1px solid rgba(139,92,246,.28); }
.track-cover { width: 96px; height: 96px; border-radius: 14px; object-fit: cover; flex-shrink: 0;
  box-shadow: 0 10px 28px -10px rgba(0,0,0,.8); }
.track-cover.placeholder { display: flex; align-items: center; justify-content: center; font-size: 40px; color: #fff;
  background: """ + GRADIENT + """; }
.track-body { min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.track-title { font-size: 18px; font-weight: 750; color: #fff; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.track-artist { font-size: 14.5px; color: #c4b5fd; font-weight: 600; margin-bottom: 4px; }
.track-tech { font-size: 12.5px; color: #9b99bd; margin-top: 4px; font-family: var(--font-mono); }
.track-hint { font-size: 12.5px; color: #fde68a; margin-top: 2px; }
.lyr-hint { font-size: 12.5px; color: #9b99bd; line-height: 1.5; }
.lyr-hint a { color: #c4b5fd; }
#lyr-dd ul.options, #lyr-dd-a ul.options, #lyr-dd-b ul.options { min-width: 420px !important; }
#lyr-dd ul.options li, #lyr-dd-a ul.options li, #lyr-dd-b ul.options li { width: auto !important; }

/* ---------- Sprachumschalter & Startdialog ---------- */
.hero-chips { margin-top: 12px; }
#top-row { position: relative; }
#lang-switch { position: absolute !important; top: 18px; right: 22px; z-index: 20; width: auto !important;
  min-width: 0 !important; flex: none !important; }
#lang-switch .wrap { padding: 4px !important; gap: 4px !important; border-radius: 12px !important; }
#lang-switch label { padding: 7px 14px !important; font-size: 13px !important; border-radius: 9px !important; }
#lang-modal { position: fixed !important; inset: 0; z-index: 1000; background: rgba(4,4,10,.74);
  backdrop-filter: blur(10px); justify-content: center; align-items: center; padding: 20px; margin: 0 !important; }
#lang-modal .modal-card { width: 100%; max-width: 500px; flex-grow: 0 !important; text-align: center;
  background: rgba(16,16,30,.96) !important; border: 1px solid rgba(255,255,255,.10) !important; border-radius: 26px !important;
  padding: 30px 28px 28px !important; box-shadow: 0 30px 90px -20px rgba(124,58,237,.55); }
.modal-head .logo { width: 136px; height: 136px; margin: 0 auto 16px; }
.modal-head h2 { margin: 0 !important; font-size: 24px !important; font-weight: 800 !important; color: #fff !important; }
.modal-head p { margin: 6px 0 10px !important; color: #b9b7da !important; }
.modal-head .modal-en { margin-top: 14px !important; font-size: 19px !important; color: #c4b5fd !important; }
.lang-btn { min-height: 62px; font-size: 17px !important; font-weight: 700 !important; }
@media (max-width: 900px) { #lang-switch { position: static !important; margin: 8px 0 0 auto; } }
@media (max-width: 900px) { .gradio-container { padding: 14px !important; } .hero h1 { font-size: 24px !important; }
  .hero .logo { width: 76px; height: 76px; } }
"""

WAVEFORM = gr.WaveformOptions(waveform_color="#4b4a6e", waveform_progress_color=VIOLET,
                              show_recording_waveform=True, trim_region_color="rgba(34,211,238,0.25)",
                              sample_rate=48000)


def esc(text):
    return html.escape(str(text if text is not None else ""))


def chip(text, kind=""):
    dot = '<span class="dot"></span>' if kind in {"ok", "warn", "err"} else ""
    return f'<span class="chip {kind}">{dot}{esc(text)}</span>'


MONITOR_ROWS = ("vram", "gpu", "power", "cpu", "ram")


def sysmon_html():
    """Gerüst der Live-Anzeige; die Werte setzt window.yue2Sysmon (siehe SYSMON_JS) alle 2 Sekunden."""
    rows = "".join(
        f'<div class="mon-row" id="mon-{key}"><span class="mon-label">{esc(t("mon." + key))}</span>'
        f'<div class="mon-bar"><div class="mon-fill"></div></div><span class="mon-value">–</span></div>'
        for key in MONITOR_ROWS)
    return f'<div class="sysmon">{rows}</div>'


LOGO_URL = "/gradio_api/file=static/logo.png"


def hero(ollama_ok, ollama_text, gpu_text, gpu_ok=True, low_vram=False, cover_text="", cover_ok=False):
    lowvram_chip = chip(t("chip.lowvram"), "warn") if low_vram else ""
    cover_chip = chip(cover_text, "ok" if cover_ok else "") if cover_text else ""
    return f"""
<div class="hero">
  <div class="hero-left">
    <img class="logo" src="{LOGO_URL}" alt="YuE2 Music Studio">
    <div><h1>YuE2 <span>Music Studio</span></h1>
      <p>{t("hero.sub")}</p>
      <div class="chips hero-chips">
        {chip(ollama_text, "ok" if ollama_ok else "err")}
        {chip(gpu_text, "ok" if gpu_ok else "warn")}
        {lowvram_chip}
        {chip(t("chip.yue"), "accent")}
        {cover_chip}
      </div></div>
  </div>
  {sysmon_html()}
</div>"""


def track_head(track):
    """Kopf der Detailkarte in der Bibliothek: Titel und Chips (Länge, Modus, Sprache, BPM, Datum, Cover)."""
    info = track.info
    chips = []
    if track.seconds:
        chips.append(chip(f"⏱ {fmt_duration(track.seconds)} min"))
    chips.append(chip(t({"remake": "lib.chip_remake", "mashup": "lib.chip_mashup"}.get(info.get("mode"), "lib.chip_new")),
                      "accent"))
    if info.get("language"):
        chips.append(chip(f"🌐 {info['language']}"))
    if track.genre():
        chips.append(chip(f"🎸 {track.genre()}"))
    if track.bpm():
        chips.append(chip(f"🥁 {track.bpm()} BPM"))
    if track.created.year > 1900:
        chips.append(chip(f"📅 {track.created:%d.%m.%Y %H:%M}"))
    if track.jpg:
        chips.append(chip(t("lib.chip_cover"), "ok"))
    files = " · ".join(f"{ext[1:].upper()}" for ext in sorted(track.audio))
    return (f'<div class="lib-head"><div class="lib-title">{esc(track.title)}</div>'
            f'<div class="lib-files">{esc(files)} · {esc(str(track.folder))}</div>'
            f'<div class="chips">{"".join(chips)}</div></div>')


def step(num, title_key, sub_key=""):
    sub = t(sub_key) if sub_key else ""
    return (f'<div class="step"><div class="step-num">{num:02d}</div><div>'
            f'<div class="step-title">{esc(t(title_key))}</div><div class="step-sub">{esc(sub)}</div></div></div>')


def modal_html():
    """Startdialog – bewusst zweisprachig, da noch keine Sprache gewählt ist."""
    de_title, en_title = STRINGS["modal.title"]
    de_sub, en_sub = STRINGS["modal.sub"]
    return f"""
<div class="modal-head">
  <img class="logo" src="{LOGO_URL}" alt="YuE2 Music Studio">
  <h2>{esc(de_title)}</h2>
  <p>{esc(de_sub)}</p>
  <h2 class="modal-en">{esc(en_title)}</h2>
  <p>{esc(en_sub)}</p>
</div>"""


def notice(kind, title, body=""):
    body_html = f"<span>{body}</span>" if body else ""
    return f'<div class="notice {kind}"><b>{esc(title)}</b>{body_html}</div>'


def idle_html():
    return f'<div class="prog idle"><span class="big">🎛️</span><span>{t("idle")}</span></div>'


def progress_html(p):
    keys = [k for k, *_ in PHASES]
    current = keys.index(p.key) if p.key in keys else (len(keys) if p.key == "done" else 0)
    steps = []
    for i, key in enumerate(keys):
        cls = "done" if i < current else "active" if i == current else ""
        steps.append(f'<span class="ps {cls}" title="{esc(t("phase." + key))}">{esc(t("phase." + key))}</span>')
    meta = []
    if p.abc_tokens:
        meta.append(chip(t("prog.score", n=p.abc_tokens)))
    if p.semantic_tokens:
        meta.append(chip(t("prog.music", s=f"{p.semantic_tokens / 25:.0f}")))
    meta.append(chip(f"⏱ {fmt_duration(p.elapsed)}"))
    pct = max(2.0, p.percent)
    return f"""
<div class="prog">
  <div class="prog-head"><span class="prog-stage">{esc(t("stage." + p.stage))} …</span><span class="prog-pct">{p.percent:.0f} %</span></div>
  <div class="prog-bar"><div class="prog-fill" style="width:{pct:.1f}%"></div></div>
  <div class="prog-steps">{''.join(steps)}</div>
  <div class="chips">{''.join(meta)}</div>
</div>"""


def result_html(title, meta, seed):
    chips = [chip(f"⏱ {fmt_duration(meta['duration'])} min"), chip(f"🎲 Seed {seed}"),
             chip(t("result.render", s=f"{meta['gen_seconds']:.0f}")), chip(f"🧠 cot = {meta['cot']}")]
    truncated = [t("trunc." + k) for k, v in meta["truncated"].items() if v]
    warn = ""
    if truncated:
        warn = ('<div style="margin-top:12px">'
                + notice("warn", t("result.trunc_t"), esc(t("result.trunc_b", parts=", ".join(truncated)))) + "</div>")
    return f"""
<div class="result">
  <div class="result-head"><div class="result-icon">♪</div>
    <div><div class="result-title">{esc(title or t('result.untitled'))}</div>
    <div class="result-sub">{t("result.sub")}</div></div></div>
  <div class="chips">{''.join(chips)}</div>{warn}
</div>"""


def track_card(info, file_name=""):
    """Karte mit Cover, Titel, Interpret und Tags des geladenen Original-Songs (Remake)."""
    if not info and not file_name:
        return ""
    info = info or {}
    title = info.get("title") or file_name or "?"
    artist = info.get("artist") or info.get("album_artist") or t("track.unknown_artist")
    cover = info.get("cover")
    art = (f'<img class="track-cover" src="{cover}" alt="">' if cover
           else '<div class="track-cover placeholder">♪</div>')
    tags = [chip(f"{t('track.' + key)}: {info[key]}") for key in ("album", "year", "genre", "track", "composer")
            if info.get(key)]
    tech = [info.get("codec", "")]
    if info.get("bitrate_kbps"):
        tech.append(f"{info['bitrate_kbps']} kbit/s")
    if info.get("sample_rate"):
        tech.append(f"{info['sample_rate'] / 1000:g} kHz")
    if info.get("channels"):
        tech.append(t("track.stereo") if info["channels"] == 2 else t("track.mono") if info["channels"] == 1
                    else f"{info['channels']} ch")
    if info.get("duration"):
        tech.append(f"{fmt_duration(info['duration'])} min")
    has_tags = any(info.get(k) for k in ("title", "artist", "album"))
    hint = "" if has_tags else f'<div class="track-hint">{esc(t("track.no_tags"))}</div>'
    return f"""
<div class="track">
  {art}
  <div class="track-body">
    <div class="track-title">{esc(title)}</div>
    <div class="track-artist">{esc(artist)}</div>
    <div class="chips">{''.join(tags)}</div>
    <div class="track-tech">{esc(' · '.join(x for x in tech if x))}</div>
    {hint}
  </div>
</div>"""


def lint_html(style, lyrics):
    if not (style or lyrics):
        return ""
    errors, warnings = lint(style, lyrics)
    sections = parse_sections(lyrics or "")
    lines = sum(len(l) for _, l in sections)
    duration = fmt_duration(estimate_seconds(lyrics or "", style))
    head = (f'<div class="lint-row">{chip(t("lint.duration", d=duration), "accent")}'
            f'{chip(t("lint.sections", n=len(sections)))}{chip(t("lint.lines", n=lines))}</div>')
    items = [f'<div class="lint-item err">❌ <span>{esc(e)}</span></div>' for e in errors]
    items += [f'<div class="lint-item warn">⚠️ <span>{esc(w)}</span></div>' for w in warnings]
    if not items:
        items = [f'<div class="lint-item ok">✅ <span>{esc(t("lint.ok"))}</span></div>']
    return f'<div class="lint">{head}{"".join(items)}</div>'


SYSMON_JS = """<script>
window.yue2Sysmon = function (raw) {
  let d;
  try { d = typeof raw === 'string' ? JSON.parse(raw) : raw; } catch (e) { return; }
  if (!d) return;
  const lang = navigator.language || 'de';
  const num = (v, digits) => v.toLocaleString(lang, { minimumFractionDigits: digits, maximumFractionDigits: digits });
  const set = (key, used, total, text) => {
    const row = document.getElementById('mon-' + key);
    if (!row) return;
    const fill = row.querySelector('.mon-fill'), value = row.querySelector('.mon-value');
    if (used === null || used === undefined || !total) {
      row.classList.add('na'); fill.style.width = '0%'; value.textContent = '–'; return;
    }
    const pct = Math.max(0, Math.min(100, used / total * 100));
    row.classList.remove('na');
    row.classList.toggle('warn', pct >= 85 && pct < 95);
    row.classList.toggle('high', pct >= 95);
    fill.style.width = pct.toFixed(1) + '%';
    value.textContent = text;
  };
  set('vram', d.vram_used, d.vram_total,
      d.vram_total ? num(d.vram_used, 1) + ' / ' + num(d.vram_total, 0) + ' GB' : '');
  set('gpu', d.gpu_util, 100, d.gpu_util === null ? '' : num(d.gpu_util, 0) + ' %');
  set('power', d.power, d.power_limit,
      d.power === null ? '' : num(d.power, 0) + ' / ' + num(d.power_limit, 0) + ' W');
  set('cpu', d.cpu, 100, num(d.cpu, 0) + ' %');
  set('ram', d.ram_used, d.ram_total, num(d.ram_used, 1) + ' / ' + num(d.ram_total, 0) + ' GB');
};
/* Der Timer in app.py schreibt die Werte alle 2 s in #sysmon-data - hier jede Sekunde auf Aenderungen pruefen.
   Nur Block-Kommentare verwenden: Gradio fuegt den Kopf-Code teils ohne Zeilenumbrueche ein. */
(function () {
  let last = null;
  setInterval(function () {
    const box = document.querySelector('#sysmon-data textarea, #sysmon-data input');
    if (box && box.value && box.value !== last) { last = box.value; window.yue2Sysmon(box.value); }
  }, 1000);
})();
</script>"""


MASH_COLORS = {"A": "#a78bfa", "B": "#22d3ee"}

# Noten (abcjs, lokal unter static/): rendert alle .abc-staff[data-abc] und wiederholt das bei Änderungen.
# Nur Blockkommentare – Gradio fügt den Kopf u. U. ohne Zeilenumbrüche ein.
STAFF_JS = """<script src="/gradio_api/file=static/abcjs-basic-min.js"></script>
<script>
(function () {
  function render() {
    if (!window.ABCJS) { return; }
    document.querySelectorAll('.abc-staff[data-abc]').forEach(function (el) {
      var abc = el.getAttribute('data-abc');
      var color = el.getAttribute('data-color') || '#e8e7f5';
      if (el.__abc === abc + color) { return; }
      el.__abc = abc + color;
      /* Breite Notenzeile (1800) mit Umbruch nach ~10 Takten, per responsive auf die Kartenbreite skaliert –
         einheitliche Größe, auch wenn der Teil beim Rendern noch ausgeblendet ist. */
      try {
        ABCJS.renderAbc(el, abc, { responsive: 'resize', foregroundColor: color, paddingtop: 6, paddingbottom: 10,
          paddingleft: 0, paddingright: 6, staffwidth: 1800,
          wrap: { minSpacing: 1.5, maxSpacing: 2.6, preferredMeasuresPerLine: 10 }, add_classes: false });
      } catch (e) { el.textContent = ''; }
    });
  }
  var timer = null;
  function schedule() { if (timer) { return; } timer = setTimeout(function () { timer = null; render(); }, 150); }
  function start() {
    new MutationObserver(schedule).observe(document.body, { childList: true, subtree: true, attributes: true,
      attributeFilter: ['data-abc', 'data-color'] });
    schedule();
  }
  if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', start); } else { start(); }
})();
</script>"""


def task_progress_html(title, steps, current, pct, elapsed, detail=""):
    """Fortschritt einer mehrstufigen Aufgabe (z. B. Mashup-Analyse) im Stil der Generierungsanzeige.

    steps: Beschriftungen der Schritte; current: Index des laufenden Schritts (len(steps) = fertig)."""
    pills = []
    for i, label in enumerate(steps):
        cls = "done" if i < current else "active" if i == current else ""
        pills.append(f'<span class="ps {cls}" title="{esc(label)}">{esc(label)}</span>')
    pct = max(2.0, min(99.0, pct))
    detail_html = f'<span class="chip">{esc(detail)}</span>' if detail else ""
    return f"""
<div class="prog task-prog">
  <div class="prog-head"><span class="prog-stage">{esc(title)} …</span><span class="prog-pct">{pct:.0f} %</span></div>
  <div class="prog-bar"><div class="prog-fill" style="width:{pct:.1f}%"></div></div>
  <div class="prog-steps">{''.join(pills)}</div>
  <div class="chips"><span class="chip">⏱ {fmt_duration(elapsed)}</span>{detail_html}</div>
</div>"""


def staff_html(abc, source):
    """Notenzeile (Gesangsstimme) eines Mashup-Teils in der Farbe des Quell-Songs."""
    if not abc:
        return ""
    return f'<div class="abc-staff" data-abc="{esc(abc)}" data-color="{MASH_COLORS.get(source, "#e8e7f5")}"></div>'


def slot_head(index, tag, source, song_title, available_b=True, stale=False):
    label = t("mash.from", song=source, title=song_title or "–")
    extra = "" if available_b else f'<span class="slot-note">{esc(t("mash.only_a"))}</span>'
    stale_html = f'<span class="slot-stale">{esc(t("mash.stale"))}</span>' if stale else ""
    return (f'<div class="slot-head {source.lower()}"><span class="slot-num">{index + 1:02d}</span>'
            f'<span class="slot-tag">{esc(tag)}</span><span class="slot-src">{esc(label)}</span>{extra}{stale_html}</div>')


def timeline_html(slots, title_a="", title_b=""):
    """Ablaufleiste: ein Segment je Teil, Breite nach Takten, Farbe nach Quelle."""
    if not slots:
        return ""
    total = sum(max(s.get("bars", 1), 1) for s in slots)
    segs = "".join(
        f'<div class="tl-seg {s["source"].lower()}" style="flex:{max(s.get("bars", 1), 1) / total:.4f}" '
        f'title="{esc(s["tag"])} – {s["source"]}"><span>{esc(s["tag"])}</span></div>' for s in slots)
    legend = (f'<div class="tl-legend"><span class="tl-dot a"></span>{esc(t("mash.song_a"))}: {esc(title_a or "–")}'
              f'<span class="tl-dot b"></span>{esc(t("mash.song_b"))}: {esc(title_b or "–")}</div>')
    return f'<div class="timeline"><div class="tl-bar">{segs}</div>{legend}</div>'


def head_html(lang):
    """Gradio übersetzt seine eigenen Texte (z. B. „Audio hier ablegen“) anhand von navigator.language.
    Vor dem Start der App auf die gewählte Sprache setzen (zuletzt gewählte Sprache aus localStorage)."""
    return f"""<script>
(function () {{
  try {{
    var l = localStorage.getItem('yue2_lang') || '{lang}';
    Object.defineProperty(navigator, 'language', {{ get: function () {{ return l; }} }});
    Object.defineProperty(navigator, 'languages', {{ get: function () {{ return [l]; }} }});
  }} catch (e) {{}}
}})();
</script>""" + SYSMON_JS + STAFF_JS
