<p align="center"><img src="docs/logo.png" alt="YuE2 Music Studio – Logo" width="280"></p>
<h1 align="center">YuE2 Music Studio</h1>

<p align="center"><sub>früher „YuE2 Studio“ · formerly “YuE2 Studio”</sub></p>

Lokale Gradio-App für das KI-Musikmodell **YuE2** (`m-a-p/YuE2-3B`).
Lyrics und Style-Prompt erzeugt ein lokales Ollama-Modell über einen Masterprompt. Beides lässt sich danach von Hand oder per KI korrigieren.

> **English:** A local Gradio app (German/English UI) for the AI music model YuE2. A local Ollama model writes the lyrics and style prompt from your idea via a master prompt, and you can refine them by hand or ask the AI to correct them. *New song* turns an idea into a full song, optionally bilingual (e.g. German verses with an Arabic chorus). *Remake* transcribes the melody of an uploaded song (SheetSage2) and its vocals (Whisper), then sings new or translated lyrics on the original melody in a new style. Songs are only saved on request, as MP3 or FLAC, together with an info TXT file. Windows · NVIDIA GPU or AMD Radeon GPU (ROCm, untested on real hardware) with ≥ 24 GB VRAM, 16 GB cards in an experimental low-VRAM mode · see *Installation* below (`install.ps1` detects your GPU, then `start.bat`).

Quellen: [YuE2 Prompt-Guide (ComfyUI)](https://docs.comfy.org/tutorials/audio/yue2/yue2) · [YuE GitHub](https://github.com/multimodal-art-projection/YuE)

## Vorschau / Preview

<p align="center"><img src="docs/vorschau.png" alt="YuE2 Music Studio – Oberfläche mit Idee, Feinschliff, Generieren und Speichern" width="900"></p>

**Bibliothek / Library** – gespeicherte Songs mit FLUX.3-Covern, Details und Wiederverwenden:

<p align="center"><img src="docs/vorschau2.png" alt="YuE2 Music Studio – Bibliothek mit Song-Kacheln, Covern und Detailkarte" width="900"></p>

**Mashup** – zwei Songs, Ablauf von Song A, je Teil A (violett) oder B (cyan), Text über den Noten:

<p align="center"><img src="docs/vorschau3.png" alt="YuE2 Music Studio – Mashup aus „Neon Rain Drive“ und „Letters to the Sea“ mit farbiger Ablaufleiste und Teil-Karten" width="900"></p>

**Einstellungen / Settings** – MP3/FLAC-Qualität und Tags; der Künstlername erscheint auf Wunsch auf dem FLUX-Cover:

<table align="center"><tr>
<td><img src="docs/vorschau4.png" alt="YuE2 Music Studio – Export-Einstellungen mit Künstler, Album, Genre und Jahr" width="440"></td>
<td><img src="docs/cover_beispiel.jpg" alt="FLUX.3-Cover „Neon Rain Drive“ mit Künstlername „Luna Vale“" width="360"></td>
</tr></table>

<sub>Alle Songs, Künstler und Cover in den Vorschaubildern sind erfunden und mit YuE2 Music Studio erzeugt.</sub>

## Beispiel / Example

Ein mit der App erzeugter Song (Modus *Neuer Song*, Ollama `qwen3.8:27b`, YuE2 `cot=full`, 56 s, Rechenzeit 40 s auf einer RTX 5090):

| Datei | Inhalt |
|---|---|
| [Sonntagsruhe.mp3](examples/Sonntagsruhe.mp3) | MP3, 48 kHz Stereo, 320 kbit/s |
| [Sonntagsruhe.flac](examples/Sonntagsruhe.flac) | FLAC, 48 kHz Stereo, 24 Bit |
| [Sonntagsruhe.txt](examples/Sonntagsruhe.txt) | Info-Datei: Idee, Style, Lyrics, Songlänge, Seed, Einstellungen und geplante Partitur (ABC) |

> **Idee:** „Ein lockerer Reggae-Song über einen faulen Sonntag in der Hängematte, entspannte Männerstimme“
> **Style:** `German, relaxed male vocal, reggae, chill, lazy, 75 BPM, clean electric guitar skank, upright bass, muted drums, warm organ, laid-back groove`

## Voraussetzungen
- **NVIDIA:** Windows 10/11, GPU mit BF16 und ≥ 24 GB VRAM (getestet: RTX 5090)
- **AMD Radeon:** Windows 11, Radeon RX 7000/9000, Radeon AI PRO R9700 oder PRO W7800/W7900, Treiber Adrenalin 26.2.2 oder neuer. Details im Abschnitt [AMD Radeon](#amd-radeon).
- 16-GB-Karten beider Hersteller laufen in einem **experimentellen Sparmodus**.
- [uv](https://docs.astral.sh/uv/), [ffmpeg](https://www.gyan.dev/ffmpeg/builds/) im PATH, git
- [Ollama](https://ollama.com) mit mindestens einem Modell, z. B. `ollama pull qwen3.8:27b`
- ca. 25 GB freier Speicher für Umgebungen und Modelle

## Installation
```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```
`install.ps1` erkennt die Grafikkarte (die Karte mit dem meisten VRAM entscheidet) und startet den passenden Installer. Du kannst ihn auch direkt aufrufen:

| Installer | Grafikkarte | PyTorch |
|---|---|---|
| `install_nvidia.ps1` | NVIDIA (RTX 30/40/50 …) | Torch 2.10, CUDA 12.8 |
| `install_amd.ps1` | AMD Radeon | Torch 2.9.1, ROCm 7.2.1 (AMD-Wheels für Windows) |

Beide legen zwei getrennte Umgebungen an, weil YuE2 und SheetSage2 unterschiedliche Versionen benötigen:

| Umgebung | Python | Inhalt |
|---|---|---|
| `.venv-yue2` | 3.12 | App, YuE2 0.1.6, PyTorch (CUDA bzw. ROCm), Gradio, Whisper |
| `.venv-sheetsage2` | 3.11 | SheetSage2 (Melodie → Noten) für Remakes, Torch 2.8 (NVIDIA: CUDA, AMD: CPU) |

Optionen:
- `-Vendor nvidia|amd`: Hersteller erzwingen (nur `install.ps1`)
- `-SkipSheetSage`: ohne Remake-Funktion
- `-SkipModels`: Modelle erst beim ersten Start laden
- `-DryRun`: nur anzeigen, was installiert würde

## Start
`start.bat` doppelklicken. Danach öffnet sich http://127.0.0.1:7860.

## Sprache / Language
Die Oberfläche gibt es auf **Deutsch** und **Englisch**.
- Beim **ersten Start** erscheint ein Dialog zur Wahl der Sprache. Die Wahl wird in `user_settings.json` gespeichert.
- Danach lässt sich die Sprache jederzeit **oben rechts (DE | EN)** wechseln. Gibt es noch keine Eingaben, lädt die Seite kurz neu und ist komplett umgestellt. Mit laufender Arbeit wird live umgestellt, ohne dass Eingaben oder ein generierter Song verloren gehen. Einige kleine Texte von Gradio selbst (z. B. der Upload-Hinweis) folgen dann beim nächsten Öffnen.
- Auch Meldungen, Prüfhinweise und die gespeicherte Info-TXT erscheinen in der gewählten Sprache. Die Masterprompts für Ollama bleiben englisch, weil das die Ergebnisse verbessert. Die Sprache der Lyrics wählst du unabhängig davon.
- Um den Startdialog erneut zu sehen, `user_settings.json` löschen.

> **English:** On first launch you are asked to choose the interface language (German or English). You can switch any time with the **DE | EN** toggle in the top right corner. Messages, check results and the saved info TXT follow the selected language, while the lyrics language is chosen separately. Delete `user_settings.json` to see the language dialog again.

## Bedienung
1. **Modus wählen**
   - **Neuer Song:** Idee eingeben, Sprache und Ziel-Länge wählen, dann **„Lyrics & Style erstellen“**.
   - **Mehrsprachige Songs:** Unter **„Zweite Sprache“** eine weitere Sprache wählen und bei **„Einsatz“** festlegen, wo sie gesungen wird: Refrain, Bridge, Refrain + Bridge, einzelne Zeilen gemischt oder wie in der Idee beschrieben. Beispiel: deutscher Text mit Refrain auf Arabisch. Das funktioniert in beiden Modi; im Remake mit „Original beibehalten“ wird dann nur der gewählte Teil übersetzt. Jede Sprache wird in ihrer eigenen Schrift geschrieben (Arabisch in arabischer Schrift, Russisch kyrillisch …), weil YuE2 sie so zuverlässiger singt als in lateinischer Umschrift. Getestet: Deutsch mit arabischem Refrain. YuE2 ist offiziell vor allem auf Chinesisch und Englisch trainiert, andere Sprachen klingen je nach Sprache unterschiedlich gut.
   - **Remake:** Song hochladen. Eine Karte zeigt Cover, Titel, Interpret und weitere Tags des Originals. Optional unter **„Originaltext online suchen“** den Songtext von [LRCLIB.net](https://lrclib.net) abrufen: Titel und Interpret sind aus den Tags vorbelegt, und die Treffer sind nach Übereinstimmung und Songlänge sortiert. Mit **„Als Originaltext übernehmen“** landet der Text im Feld „Originaltext“, und die Analyse überspringt dann die Whisper-Erkennung. Songtexte sind urheberrechtlich geschützt: nur privat verwenden und die Rechte am Original beachten. Danach **„Song analysieren“** klicken. SheetSage2 schreibt die Melodie als ABC-Noten, Whisper erkennt den Gesangstext. Danach den Lyrics-Modus (beibehalten, neu schreiben, übersetzen) und den neuen Stil wählen und **„Lyrics & Style erstellen“** klicken. YuE2 singt die Lyrics anschließend auf die Originalmelodie im neuen Stil.
2. **Bearbeiten:** Titel, Style und Lyrics frei editieren. **„Prüfen“** zeigt Regelverstöße und die geschätzte Länge. **„Mit KI korrigieren“** setzt einen Korrekturwunsch um und behebt dabei auch Regelverstöße.
3. **Song generieren:** Ollama wird automatisch aus dem VRAM entladen. Fortschritt und Abbruch sind möglich. Das Ergebnis ist zunächst **nur eine Vorschau** und wird nicht gespeichert.
4. **Speichern:** Dateiname (= Songname), MP3 (320 kbit/s) oder FLAC (24 Bit) und Zielordner wählen. Dabei entstehen zwei Dateien:
   - `<Name>.mp3` bzw. `<Name>.flac`
   - `<Name>.txt` mit Titel, Datum, Modus, Idee, Style, Lyrics, Songlänge, Seed, Einstellungen, Modellen und beim Remake zusätzlich Quelldatei, Transkript und Melodie-ABC
   - optional `<Name>.jpg`: Mit **„🎨 Cover mit FLUX.3 erzeugen“** entsteht direkt nach dem Speichern ein Cover (siehe unten).

## Mashup
Im Reiter **„🎚️ Mashup“** entsteht aus zwei Songs ein neues Lied:
1. **Song A** und **Song B** hochladen (Song A gibt Ablauf, Tonart und Tempo vor). Den Originaltext je Song optional einfügen oder unter **„Originaltext online suchen“** von [LRCLIB.net](https://lrclib.net) übernehmen (Titel und Interpret sind aus den Tags vorbelegt) – sonst erkennt Whisper ihn.
2. **„Beide Songs analysieren“** – SheetSage2 schreibt die Melodien als Noten, die KI (Denkmodus) schlägt für jeden Teil vor, ob er aus A oder B kommt (z. B. Strophen A, Refrains B).
3. Die **Ablaufleiste** zeigt farbig, welcher Song wo erklingt (**A violett, B cyan**). Jeder Teil hat eine eigene Karte mit **A/B-Umschalter**, dem **Text über den Noten** und den **Noten der Gesangsstimme** in der Farbe des Quell-Songs. Song-B-Teile werden automatisch in Tonart und Tempo von A angeglichen (Transposition, Notenlänge, Oktavlage) – die Noten zeigen schon die angeglichene Fassung.
4. **Style-Prompt** frei eingeben oder **„Style vorschlagen“**, dann **„Mashup-Text erstellen“**: Die KI (immer im Denkmodus) verwendet für jeden Teil den Originaltext des gewählten Songs und baut mashup-typische Übergänge ein – angeteaserte Hooks, Call-and-Response, verbindende Brückenzeilen.
5. Texte direkt bearbeiten, Teile umschalten (der Text des Teils wird als veraltet markiert, **„Text für geänderte Teile neu erzeugen“** schreibt nur diese neu) oder per **Korrekturwunsch** von der KI anpassen lassen.
6. **„Ins Studio übernehmen“** – Noten, Text und Style landen im Studio; dort wie gewohnt generieren, speichern und Cover erstellen. Die Info-TXT vermerkt beide Quellen, die Angleichung von Song B und den Ablauf; die Bibliothek zeigt den Song als „Mashup“ und kann ihn per „Alles übernehmen“ erneut generieren.

## Einstellungen (Export)
Im Reiter **„⚙️ Einstellungen“** legst du fest, wie Songs gespeichert werden (dauerhaft in `user_settings.json`):
- **MP3-Bitrate**: 128, 192, 256, 320 kbit/s oder VBR V0 · **FLAC-Bittiefe**: 16 oder 24 Bit
- **Tags**: Künstler, Album, Genre, Jahr, Kommentar – werden in MP3 und FLAC geschrieben und in der Info-TXT vermerkt.
- **Künstlername aufs Cover**: Ist ein Künstler gesetzt, malt FLUX.3 ihn zusätzlich zum Titel ins Cover (kleiner, direkt unter oder über dem Titel).

> **English:** The **Mashup** tab combines two songs: song A sets arrangement, key and tempo; for each section you choose whether melody and words come from A or B (colour-coded: A violet, B cyan; song B is transposed and time-matched automatically). Each section card shows its lyrics above the rendered vocal notes. The AI (always in thinking mode) writes the mashup lyrics from both originals with typical mashup transitions; you can edit them, switch sections and rewrite only the changed ones, or request corrections. *Send to studio* hands notes, lyrics and style to the studio for generating and saving. The **Settings** tab sets MP3 bitrate (128–320 kbps or V0), FLAC bit depth (16/24) and tags (artist, album, genre, year, comment); a set artist name is also painted onto FLUX covers.

## Bibliothek
Der Reiter **„📚 Bibliothek“** zeigt alle gespeicherten Songs als Kacheln: Cover (oder ein Platzhalter mit dem Titel), darunter Titel, Länge, Genre und Tempo. Erfasst werden der Standard-Ausgabeordner und jeder Ordner, in den du schon gespeichert hast. Suche (Titel, Style, Lyrics) und Sortierung (neueste, Titel, Länge) helfen beim Finden.

Ein Klick auf eine Kachel öffnet rechts die Detailkarte mit großem Cover, Infos (Länge, Modus, Sprache, Genre, BPM, Datum) und Player. Unter **„Details“** stehen Songkonzept, Idee, Style und Lyrics zum Lesen und Kopieren. Alle Infos stammen aus der Info-TXT des Songs (egal ob auf Deutsch oder Englisch gespeichert).

Wiederverwenden per Knopfdruck – die Werte landen im Studio, und die App wechselt dorthin:
- **„♻️ Alles übernehmen“**: Titel, Konzept, Idee, Sprache, Style, Lyrics, Seed und Planungsmodus. Bei Remakes zusätzlich die Original-Melodie (ABC) und der Stilwunsch – das Remake lässt sich so ohne Originaldatei erneut generieren.
- **„💡 Idee“**, **„🎨 Style“**, **„📝 Lyrics“**: nur der jeweilige Teil.

## Cover (optional, FLUX.3 Image Klein)
Auf Wunsch malt [FLUX.3 Image Klein](https://huggingface.co/black-forest-labs/flux-3-image-klein) ein Albumcover (512 × 512) mit dem **Songtitel als Schriftzug im Bild**. Ollama schreibt dafür aus Titel, Style, Songkonzept und Lyrics eine ausführliche Bildbeschreibung – mit dem offiziellen Prompt-Upsampler-Systemprompt von Black Forest Labs (`prompts/flux3_upsampler_t2i.md`). Das Cover wird als `<Name>.jpg` gespeichert, **in MP3 und FLAC eingebettet** (Audiodaten bleiben unverändert) und in der Info-TXT vermerkt. Erstellen lässt es sich beim Speichern (Checkbox) oder später in der Bibliothek (**„🎨 Cover erstellen“**, auch erneut mit neuem Motiv).

FLUX.3 läuft komplett innerhalb von YuE2 Music Studio – in einer eigenen Umgebung `.venv-flux3` (diffusers), ohne ComfyUI. Die Funktion ist **optional** und wird separat installiert:
```powershell
powershell -ExecutionPolicy Bypass -File install_cover.ps1
```
- Download: ca. **15,5 GB** (fp8-Variante, Standard) aus `unsloth/flux-3-image-klein` (Spiegel des offiziellen Repos, ohne Login). `-Variant bf16` lädt den größeren bf16-Transformer (ca. 20 GB gesamt).
- RTX 5090: ein Cover dauert etwa 35 s (davon ~20 s für die Bildbeschreibung durch Ollama), VRAM-Spitze ca. 17 GB. Danach gibt FLUX den Grafikspeicher sofort wieder frei, das Modell bleibt für weitere Cover im Arbeitsspeicher; **„🧹 VRAM freigeben“** beendet es ganz.
- Karten unter 22 GB VRAM nutzen automatisch CPU-Offload (langsamer, nicht getestet). AMD/ROCm: experimentell, nicht auf echter Hardware getestet.
- Ohne Installation sind die Cover-Knöpfe ausgegraut; alles andere funktioniert wie gewohnt.
- Lizenz des Modells: **FLUX Kommunity License** – kostenlos für private Nutzung und kleine Unternehmen, Details auf der Modellseite.

> **English:** The new **Library** tab shows all saved songs as tiles (cover, title, length, genre, BPM) with search and sorting. Clicking a tile opens a detail card with player and – under *Details* – concept, idea, style and lyrics, read from the song's info TXT. **Reuse** buttons copy everything (incl. seed and, for remakes, the original melody) or just idea, style or lyrics back into the studio. Optionally, **FLUX.3 Image Klein** creates a 512 × 512 album cover with the song title rendered into the artwork; Ollama writes the image prompt using BFL's official upsampler system prompt. The cover is saved as `<Name>.jpg`, embedded into MP3/FLAC and noted in the info TXT. FLUX runs fully inside YuE2 Music Studio (own environment, no ComfyUI) and is installed separately with `install_cover.ps1` (~15.5 GB download from `unsloth/flux-3-image-klein`, FLUX Kommunity License).

## Masterprompts
Die Prompts liegen in `prompts/` und lassen sich anpassen:
- `master_new.md`: neuer Song aus einer Idee
- `master_remake.md`: Lyrics passend zur transkribierten Originalmelodie (Silbenzahl je Zeile beibehalten)
- `master_correct.md`: Korrektur nach Wunsch und Regeln

Die Masterprompts arbeiten wie ein erfahrener Musikproduzent („YuE2 Song Architect“):
- **Songkonzept zuerst:** Ollama analysiert die Idee (Stil, Geschichte, Arrangement, Gesang, Produktion) und schreibt 2–3 Sätze Songkonzept. Erst danach folgen Style und Lyrics, die sich an das Konzept halten. Das Konzept steht im Feinschliff im Feld **„Songkonzept“**, lässt sich bearbeiten und landet in der Info-TXT.
- **Songwriting:** klare Kernaussage, konkrete Bilder statt Floskeln, Spannungsbogen von Strophe über Pre-Chorus zum Refrain, Refrain als Hook, echte Reime in jeder Sektion. Ein in der Idee mitgelieferter Songtext wird unverändert übernommen.
- **Style:** konkrete Musikbegriffe, keine widersprüchlichen Angaben, kein Negativ-Prompt (YuE2 hat keinen).
- **Qualitätskontrolle:** Vor der Antwort prüft das Modell Reime, Singbarkeit, Länge und alle Vorgaben.
- **Gezielte Korrektur:** „Mit KI korrigieren“ ändert nur das Betroffene und übersetzt Problembeschreibungen in konkrete Änderungen („zu langsam“ → höheres BPM, „Stimme geht unter“ → präsentere Stimme).

**🧠 Denkmodus** (Schalter unter der Modus-Leiste, standardmäßig an): Denkfähige Modelle wie Qwen überlegen vor der Antwort. Die Reime werden deutlich besser, dafür dauert es etwa dreimal so lange (getestet mit `qwen3.8:27b`: ca. 1–3 min statt 25 s). Modelle ohne Denkmodus laufen unverändert.

Kernregeln nach dem YuE2-Guide: Der **Style** ist eine kommagetrennte Liste in der Reihenfolge *Sprache → Stimme → Genre → Stimmung → BPM → Instrumente → Produktion*. Die **Lyrics** enthalten nur gesungene Wörter mit den Tags `[Intro] [Verse] [Pre-Chorus] [Chorus] [Bridge] [Interlude] [Outro]`. Musikalische Anweisungen stehen nie in den Lyrics.

## Einstellungen (`config.json`)
| Schlüssel | Bedeutung |
|---|---|
| `ollama_default_model` | vorausgewähltes Ollama-Modell |
| `ollama_think` | Denkmodus beim Start an (`true`) oder aus (`false`) |
| `flux_model_dir`, `flux_python` | Ort des FLUX.3-Modells und der FLUX-Umgebung (legt `install_cover.ps1` an) |
| `flux_variant` | `auto` (vorhandene Variante, fp8 bevorzugt), `fp8r` oder `bf16` |
| `cover_steps`, `cover_render_size`, `cover_size` | Schritte (16), Render-Größe (1024) und Endgröße des Covers (512) |
| `yue2_backend` | `auto` (NVIDIA: `torch` mit CUDA-Graphs, AMD: `torch-eager`), `torch` oder `torch-eager` |
| `yue2_attention` | `auto` (NVIDIA/Windows: cuDNN, da PyTorch für Windows ohne Flash-Attention gebaut ist; AMD: `sdpa`), `cudnn`, `sdpa` oder `flash` |
| `yue2_synth_attention` | Attention-Kern der Audio-Synthese: `auto` (NVIDIA: cuDNN, AMD: `sdpa` – spart bei einem 4-Minuten-Song rund 12 GB VRAM und ist mehrfach schneller), `cudnn`, `efficient`, `sdpa` oder `original` (YuE2-Standard) |
| `yue2_memory_budget_gib` | Obergrenze für das VRAM-Budget (wird automatisch auf den Speicher der Karte begrenzt) |
| `yue2_low_vram` | Sparmodus: `auto` (unter 22 GB VRAM aktiv), `on` oder `off` |
| `whisper_model` | Whisper-Modell für die Remake-Texterkennung |
| `output_dir` | Standard-Speicherordner |

## AMD Radeon
Die App läuft auch auf AMD-Grafikkarten. Grundlage ist AMDs offizielles PyTorch für Windows (ROCm 7.2.1).

> ⚠️ **Status:** Der AMD-Weg ist auf NVIDIA-Hardware so weit wie möglich nachgebildet und geprüft (Wheel-Adressen, Paketauflösung, Installer-Probelauf, die AMD-Code-Pfade der App). **Auf einer echten AMD-Karte wurde er noch nicht getestet.** Rückmeldungen gerne als [Issue](https://github.com/sunnyfunny1977-alt/yue2-music-studio/issues).

- **Unterstützte Karten** (laut AMD): Radeon RX 7900 XTX/XT, RX 7700, RX 9060 XT, RX 9070/9070 XT, Radeon AI PRO R9700, Radeon PRO W7800/W7900 (gfx1100/1101/1200/1201).
- **Voraussetzungen:** Windows 11, Treiber Adrenalin 26.2.2 oder neuer, Python 3.12 (installiert uv automatisch).
- **VRAM:** Karten mit 24 GB oder mehr laufen normal. **16-GB-Karten** (z. B. RX 9070 XT) laufen im **experimentellen Sparmodus**: Das Sprachmodell wird während der Audio-Synthese ausgelagert, und die Songlänge startet bei 180 s. Das ist langsamer und kann trotzdem am Speicher scheitern.
- **Technik:** YuE2 läuft mit Standard-Attention (`sdpa`) und ohne CUDA-Graphs (`torch-eager`). Wer experimentieren möchte, setzt in `config.json` `"yue2_backend": "torch"`.
- **Remake:** Die Melodie-Analyse (SheetSage2) läuft auf AMD-Systemen auf der **CPU**, weil SheetSage2 Versionen voraussetzt, für die es keine ROCm-Pakete gibt. Das dauert einige Minuten pro Song. Whisper und YuE2 laufen auf der GPU.
- **Bei Problemen** (laut AMD): Smart App Control deaktivieren und das Visual C++ 2015-2022 Redistributable installieren.

> **English:** AMD Radeon GPUs are supported via AMD's official PyTorch for Windows (ROCm 7.2.1, Windows 11, Adrenalin 26.2.2+). Run `install.ps1` (auto-detects the GPU) or `install_amd.ps1`. Cards with ≥ 24 GB run normally, 16 GB cards use an experimental low-VRAM mode. On AMD the melody analysis for remakes runs on the CPU. **The AMD path has not yet been tested on real AMD hardware.**

## Hinweise
- **Systemanzeige:** Oben im Kopfbereich zeigen Balken alle 2 Sekunden VRAM, GPU-Last, Leistungsaufnahme (Watt), CPU- und RAM-Auslastung. Ab 85 % werden sie gelb, ab 95 % rot. Bei NVIDIA kommen die GPU-Werte über NVML (`nvidia-ml-py`). Bei AMD unter Windows gibt es keine solche Schnittstelle, dort zeigen GPU-Last und Leistung „–“.
- Die Songlänge ergibt sich vor allem aus den Lyrics. „Max. Songlänge“ ist nur eine Obergrenze (25 Tokens/s). Meldet die App „Token-Limit erreicht“, endet der Song eventuell abrupt.
- YuE2 und SheetSage2 sind offiziell nur unter Linux getestet. Unter Windows läuft die App nativ. Zwei Windows-Eigenheiten fängt sie automatisch ab: Flash-Attention fehlt (stattdessen cuDNN), und SheetSage2 lädt Quelldateien per Pfad (sie werden in den Transformers-Modul-Cache gespiegelt). Falls es bei der Generierung trotzdem Fehler gibt, `"yue2_backend": "torch-eager"` versuchen.
- Richtwerte auf einer RTX 5090: ca. 1 min Song in 40–50 s, Melodie-Analyse ca. 75 s pro Minute Audio.
- Ollama und YuE2 passen nicht gleichzeitig in 32 GB VRAM. Die App entlädt das Ollama-Modell deshalb vor jeder Generierung automatisch.
- **VRAM-Bedarf:** Die App rechnet die Audio-Synthese mit einem speichersparenden Attention-Kern (cuDNN) und begrenzt den Cache von PyTorch. Ein 3-Minuten-Song braucht damit auf der RTX 5090 höchstens ~9 GB statt ~28 GB und ist etwa doppelt so schnell fertig (63 s statt 129 s). Der Klang bleibt gleich, nur die Rundung unterscheidet sich minimal.
- Whisper erkennt Gesang mit lauter Begleitung nicht immer fehlerfrei. Den Text vor dem Erstellen im Feld „Erkannter Originaltext“ prüfen.
- Bitte die Lizenzen der Modelle beachten (YuE2: siehe `MODEL_LICENSE` im YuE-Repository) und bei Remakes die Rechte am Original.

## Lizenz
Der Code dieser App steht unter der [Apache-2.0-Lizenz](LICENSE). Copyright 2026 sunnyfunny1977-alt.
Die Modelle (YuE2, SheetSage2, MERT, Whisper) und Bibliotheken werden von `install.ps1` aus ihren Original-Quellen geladen und unterliegen ihren eigenen Lizenzen. Die Notendarstellung nutzt [abcjs](https://abcjs.net) (MIT-Lizenz, `static/abcjs-basic-min.js`, Lizenz in `static/abcjs-LICENSE.md`). Das optionale Bildmodell FLUX.3 Image Klein (`install_cover.ps1`) steht unter der FLUX Kommunity License von Black Forest Labs; `prompts/flux3_upsampler_t2i.md` ist der unveränderte Upsampler-Systemprompt aus `black-forest-labs/flux-3-image-klein-pup` (Apache-2.0).
