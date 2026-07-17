# UFC Keypad Localization

UFC Keypad supports three interface-language modes:

- `system` — Simplified Chinese on a Chinese locale, English otherwise
- `en_US`
- `zh_CN`

The selected value is stored as `language` in `ufc_config.json`.

## Scope

Localized text includes:

- settings-window title and groups
- display selection and placement status
- fullscreen, always-on-top and scale controls
- native touch-isolation controls and status
- key-log group title
- startup-animation settings and status
- language selector itself

Established avionics terminology, DCS-BIOS identifiers, cockpit labels, SYSTEM 4 labels and cold-start checklist terminology remain in English in every language. This avoids translating aircraft-control names into labels that no longer match DCS or NATOPS terminology.

Console diagnostics, developer comments and historical engineering notes are not runtime UI and do not need to be translated to add a new interface language.

## Files

| File | Responsibility |
|---|---|
| `ufc/i18n.py` | Locale selection, persistent configuration and translation catalogue |
| `ufc/i18n_ui.py` | SettingsWindow capture, language selector and live retranslation |
| `ufc/startup_i18n.py` | Localization adapter for the dynamically attached startup-style controls |
| `ufc/windowing.py` | Localized display-placement status messages |
| `verify_i18n.py` | Dependency-light catalogue and formatting checks |

The localization modules are installed in both `main.py` and `main_safe.py` and are listed in `UFC_Keypad_v5.spec`.

## Adding text

1. Add a stable key to `_TRANSLATIONS` in `ufc/i18n.py`.
2. Provide both `en_US` and `zh_CN` entries.
3. Use `tr("key")` for runtime text.
4. Keep variable content in named format fields, for example:

```python
tr("settings.screen.item", index=0, name="DISPLAY1", width=1024, height=600)
```

5. Add or extend a check in `verify_i18n.py`.

Do not use translated text as a program-state identifier. Store stable values such as `en_US`, `ufc_bit`, control IDs and page IDs as data, and translate only the visible label.

## Verification

```bash
python verify_i18n.py
python _verify.py
```

The first command checks translation completeness and format substitution. The second command compiles and imports the full application in an off-screen Qt environment.
