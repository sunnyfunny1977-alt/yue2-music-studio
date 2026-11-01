"""Online-Suche nach Songtexten über LRCLIB (https://lrclib.net) – kostenlos, ohne Konto/API-Schlüssel."""
import re
import time

import requests

from settings import CONFIG

PROVIDER = "LRCLIB"
API = CONFIG.get("lyrics_api_url", "https://lrclib.net/api").rstrip("/")
USER_AGENT = "YuE2-Music-Studio (https://github.com/sunnyfunny1977-alt/yue2-music-studio)"
_LRC_TIME = re.compile(r"^\s*(\[\d{1,2}:\d{2}(?:[.:]\d{1,3})?\])+\s*")
_NORMALIZE = re.compile(r"[\W_]+", re.UNICODE)


class LyricsError(RuntimeError):
    pass


def _norm(text):
    return _NORMALIZE.sub(" ", (text or "").casefold()).strip()


def _plain_from_synced(synced):
    """Zeitstempel aus LRC-Zeilen entfernen („[01:23.45] Text“ → „Text“)."""
    return "\n".join(_LRC_TIME.sub("", line) for line in (synced or "").splitlines()).strip()


def _query(params, attempts=3):
    """Ruft /api/search auf. LRCLIB antwortet gelegentlich kurz mit 5xx – dann bis zu zweimal wiederholen."""
    for attempt in range(attempts):
        try:
            r = requests.get(f"{API}/search", params=params, headers={"User-Agent": USER_AGENT}, timeout=20)
            if r.status_code >= 500 and attempt < attempts - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.json() or []
        except requests.ConnectionError as e:
            if attempt < attempts - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise LyricsError(str(e)) from e
        except (requests.RequestException, ValueError) as e:
            raise LyricsError(str(e)) from e
    return []


def search(title, artist="", duration=None, limit=10):
    """Sucht Songtexte und gibt die besten Treffer zuerst zurück.

    Jeder Treffer: {id, title, artist, album, duration, synced, lyrics}. Instrumentals und leere Einträge
    werden aussortiert. Sortiert nach Titel-/Interpret-Übereinstimmung und Nähe zur Songlänge.
    """
    title, artist = (title or "").strip(), (artist or "").strip()
    if not title:
        return []
    params = {"track_name": title}
    if artist:
        params["artist_name"] = artist
    raw = _query(params)
    if not raw and artist:  # Fallback: Freitextsuche, z. B. bei abweichender Schreibweise
        raw = _query({"q": f"{artist} {title}"})

    results, seen = [], set()
    for item in raw:
        if item.get("instrumental"):
            continue
        lyrics = (item.get("plainLyrics") or "").strip() or _plain_from_synced(item.get("syncedLyrics"))
        if not lyrics:
            continue
        key = (_norm(item.get("trackName")), _norm(item.get("artistName")), lyrics[:200])
        if key in seen:  # identische Einträge (z. B. dasselbe Album mehrfach) nur einmal zeigen
            continue
        seen.add(key)
        results.append({
            "id": item.get("id"), "title": item.get("trackName") or "", "artist": item.get("artistName") or "",
            "album": item.get("albumName") or "", "duration": float(item.get("duration") or 0),
            "synced": bool(item.get("syncedLyrics")), "lyrics": lyrics,
        })

    want_title, want_artist = _norm(title), _norm(artist)

    def score(r):
        s = 0.0
        if _norm(r["title"]) == want_title:
            s -= 100
        if want_artist and _norm(r["artist"]) == want_artist:
            s -= 50
        elif want_artist and want_artist in _norm(r["artist"]):
            s -= 25
        if duration and r["duration"]:
            s += min(abs(r["duration"] - duration), 120) / 2  # Länge nah am hochgeladenen Song bevorzugen
        return s

    results.sort(key=score)
    return results[:limit]
