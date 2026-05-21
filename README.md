# GradeMatch

GradeMatch is a native Windows/macOS/Linux desktop app built with Python and CustomTkinter. It compares a source photo against a reference photo and generates an AI-assisted color grading, retouching, and visual matching blueprint.

The app supports both ChatGPT and Gemini, includes side-by-side image previews, editable prompt presets, encrypted local API key storage, and a black desktop interface.

![GradeMatch logo](assets/app_logo.png)

## Features

- Black CustomTkinter desktop UI.
- ChatGPT and Gemini provider selector.
- Default model targets:
  - ChatGPT: `gpt-5.2-pro`
  - Gemini: `gemini-2.5-pro`
- Two-image comparison workflow:
  - Image 1: reference / target style image.
  - Image 2: source / raw image.
- Live prompt editor for tailoring the analysis.
- Persistent custom prompt presets in `prompt_presets.json`.
- Local encrypted API key storage using `.config.json` and `.config.key`.
- One-click daily workflow after keys are saved.
- Threaded API execution so the UI remains responsive.
- Automatic cleanup of stored keys when a saved key appears invalid or expired.
- Built-in Instructions tab inside the app.

## Project Files

- `app.py`: main GradeMatch application.
- `assets/app_logo.png`: source logo used in the app header.
- `assets/app_logo.ico`: Windows app/executable icon.
- `requirements.txt`: Python dependencies.
- `prompt_presets.json`: generated automatically when presets are saved.
- `.config.json`: hidden encrypted local API key config, generated only when saving keys.
- `.config.key`: hidden local encryption key, generated only when saving keys.
- `dist/GradeMatch.exe`: packaged app after building with PyInstaller.

## Installation

Install Python 3.10 or newer, then run:

```powershell
python -m pip install -r requirements.txt
```

Run the app from source:

```powershell
python app.py
```

## Building the Windows Executable

Install PyInstaller if needed:

```powershell
python -m pip install pyinstaller
```

Build the app:

```powershell
python -m PyInstaller --windowed --onefile --name GradeMatch app.py
```

The executable will be created at:

```text
dist/GradeMatch.exe
```

## API Key Setup

GradeMatch can use keys in three ways:

1. Paste the key into the app field.
2. Save it locally with `Save Keys Locally`.
3. Use environment variables.

Supported environment variables:

- ChatGPT/OpenAI: `OPENAI_API_KEY`
- Gemini: `GOOGLE_API_KEY` or `GEMINI_API_KEY`

Saved keys are encrypted locally using `cryptography.Fernet`. The app stores encrypted values in `.config.json` and the matching local encryption key in `.config.key`. On Windows, both files are marked hidden. On platforms that support POSIX permissions, file permissions are restricted.

Use `Clear Saved Keys` in the app to wipe saved credentials.

## Using GradeMatch

1. Open GradeMatch.
2. Choose `ChatGPT` or `Gemini`.
3. Paste the matching API key or use a saved key.
4. Click `Save Keys Locally` if you want one-click future use.
5. Load Image 1, the target/reference image.
6. Load Image 2, the raw/source image.
7. Select a prompt recipe.
8. Optionally edit the prompt in the live prompt editor.
9. Click `Run GradeMatch Analysis`.
10. Copy the generated output from the result panel.

## Prompt Presets

The app ships with:

- `Adobe Photoshop (PC Desktop Master Suite)`
- `Adobe Lightroom Mobile (Strict Free Tier Engine)`
- `Google Snapseed (Mobile Correction Engine Constraints)`

To create a custom preset:

1. Edit the live prompt text.
2. Type a new preset name.
3. Click `Save Custom Preset`.

Custom presets are saved into `prompt_presets.json` in the app folder.

## Troubleshooting

If the app says the API key is missing, paste a key into the correct provider field or set the environment variable.

If a saved key is invalid or expired, GradeMatch clears the stored key for that provider and asks you to enter a fresh one.

If Gemini returns a model or quota error, confirm your Google API key has access to `gemini-2.5-pro`.

If ChatGPT returns a model access error, confirm your OpenAI account has access to `gpt-5.2-pro`.

If image preview fails, try JPG, PNG, WEBP, BMP, or TIFF. HEIC depends on local Pillow support and may vary by system.

## Security Notes

GradeMatch stores credentials locally only when you click `Save Keys Locally`.

This is local encryption designed for desktop convenience. Anyone with full access to both `.config.json` and `.config.key` on the same machine may be able to decrypt the saved values. For maximum security, use environment variables or avoid saving keys locally.

## Development Notes

The app uses background threads for API requests and returns UI updates to the Tkinter main loop via `after(...)`. This prevents the app window from freezing during network calls.

Dependencies:

- `customtkinter`
- `openai`
- `pillow`
- `google-generativeai`
- `cryptography`
