# Roll-Assistent — Ein-Schuss-Empfehlung → echter Chat-Dialog

**Datum:** 2026-07-21
**Branch:** `feature/roll-and-screen`
**Betroffene Dateien:** `src/llm_client.py`, `pages/roll_and_screen.py`

---

## Problem

Der Roll-Assistent auf der Roll-Seite (`_render_roll_ai_chat`) ist heute **kein Chat**,
sondern ein Formular mit einem Schuss:

1. User gibt 2 Zahlen ein (roll_count, prev_netto)
2. Klick auf "Empfehlung anfordern"
3. DeepSeek bekommt **einen** Prompt, der ihn zwingt: *"ANTWORTE EXAKT IN DIESEM
   FORMAT (kein anderes Format akzeptiert)"* → Tabelle zurück
4. Ende. Keine Rückfrage möglich.

Der User will einen **echten Dialog**: erst die Empfehlung, danach frei nachfragen
("Warum nicht Stufe 3?", "Was wäre bei 90 DTE?") und DeepSeek antwortet im Kontext
der Position.

## Ziel

Aus dem Ein-Schuss-Formular einen **Analyse-dann-Chat**-Assistenten machen:
- Erste Empfehlung bleibt strukturiert (Tabelle) — funktioniert, ist wertvoll.
- Darunter ein echtes Chat-Fenster mit Verlauf und freien Rückfragen.
- **Rückbaubarkeit ist explizites Design-Ziel** (User-Wunsch): der Umbau muss per
  Git-Revert vollständig entfernbar sein, ohne dass die Ein-Schuss-Empfehlung leidet.

---

## Architektur — 3 Bausteine

### Baustein 1: `LLMClient` — Message-History (additiv)

`src/llm_client.py`

Neue Methode `chat_completion_messages()` **neben** der bestehenden
`chat_completion()`. Sie nimmt eine fertige Message-Liste
(`[{"role": "system"|"user"|"assistant", "content": str}, ...]`) und schickt sie
komplett an DeepSeek (die OpenAI-kompatible API kann das nativ).

Die alte `chat_completion(system_prompt, user_prompt)` bleibt in ihrer Signatur
**unverändert** und wird intern zu einem 2-Element-Aufruf der neuen Methode
umgebaut. Alle bestehenden Call-Sites (`rank_puts`, erste Roll-Empfehlung) laufen
unverändert weiter.

**Warum additiv statt Umbau:** null Regressions-Risiko, und die neue Methode ist
isoliert löschbar (Rückbaubarkeit).

Signatur:
```python
def chat_completion_messages(
    self,
    provider: str,
    *,
    messages: list[dict[str, str]],
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 3500,
) -> LLMResponse
```

Der DeepSeek-Pfad wird so refaktoriert, dass `_chat_completion_deepseek` eine
`messages`-Liste bekommt statt system_prompt+user_prompt. Der Rest (Auth, Timeout,
`thinking: disabled`, Content-Parsing, LLMResponse) bleibt identisch.

### Baustein 2: Chat-UI in `_render_roll_ai_chat()`

`pages/roll_and_screen.py`

Der bestehende Block bis zur ersten Empfehlung bleibt **exakt wie er ist**
(Formular → Spinner → Tabelle). Neu darunter:

- Beim ersten erfolgreichen "Empfehlung anfordern" wird der eingefrorene
  System-Kontext + die erste Assistant-Antwort in die Chat-History übernommen.
- `st.chat_message("user"/"assistant")` rendert den Verlauf.
- `st.chat_input("Rückfrage an DeepSeek…")` als Eingabe.
- Bei Eingabe: History + neue User-Frage → `chat_completion_messages()` →
  Antwort anhängen → `st.rerun()`.
- `🗑️ Chat zurücksetzen`-Button löscht messages + context + Ergebnis.

### Baustein 3: State-Modell (session_state, position-gebunden)

Bindung an bestehenden `chat_key = f"roll_ai_{symbol}_{K:.2f}"`.

| Key | Inhalt |
|---|---|
| `{chat_key}_context` | Eingefrorener System-Prompt (Position + Kandidaten + Strategie-Wissen). Einmal beim ersten "Empfehlung anfordern" gesetzt = **Snapshot**. |
| `{chat_key}_messages` | Liste der Chat-Turns: `[{"role": "user"/"assistant", "content": str}]`. Erste Assistant-Nachricht = die strukturierte Empfehlung. |
| `{chat_key}_result` / `_usage` / `_model` | Bleiben für die Anzeige der ersten Empfehlung + Meta (wie bisher). |

Wechsel von Symbol oder Strike → neuer `chat_key` → automatisch frischer Chat.
Kein Übersprechen zwischen Positionen möglich.

---

## Prompt-Umbau

`_build_roll_ai_prompt()` liefert weiterhin den großen Kontext-Text. Aufteilung
in der Message-Liste:

1. **System-Message** = Rollenbeschreibung + Positions-Kontext + alle Roll-Kandidaten
   + Strategie-Wissen (Buch + Ludwig). Gelockert: *"Antworte präzise auf Basis
   dieser Daten. Nutze Tabellen NUR wenn du rechnest — sonst normale Erklärung.
   Antworte auf Deutsch."* (Das strenge "kein anderes Format akzeptiert" fällt weg.)
2. **Erste User-Message** = *"Gib mir deine Roll-Empfehlung im folgenden Format: …"*
   (das exakte Tabellenformat, das bisher im Prompt stand). → erste Antwort bleibt
   strukturiert.
3. **Folge-User-Messages** = die freien Rückfragen des Users. Da das Format nur in
   der ersten User-Message verlangt wird, antwortet DeepSeek auf Rückfragen frei.

**Kontext-Umfang (User-Entscheidung):** Voller Kontext immer — die System-Message
mit Position + Kandidaten bleibt bei jeder Runde die erste Message, wird also bei
jedem Request mitgeschickt. DeepSeek "vergisst" die Kandidaten nie.

**Preise (User-Entscheidung):** Snapshot einfrieren. Kurs/Put-Preis/Kandidaten
werden beim Öffnen der Position einmal geholt und gelten für den ganzen Chat
(die DB-Preise sind ohnehin Tagesschluss-Näherungen).

---

## Fehlerbehandlung

- `LLMProviderError` / Timeout / sonstige Exception → `st.error(...)` in der
  Chat-Zeile.
- Die fehlgeschlagene User-Nachricht wird **nicht** in die History committed
  (sonst hängt ein unbeantworteter Turn drin und wird bei jedem Folge-Request
  mitgeschickt). User kann die Frage einfach neu abschicken.

---

## Rückbaubarkeit (explizites Ziel)

- Baustein 1 ist rein additiv: neue Methode löschen, alte funktioniert weiter.
- Baustein 2+3 sind ein klar abgegrenzter Zusatzblock **unter** der bestehenden
  Ein-Schuss-Logik. Im Git-Diff isoliert, per Revert-Commit vollständig entfernbar.
  Die Formular-Empfehlung bleibt danach unangetastet funktionsfähig.

---

## Testing

- **Unit:** `chat_completion_messages()` — Message-Liste wird korrekt ins Payload
  gemappt; alte `chat_completion()` erzeugt identisches Payload wie vorher
  (2-Element system+user). DeepSeek-Call gemockt (kein echter API-Call im Test).
- **Manuell auf DB-Maschine:** Symbol+Strike wählen → Empfehlung anfordern (Tabelle
  erscheint) → Rückfrage stellen (freie Antwort) → zweite Rückfrage (Kontext noch da)
  → Symbol wechseln (frischer Chat) → Reset-Button (Chat leer) → API-Key entfernen
  (saubere Fehlermeldung, kein Crash, kein hängender Turn).

---

## Nicht im Scope (YAGNI)

- DB-Persistenz des Chats (Seite ist bewusst session-only).
- Streaming-Antworten (DeepSeek-Antwort kommt als Block, wie bisher).
- Umschalter zwischen "strukturiert" und "frei" (Hybrid) — verworfen.
- Live-Nachladen der Preise während des Chats — verworfen (Snapshot).
