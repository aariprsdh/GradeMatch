import base64
import json
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
import google.generativeai as genai
from cryptography.fernet import Fernet, InvalidToken
from openai import OpenAI
from PIL import Image


ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

APP_BG = "#000000"
PANEL_BG = "#050505"
SURFACE_BG = "#111111"
CANVAS_BG = "#000000"
BORDER = "#333333"
ACCENT = "#FFB800"
ACCENT_DIM = "#B8860B"
TEXT_PRIMARY = "#ffffff"
TEXT_BODY = "#dddddd"
TEXT_MUTED = "#777777"
TEXT_DIM = "#777777"
CONTROL_BG = "#050505"
CONTROL_HOVER = "#222222"
CONTROL_ACTIVE = "#111111"
FONT_FAMILY = "Consolas"
FONT_SIZE = 10
FONT_SIZE_SMALL = 9
FONT_SIZE_TITLE = 13
SUCCESS = ACCENT_DIM
DANGER = ACCENT_DIM

OPENAI_DEFAULT_MODEL = "gpt-5.5"
GEMINI_DEFAULT_MODEL = "gemini-2.5-pro"
OPENAI_RESPONSES_ONLY_MODELS = {"gpt-5.5-pro", "gpt-5.2-pro"}
MODEL_OPTIONS = {
    "ChatGPT": {
        "GPT-5.5": OPENAI_DEFAULT_MODEL,
        "GPT-5.5 Pro": "gpt-5.5-pro",
        "GPT-5.4 Mini": "gpt-5.4-mini",
        "GPT-5.4 Nano": "gpt-5.4-nano",
        "GPT-5.2": "gpt-5.2",
        "GPT-5.2 Pro": "gpt-5.2-pro",
        "Chat Latest": "chat-latest",
        "GPT-5 Mini": "gpt-5-mini",
        "GPT-5 Nano": "gpt-5-nano",
        "GPT-4.1": "gpt-4.1",
    },
    "Gemini": {
        "Gemini 2.5 Pro": GEMINI_DEFAULT_MODEL,
        "Gemini 2.5 Flash": "gemini-2.5-flash",
        "Gemini 2.5 Flash Lite": "gemini-2.5-flash-lite",
    },
}

APP_NAME = "GradeMatch"
RUN_BUTTON_TEXT = "Run GradeMatch Analysis"
LOGO_PNG = "assets/app_logo.png"
LOGO_ICO = "assets/app_logo.ico"
INSTRUCTIONS_TEXT = """GradeMatch Instructions

What GradeMatch does

GradeMatch compares two images:

1. Image 1 / Target: the reference grade, mood, or visual target.
2. Image 2 / Source: the raw photo you want to edit.

It sends both images to your selected AI engine and returns a practical color and retouching blueprint based on the active prompt recipe.

Daily workflow

1. Select the AI Engine: ChatGPT or Gemini.
2. Pick the model. Use Pro/best models for deeper analysis, or Mini/Nano/Flash models for faster results.
3. Paste your API key once.
4. Click Save Keys Locally if you want GradeMatch to remember it.
5. Load Image 1 and Image 2.
6. Choose or edit the prompt recipe.
7. Click Run GradeMatch Analysis.
8. Copy the output from the result box.

API keys

GradeMatch supports two providers:

ChatGPT: uses the OpenAI API key field and can switch between GPT-5.5, GPT-5.5 Pro, GPT-5.4 Mini/Nano, GPT-5.2, Chat Latest, Mini, Nano, and GPT-4.1 models.
Gemini: uses the Gemini API key field and can switch between Pro, Flash, and Flash Lite models.

Saved keys are encrypted locally in hidden app-folder files named .config.json and .config.key. Use Clear Saved Keys any time you want to remove them from this machine.

Prompt presets

The Prompt Recipe menu loads reusable prompt templates. You can edit the live prompt text before running. To keep your edited version, type a new preset name and click Save Custom Preset. Custom presets are saved in prompt_presets.json beside the app.

Troubleshooting

If the app says an API key is missing, paste the correct key into the provider field or set the matching environment variable.
If a saved key is invalid or expired, GradeMatch clears that saved provider key and asks you to enter a fresh one.
If image preview fails, try JPG, PNG, WEBP, BMP, or TIFF.
If a model is unavailable on your account, use the other provider or update the model constants in app.py.
"""


def app_root():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resource_path(relative_path):
    base_path = Path(getattr(sys, "_MEIPASS", APP_ROOT))
    return base_path / relative_path


APP_ROOT = app_root()
PRESETS_FILE = APP_ROOT / "prompt_presets.json"
CONFIG_FILE = APP_ROOT / ".config.json"
KEY_FILE = APP_ROOT / ".config.key"


def restrict_file(path):
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass

    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.kernel32.SetFileAttributesW(str(path), 0x02)
        except Exception:
            pass


def make_file_writable(path):
    if os.name == "nt" and Path(path).exists():
        try:
            import ctypes

            ctypes.windll.kernel32.SetFileAttributesW(str(path), 0x80)
        except Exception:
            pass
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass


class LocalCredentialStore:
    def __init__(self, config_path=CONFIG_FILE, key_path=KEY_FILE):
        self.config_path = Path(config_path)
        self.key_path = Path(key_path)

    def _fernet(self):
        if not self.key_path.exists():
            self.key_path.write_bytes(Fernet.generate_key())
            restrict_file(self.key_path)
        return Fernet(self.key_path.read_bytes())

    def load_keys(self):
        data = self.load_config()
        if not data:
            return {}
        try:
            fernet = self._fernet()
            keys = {}
            encrypted_keys = data.get("api_keys", {})
            for provider, token in encrypted_keys.items():
                try:
                    keys[provider] = fernet.decrypt(token.encode("utf-8")).decode("utf-8")
                except (InvalidToken, UnicodeDecodeError):
                    continue
            return keys
        except Exception:
            return {}

    def load_config(self):
        if not self.config_path.exists():
            return {}
        try:
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def save_keys(self, keys):
        fernet = self._fernet()
        encrypted = {}
        for provider, key in keys.items():
            clean_key = key.strip()
            if clean_key:
                encrypted[provider] = fernet.encrypt(clean_key.encode("utf-8")).decode("utf-8")

        payload = self.load_config()
        payload.update({
            "version": 1,
            "api_keys": encrypted,
        })
        self.save_config(payload)

    def load_preferences(self):
        return self.load_config().get("preferences", {})

    def save_preferences(self, preferences):
        payload = self.load_config()
        payload["version"] = 1
        payload["preferences"] = preferences
        self.save_config(payload)

    def save_config(self, payload):
        make_file_writable(self.config_path)
        self.config_path.write_text(json.dumps(payload, indent=4), encoding="utf-8")
        restrict_file(self.config_path)

    def clear_provider(self, provider):
        keys = self.load_keys()
        keys.pop(provider, None)
        if keys:
            self.save_keys(keys)
        else:
            self.clear_all()

    def clear_all(self):
        for path in (self.config_path, self.key_path):
            try:
                make_file_writable(path)
                path.unlink(missing_ok=True)
            except Exception:
                pass


DEFAULT_PRESETS = {
    "Adobe Photoshop (PC Desktop Master Suite)": """Act as an elite high-end commercial retoucher, master color scientist, and digital imaging technician (DIT). You are tasked with a pixel-by-pixel reverse engineering and style migration. Analyze the two uploaded images: Image 1 is my target reference look from Instagram; Image 2 is my unedited, raw source image.

Your objective is to extract the exact aesthetic DNA, contrast architecture, and chromatic profile of Image 1 and map it flawlessly onto Image 2 while strictly maintaining identity, natural skin texture, and authentic melanin depth.

Provide an absolute, zero-vagueness engineering blueprint for Adobe Photoshop on PC using exact numerical values, coordinates, and percentages. Break down your instructions into these exact technical sections:

1. RAW SENSOR INPUT & GLOBAL LUMA (Camera Raw Filter):
   - Provide exact slider values for the Basic Panel: Exposure (+/- EV), Contrast, Highlights, Shadows, Whites, and Blacks to match the dynamic range and shadow-crush profile of Image 1.
   - For cinema-level facial clarity without digital halo artifacts or artificial crunch, calculate explicit micro-contrast adjustments using precise numbers for Texture, Clarity, and Dehaze.

2. MULTI-CHANNEL POINT CURVES (Mathematically Defined):
   - Break down the exact Input/Output coordinate pairs for the Point Curve (RGB) to map global luminance (including matte shadow lifts or highlight roll-offs).
   - Provide explicit, independent Input/Output coordinate pairs for the Red Curve, Green Curve, and Blue Curve channels to isolate and replicate precise cross-processing, split-toning, or environmental color-cast anomalies.

3. SPATIAL FREQUENCY SEPARATION & RETOUCHING:
   - Define the exact Gaussian Blur pixel radius required to split Image 2 into a low-frequency (color/tonal transitions) and high-frequency (pores/fine texture) workflow based on the subject's distance.
   - Outline precise localized Dodge & Burn layer strategies (using 50% Gray overlay layers or independent Curves adjustment layers) to match the ambient facial lighting direction and highlight roll-off profile of Image 1.

4. TARGETED CHROMATICITY & COLOR SCIENCE:
   - Provide exact percentage values for a Selective Color adjustment layer across individual color channels: Reds, Yellows, Cyans, and Neutrals. Explicitly specify the CMYK slider shifts required to align skin tones and background palettes.
   - Provide exact numeric values for the Color Balance tool across Shadows, Midtones, and Highlights separately to lock in the final ambient mood.""",
    "Adobe Lightroom Mobile (Strict Free Tier Engine)": """Act as a master mobile colorist and expert in mobile imaging constraints. Analyze the two uploaded images: Image 1 is the target reference look, and Image 2 is my unedited mobile source photo.

Provide a comprehensive, highly granular style-migration manual using ONLY the tools available in the standard FREE version of Lightroom Mobile. You are strictly forbidden from recommending premium, paid, or subscription-locked features. Do not use local masking (Linear/Radial/AI Selects), healing/cloning brushes, or geometry/perspective correction tools. Maximize the global styling engine.

Your manual must contain definitive integers (-100 to +100) or precise decimal values for the following panels:

1. THE LIGHT PANEL:
   - Give exact numerical values for Exposure, Contrast, Highlights, Shadows, Whites, and Blacks to perfectly align the histogram distribution of Image 2 with the highlight preservation and shadow compression profile of Image 1.

2. LIGHTROOM TONE CURVES (Four-Channel Coordinates):
   - Provide exact mathematical Input/Output node coordinates for the Parametric/Point White Curve.
   - Provide independent Input/Output node coordinates for the Red, Green, and Blue curves to execute the exact color grade and tonal split seen in the reference asset.

3. COLOR MIXER / HSL MATRIX (8-Channel Breakdown):
   - Provide a complete, explicit table detailing the exact Hue (-100 to +100), Saturation (-100 to +100), and Luminance (-100 to +100) modifications for all 8 color channels: Red, Orange, Yellow, Green, Aqua, Blue, Purple, and Magenta.
   - Prioritize precise mathematical handling of the Orange and Red channels to enrich and preserve natural skin tones while radically shifting background vegetation or skies to match the reference.

4. THREE-WAY COLOR GRADING WHEELS:
   - Calculate exact numeric inputs for Shadows, Midtones, and Highlights wheels. Specify the precise Hue angle (0-360 degrees) and Saturation depth (0-100) for each wheel.
   - Provide the exact decimal value for the Blending (0-100) and Balance (-100 to +100) sliders to control the crossover thresholds of the color grade.

5. GLOBAL EFFECTS & APERTURE SIMULATION:
   - Specify exact integers for Texture, Clarity, and Dehaze to mirror the perceived sharpness of the reference without introducing artificial edge noise.
   - Provide precise values for Vignette, Midpoint, Roundness, and Feathering if a custom edge fall-off is needed to focus light on the subject.""",
    "Google Snapseed (Mobile Correction Engine Constraints)": """Act as a mobile post-production specialist engineered to extract maximum performance from the Google Snapseed application interface. Analyze the two uploaded images: Image 1 is the reference style benchmark; Image 2 is my raw, unedited source photo.

Translate the high-end color science of Image 1 into a step-by-step, manual execution recipe built entirely within Snapseed's local tools and workflow mechanics. Every tool block must state a definitive positive or negative integer value. Do not use vague or descriptive language.

Structure the recipe using Snapseed's native terminology in this exact sequence:

1. TUNE IMAGE GRID ENGINE:
   - Provide exact slider values (-100 to +100) for Brightness, Contrast, Saturation, Ambiance, Highlights, Shadows, and Warmth.
   - Optimize the Ambiance value specifically to compress the illumination delta between the background environment and the subject's face, matching the spatial lighting distribution of Image 1.

2. DETAILS & TEXTURAL HARMONY:
   - Provide explicit integer targets for Structure and Sharpening. Balance these values to extract clean facial details, clothing lines, or background textures without generating digital aliasing, pixel distortion, or noise artifacts.

3. WHITE BALANCE MAPPING:
   - Calculate the exact numerical adjustments for Temperature and Tint to lock down the overall color temperature of the shot before entering complex grading tools.

4. SNAPSEED FIVE-NODE CURVES TOOL:
   - Snapseed uses a simplified grid coordinate system. Translate the required color grading transformation into exact instructions for the Neutral (Luminance), Red, Green, and Blue curves.
   - Describe precisely where to drag and anchor the nodes on the grid (e.g., "Place an anchor point at the bottom 25% shadow region and pull down by X amount") to match the target's exact color profile.

5. LAYER BRUSH & SELECTIVE TOOL PINS:
   - Provide structural coordinates and brush parameters (Exposure, Temperature, Saturation at values of +/- 0.3, 0.7, or 1.0) for manual masking brush passes.
   - Identify exactly where to drop Selective pins on the subject's face or background to modify brightness and contrast locally, duplicating the high-end vignette or dodge-and-burn patterns of Image 1.""",
}


def load_presets():
    if PRESETS_FILE.exists():
        try:
            loaded = json.loads(PRESETS_FILE.read_text(encoding="utf-8"))
            return {**DEFAULT_PRESETS, **loaded}
        except Exception:
            return DEFAULT_PRESETS.copy()
    save_presets_to_file(DEFAULT_PRESETS)
    return DEFAULT_PRESETS.copy()


def save_presets_to_file(presets):
    try:
        PRESETS_FILE.write_text(json.dumps(presets, indent=4), encoding="utf-8")
    except Exception as exc:
        print(f"Error saving presets: {exc}")


def encode_image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def extract_openai_response_text(response):
    direct_text = getattr(response, "output_text", "")
    if direct_text:
        return direct_text

    output_chunks = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            text = getattr(content, "text", "")
            if text:
                output_chunks.append(text)
    return "\n".join(output_chunks)


def call_ai_engine(provider, api_key, model_name, prompt, img1_path, img2_path):
    if not provider or not api_key:
        raise ValueError("Missing API provider selection or API key.")
    if not model_name:
        raise ValueError("Missing AI model selection.")
    if not prompt:
        raise ValueError("Prompt field is empty.")
    if not img1_path or not img2_path:
        raise ValueError("Please select both Image 1 and Image 2 before processing.")

    if provider == "ChatGPT":
        client = OpenAI(api_key=api_key)
        base64_img1 = encode_image_to_base64(img1_path)
        base64_img2 = encode_image_to_base64(img2_path)

        if model_name in OPENAI_RESPONSES_ONLY_MODELS:
            response = client.responses.create(
                model=model_name,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": prompt},
                            {
                                "type": "input_text",
                                "text": "Image 1 is the target/reference look. Image 2 is the raw/source image to transform.",
                            },
                            {"type": "input_image", "image_url": f"data:image/jpeg;base64,{base64_img1}"},
                            {"type": "input_image", "image_url": f"data:image/jpeg;base64,{base64_img2}"},
                        ],
                    }
                ],
                max_output_tokens=4000,
            )
            return extract_openai_response_text(response) or "No response text returned."

        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "text", "text": "Image 1 is the target/reference look. Image 2 is the raw/source image to transform."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img1}"}},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img2}"}},
                    ],
                }
            ],
            max_completion_tokens=4000,
        )
        return response.choices[0].message.content or "No response text returned."

    if provider == "Gemini":
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name=model_name)

        with Image.open(img1_path) as img1, Image.open(img2_path) as img2:
            pil_img1 = img1.copy()
            pil_img2 = img2.copy()

        contents = [
            prompt,
            "\n[Image 1 / Target Reference]:",
            pil_img1,
            "\n[Image 2 / Raw Source]:",
            pil_img2,
        ]

        response = model.generate_content(contents)
        return getattr(response, "text", "") or "No response text returned."

    raise ValueError(f"Unsupported provider: {provider}")


def looks_like_auth_error(error):
    text = str(error).lower()
    markers = [
        "invalid api key",
        "incorrect api key",
        "api key not valid",
        "expired",
        "unauthorized",
        "unauthenticated",
        "authentication",
        "permission_denied",
        "401",
        "403",
    ]
    return any(marker in text for marker in markers)


class FlatTabSwitch(ctk.CTkFrame):
    def __init__(self, master, items, command, initial_index=0):
        super().__init__(
            master,
            fg_color=APP_BG,
            corner_radius=0,
            border_width=1,
            border_color=BORDER,
        )
        self.items = items
        self.command = command
        self.active_index = initial_index
        self.buttons = []

        for index, label in enumerate(items):
            button = ctk.CTkButton(
                self,
                text=label.upper(),
                height=28,
                corner_radius=0,
                border_width=0,
                font=(FONT_FAMILY, FONT_SIZE),
                text_color=TEXT_PRIMARY if index == initial_index else TEXT_MUTED,
                fg_color=CONTROL_ACTIVE if index == initial_index else APP_BG,
                hover_color=CONTROL_HOVER,
                command=lambda i=index: self.select(i),
            )
            button.grid(row=0, column=index, sticky="ew")
            self.grid_columnconfigure(index, weight=1)
            self.buttons.append(button)

    def select(self, index):
        if index == self.active_index:
            return
        self.active_index = index
        for button_index, button in enumerate(self.buttons):
            active = button_index == index
            button.configure(
                fg_color=CONTROL_ACTIVE if active else APP_BG,
                text_color=TEXT_PRIMARY if active else TEXT_MUTED,
            )
        if callable(self.command):
            self.command(self.items[index])


class ColorGradeAnalyzerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1440x880")
        self.minsize(1180, 760)
        self.configure(fg_color=APP_BG)
        self.option_add("*Font", f"{FONT_FAMILY} {FONT_SIZE}")
        self.apply_app_icon()

        self.img1_path = ""
        self.img2_path = ""
        self.presets = load_presets()
        self.credential_store = LocalCredentialStore()
        self.saved_keys = self.credential_store.load_keys()
        self.preferences = self.credential_store.load_preferences()
        self.is_running = False

        self.preview_img1 = None
        self.preview_img2 = None

        self.setup_ui()
        self.populate_saved_keys()

    def apply_app_icon(self):
        icon_path = resource_path(LOGO_ICO)
        if icon_path.exists():
            try:
                self.iconbitmap(str(icon_path))
            except Exception:
                pass

    def setup_ui(self):
        self.header = ctk.CTkFrame(
            self,
            fg_color=APP_BG,
            corner_radius=0,
            border_width=0,
            height=42,
        )
        self.header.pack(fill="x", padx=16, pady=(12, 8))
        self.header.pack_propagate(False)

        self.header_logo_image = None
        logo_path = resource_path(LOGO_PNG)
        if logo_path.exists():
            try:
                logo_source = Image.open(logo_path)
                self.header_logo_image = ctk.CTkImage(
                    light_image=logo_source,
                    dark_image=logo_source,
                    size=(30, 30),
                )
                self.header_logo = ctk.CTkLabel(
                    self.header,
                    text="",
                    image=self.header_logo_image,
                    width=30,
                )
                self.header_logo.pack(side="left", padx=(0, 10))
            except Exception:
                self.header_logo_image = None

        self.title_label = ctk.CTkLabel(
            self.header,
            text="GRADEMATCH",
            font=(FONT_FAMILY, FONT_SIZE_TITLE, "bold"),
            text_color=ACCENT,
            anchor="w",
        )
        self.title_label.pack(side="left")

        self.tab_switch = FlatTabSwitch(
            self.header,
            items=("Workspace", "Instructions"),
            command=self.switch_tab,
            initial_index=0,
        )
        self.tab_switch.pack(side="right", fill="x", padx=(16, 0))

        self.tab_container = ctk.CTkFrame(self, fg_color=APP_BG, corner_radius=0, border_width=0)
        self.tab_container.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self.workspace_tab = ctk.CTkFrame(self.tab_container, fg_color=APP_BG, corner_radius=0, border_width=0)
        self.instructions_tab = ctk.CTkFrame(self.tab_container, fg_color=APP_BG, corner_radius=0, border_width=0)
        self.build_workspace_tab(self.workspace_tab)
        self.build_instructions_tab(self.instructions_tab)
        self.active_tab = "Workspace"
        self.workspace_tab.pack(fill="both", expand=True)

    def switch_tab(self, tab_name):
        if tab_name == getattr(self, "active_tab", None):
            return

        current = self.workspace_tab if self.active_tab == "Workspace" else self.instructions_tab
        next_tab = self.workspace_tab if tab_name == "Workspace" else self.instructions_tab
        current.pack_forget()
        next_tab.pack(fill="both", expand=True)
        self.active_tab = tab_name

    def section_label(self, parent, text):
        label = ctk.CTkLabel(
            parent,
            text=text.upper(),
            font=(FONT_FAMILY, FONT_SIZE_SMALL),
            text_color=ACCENT,
            anchor="w",
        )
        label.pack(fill="x", pady=(16, 6))
        return label

    def flat_button(self, parent, text, command, height=32, accent=False):
        return ctk.CTkButton(
            parent,
            text=text.upper(),
            height=height,
            corner_radius=0,
            border_width=1,
            border_color=ACCENT if accent else BORDER,
            font=(FONT_FAMILY, FONT_SIZE),
            text_color=ACCENT if accent else TEXT_PRIMARY,
            text_color_disabled=ACCENT_DIM if accent else TEXT_DIM,
            fg_color=CONTROL_BG,
            hover_color=CONTROL_HOVER,
            command=command,
        )

    def build_workspace_tab(self, parent):
        parent.grid_columnconfigure(0, minsize=264, weight=0)
        parent.grid_columnconfigure(1, weight=1)
        parent.grid_columnconfigure(2, minsize=420, weight=0)
        parent.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(
            parent,
            fg_color=PANEL_BG,
            corner_radius=0,
            border_width=1,
            border_color=BORDER,
            width=264,
        )
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)

        self.center_canvas = ctk.CTkFrame(parent, fg_color=CANVAS_BG, corner_radius=0, border_width=0)
        self.center_canvas.grid(row=0, column=1, sticky="nsew", padx=12)
        self.center_canvas.grid_columnconfigure(0, weight=1)
        self.center_canvas.grid_columnconfigure(1, weight=1)
        self.center_canvas.grid_rowconfigure(1, weight=1)

        self.console = ctk.CTkFrame(
            parent,
            fg_color=PANEL_BG,
            corner_radius=0,
            border_width=1,
            border_color=BORDER,
            width=420,
        )
        self.console.grid(row=0, column=2, sticky="nsew")
        self.console.grid_propagate(False)

        self.build_sidebar(self.sidebar)
        self.build_image_canvas(self.center_canvas)
        self.build_console(self.console)

    def build_sidebar(self, parent):
        inner = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0, border_width=0)
        inner.pack(fill="both", expand=True, padx=14, pady=14)

        self.section_label(inner, "Engine")
        self.provider_menu = ctk.CTkOptionMenu(
            inner,
            values=["ChatGPT", "Gemini"],
            command=self.on_provider_select,
            height=32,
            corner_radius=0,
            font=(FONT_FAMILY, FONT_SIZE),
            dropdown_font=(FONT_FAMILY, FONT_SIZE),
            text_color=TEXT_PRIMARY,
            fg_color=CONTROL_BG,
            button_color=CONTROL_BG,
            button_hover_color=CONTROL_HOVER,
            dropdown_fg_color=SURFACE_BG,
            dropdown_hover_color=CONTROL_HOVER,
            dropdown_text_color=TEXT_PRIMARY,
        )
        self.provider_menu.pack(fill="x")
        preferred_provider = self.preferences.get("provider", "ChatGPT")
        if preferred_provider in MODEL_OPTIONS:
            self.provider_menu.set(preferred_provider)

        self.section_label(inner, "Model")
        selected_provider = self.provider_menu.get()
        self.model_menu = ctk.CTkOptionMenu(
            inner,
            values=list(MODEL_OPTIONS[selected_provider].keys()),
            command=self.on_model_select,
            height=32,
            corner_radius=0,
            font=(FONT_FAMILY, FONT_SIZE_SMALL),
            dropdown_font=(FONT_FAMILY, FONT_SIZE_SMALL),
            text_color=TEXT_PRIMARY,
            fg_color=CONTROL_BG,
            button_color=CONTROL_BG,
            button_hover_color=CONTROL_HOVER,
            dropdown_fg_color=SURFACE_BG,
            dropdown_hover_color=CONTROL_HOVER,
            dropdown_text_color=TEXT_PRIMARY,
        )
        self.model_menu.pack(fill="x")
        preferred_model_label = self.preferences.get("models", {}).get(selected_provider)
        if preferred_model_label in MODEL_OPTIONS[selected_provider]:
            self.model_menu.set(preferred_model_label)

        self.section_label(inner, "Prompt Recipe")
        self.preset_menu = ctk.CTkOptionMenu(
            inner,
            values=list(self.presets.keys()),
            command=self.on_preset_select,
            height=32,
            corner_radius=0,
            font=(FONT_FAMILY, FONT_SIZE_SMALL),
            dropdown_font=(FONT_FAMILY, FONT_SIZE_SMALL),
            text_color=TEXT_PRIMARY,
            fg_color=CONTROL_BG,
            button_color=CONTROL_BG,
            button_hover_color=CONTROL_HOVER,
            dropdown_fg_color=SURFACE_BG,
            dropdown_hover_color=CONTROL_HOVER,
            dropdown_text_color=TEXT_PRIMARY,
        )
        self.preset_menu.pack(fill="x")

        self.section_label(inner, "API Setup")
        self.chatgpt_key_entry = ctk.CTkEntry(
            inner,
            placeholder_text="OPENAI_API_KEY",
            show="*",
            height=32,
            corner_radius=0,
            border_width=1,
            fg_color=CONTROL_BG,
            border_color=BORDER,
            text_color=TEXT_PRIMARY,
            placeholder_text_color=TEXT_DIM,
            font=(FONT_FAMILY, FONT_SIZE_SMALL),
        )
        self.chatgpt_key_entry.pack(fill="x", pady=(0, 8))

        self.gemini_key_entry = ctk.CTkEntry(
            inner,
            placeholder_text="GEMINI_API_KEY",
            show="*",
            height=32,
            corner_radius=0,
            border_width=1,
            fg_color=CONTROL_BG,
            border_color=BORDER,
            text_color=TEXT_PRIMARY,
            placeholder_text_color=TEXT_DIM,
            font=(FONT_FAMILY, FONT_SIZE_SMALL),
        )
        self.gemini_key_entry.pack(fill="x", pady=(0, 10))

        self.save_keys_btn = self.flat_button(inner, "Save Keys", self.save_keys_locally)
        self.save_keys_btn.pack(fill="x", pady=(0, 8))

        self.clear_keys_btn = self.flat_button(inner, "Clear Keys", self.clear_saved_keys)
        self.clear_keys_btn.pack(fill="x")

        self.key_status_label = ctk.CTkLabel(
            inner,
            text="No saved keys loaded.",
            text_color=ACCENT_DIM,
            font=(FONT_FAMILY, FONT_SIZE_SMALL),
            anchor="w",
            wraplength=226,
        )
        self.key_status_label.pack(fill="x", pady=(16, 0))

        self.model_status_label = ctk.CTkLabel(
            inner,
            text="",
            text_color=TEXT_DIM,
            font=(FONT_FAMILY, FONT_SIZE_SMALL),
            justify="left",
            anchor="sw",
        )
        self.model_status_label.pack(side="bottom", fill="x", pady=(16, 0))
        self.update_model_status()

    def build_image_canvas(self, parent):
        title = ctk.CTkLabel(
            parent,
            text="IMAGE PAIR",
            font=(FONT_FAMILY, FONT_SIZE_SMALL),
            text_color=ACCENT,
            anchor="w",
        )
        title.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))

        self.left_canvas_frame = ctk.CTkFrame(
            parent,
            fg_color=CANVAS_BG,
            corner_radius=0,
            border_width=0,
        )
        self.left_canvas_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        self.left_canvas_frame.grid_rowconfigure(0, weight=1)
        self.left_canvas_frame.grid_columnconfigure(0, weight=1)

        self.lbl_img1_preview = ctk.CTkLabel(
            self.left_canvas_frame,
            text="[ IMAGE 1 TARGET ]\nNO MEDIA",
            text_color=ACCENT_DIM,
            font=(FONT_FAMILY, FONT_SIZE),
        )
        self.lbl_img1_preview.grid(row=0, column=0, sticky="nsew")

        self.btn_img1 = self.flat_button(parent, "Load Image 1 / Target", lambda: self.load_image(1))
        self.btn_img1.grid(row=2, column=0, sticky="ew", padx=(0, 8), pady=(10, 0))

        self.right_canvas_frame = ctk.CTkFrame(
            parent,
            fg_color=CANVAS_BG,
            corner_radius=0,
            border_width=0,
        )
        self.right_canvas_frame.grid(row=1, column=1, sticky="nsew", padx=(8, 0))
        self.right_canvas_frame.grid_rowconfigure(0, weight=1)
        self.right_canvas_frame.grid_columnconfigure(0, weight=1)

        self.lbl_img2_preview = ctk.CTkLabel(
            self.right_canvas_frame,
            text="[ IMAGE 2 SOURCE ]\nNO MEDIA",
            text_color=ACCENT_DIM,
            font=(FONT_FAMILY, FONT_SIZE),
        )
        self.lbl_img2_preview.grid(row=0, column=0, sticky="nsew")

        self.btn_img2 = self.flat_button(parent, "Load Image 2 / Source", lambda: self.load_image(2))
        self.btn_img2.grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=(10, 0))

    def build_console(self, parent):
        inner = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0, border_width=0)
        inner.pack(fill="both", expand=True, padx=14, pady=14)

        self.section_label(inner, "Prompt")
        self.prompt_textbox = ctk.CTkTextbox(
            inner,
            height=220,
            border_width=1,
            border_color=BORDER,
            corner_radius=0,
            fg_color=CONTROL_BG,
            text_color=TEXT_BODY,
            font=(FONT_FAMILY, FONT_SIZE_SMALL),
            scrollbar_button_color=CONTROL_HOVER,
            scrollbar_button_hover_color="#2a2a2a",
            wrap="word",
        )
        self.prompt_textbox.pack(fill="x")
        self.prompt_textbox.insert("1.0", self.presets[self.preset_menu.get()])

        self.section_label(inner, "Preset Save")
        self.new_preset_entry = ctk.CTkEntry(
            inner,
            placeholder_text="NEW PRESET NAME",
            height=32,
            corner_radius=0,
            border_width=1,
            fg_color=CONTROL_BG,
            border_color=BORDER,
            text_color=TEXT_BODY,
            placeholder_text_color=TEXT_DIM,
            font=(FONT_FAMILY, FONT_SIZE_SMALL),
        )
        self.new_preset_entry.pack(fill="x", pady=(0, 8))

        self.save_preset_btn = self.flat_button(inner, "Save Custom Preset", self.save_custom_preset)
        self.save_preset_btn.pack(fill="x")

        self.process_btn = self.flat_button(inner, RUN_BUTTON_TEXT, self.start_analysis, height=38, accent=True)
        self.process_btn.pack(fill="x", pady=(16, 0))

        self.section_label(inner, "Markdown Output")
        self.output_textbox = ctk.CTkTextbox(
            inner,
            corner_radius=0,
            font=(FONT_FAMILY, FONT_SIZE),
            fg_color=CONTROL_BG,
            text_color=TEXT_BODY,
            border_width=1,
            border_color=BORDER,
            scrollbar_button_color=CONTROL_HOVER,
            scrollbar_button_hover_color="#2a2a2a",
            wrap="word",
        )
        self.output_textbox.pack(fill="both", expand=True)
        self.output_textbox.insert("1.0", "Analysis output will appear here.")

    def build_instructions_tab(self, parent):
        instructions_frame = ctk.CTkFrame(
            parent,
            fg_color=PANEL_BG,
            border_width=1,
            border_color=BORDER,
            corner_radius=0,
        )
        instructions_frame.pack(fill="both", expand=True)

        title = ctk.CTkLabel(
            instructions_frame,
            text="HOW TO USE GRADEMATCH",
            font=(FONT_FAMILY, FONT_SIZE_TITLE, "bold"),
            text_color=TEXT_BODY,
            anchor="w",
        )
        title.pack(anchor="w", padx=16, pady=(16, 8))

        self.instructions_textbox = ctk.CTkTextbox(
            instructions_frame,
            corner_radius=0,
            font=(FONT_FAMILY, FONT_SIZE),
            fg_color=CONTROL_BG,
            text_color=TEXT_BODY,
            border_width=1,
            border_color=BORDER,
            scrollbar_button_color=CONTROL_HOVER,
            scrollbar_button_hover_color="#2a2a2a",
            wrap="word",
        )
        self.instructions_textbox.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self.instructions_textbox.insert("1.0", INSTRUCTIONS_TEXT)
        self.instructions_textbox.configure(state="disabled")

    def on_provider_select(self, provider):
        if hasattr(self, "model_menu"):
            model_labels = list(MODEL_OPTIONS[provider].keys())
            self.model_menu.configure(values=model_labels)
            preferred_model_label = self.preferences.get("models", {}).get(provider)
            self.model_menu.set(preferred_model_label if preferred_model_label in model_labels else model_labels[0])
        self.save_model_preferences()
        self.update_model_status()

    def on_model_select(self, _choice=None):
        self.save_model_preferences()
        self.update_model_status()

    def get_selected_model(self, provider=None):
        provider = provider or self.provider_menu.get()
        model_label = self.model_menu.get()
        return MODEL_OPTIONS.get(provider, {}).get(model_label, "")

    def save_model_preferences(self):
        if not hasattr(self, "provider_menu") or not hasattr(self, "model_menu"):
            return
        provider = self.provider_menu.get()
        preferences = dict(self.preferences)
        models = dict(preferences.get("models", {}))
        models[provider] = self.model_menu.get()
        preferences["provider"] = provider
        preferences["models"] = models
        self.preferences = preferences
        self.credential_store.save_preferences(preferences)

    def update_model_status(self):
        if not hasattr(self, "model_status_label") or not hasattr(self, "model_menu"):
            return
        provider = self.provider_menu.get()
        model_id = self.get_selected_model(provider)
        self.model_status_label.configure(text=f"ACTIVE MODEL\n{provider.upper()}  {model_id}")

    def populate_saved_keys(self):
        chatgpt_key = self.saved_keys.get("ChatGPT") or os.getenv("OPENAI_API_KEY", "").strip()
        gemini_key = (
            self.saved_keys.get("Gemini")
            or os.getenv("GOOGLE_API_KEY", "").strip()
            or os.getenv("GEMINI_API_KEY", "").strip()
        )

        if chatgpt_key:
            self.chatgpt_key_entry.delete(0, "end")
            self.chatgpt_key_entry.insert(0, chatgpt_key)
        if gemini_key:
            self.gemini_key_entry.delete(0, "end")
            self.gemini_key_entry.insert(0, gemini_key)

        saved_count = len(self.saved_keys)
        if saved_count:
            self.key_status_label.configure(text=f"{saved_count} saved key(s) loaded.", text_color=SUCCESS)
        else:
            self.key_status_label.configure(text="No saved keys loaded.", text_color=ACCENT_DIM)

    def save_keys_locally(self):
        keys = {
            "ChatGPT": self.chatgpt_key_entry.get().strip(),
            "Gemini": self.gemini_key_entry.get().strip(),
        }
        if not any(keys.values()):
            messagebox.showwarning("No Keys", "Enter at least one API key before saving.")
            return

        self.credential_store.save_keys(keys)
        self.saved_keys = self.credential_store.load_keys()
        self.key_status_label.configure(text="Credentials encrypted and saved locally.", text_color=SUCCESS)
        self.after(3500, self.populate_saved_keys)

    def clear_saved_keys(self):
        if not messagebox.askyesno("Clear Saved Keys", "Remove all saved local API keys from this machine?"):
            return
        self.credential_store.clear_all()
        self.saved_keys = {}
        self.chatgpt_key_entry.delete(0, "end")
        self.gemini_key_entry.delete(0, "end")
        self.key_status_label.configure(text="Saved keys cleared.", text_color=ACCENT_DIM)

    def clear_provider_key_after_auth_failure(self, provider):
        self.credential_store.clear_provider(provider)
        self.saved_keys = self.credential_store.load_keys()
        if provider == "ChatGPT":
            self.chatgpt_key_entry.delete(0, "end")
        elif provider == "Gemini":
            self.gemini_key_entry.delete(0, "end")
        self.key_status_label.configure(text=f"{provider} saved key was cleared.", text_color=DANGER)
        messagebox.showwarning(
            "Saved Key Cleared",
            f"The saved {provider} API key appears invalid or expired. It was removed. Enter a fresh key and save again.",
        )

    def get_provider_key(self, provider):
        if provider == "ChatGPT":
            key = self.chatgpt_key_entry.get().strip()
            source = "saved" if key and key == self.saved_keys.get("ChatGPT") else "entry"
            return key, source
        if provider == "Gemini":
            key = self.gemini_key_entry.get().strip()
            source = "saved" if key and key == self.saved_keys.get("Gemini") else "entry"
            return key, source
        return "", "missing"

    def on_preset_select(self, choice):
        self.prompt_textbox.delete("1.0", "end")
        self.prompt_textbox.insert("1.0", self.presets[choice])

    def save_custom_preset(self):
        preset_name = self.new_preset_entry.get().strip()
        current_prompt = self.prompt_textbox.get("1.0", "end-1c").strip()

        if not preset_name:
            messagebox.showwarning("Name Required", "Please input a name for your custom preset sequence.")
            return
        if not current_prompt:
            messagebox.showwarning("Prompt Empty", "Cannot save an empty prompt system field.")
            return

        self.presets[preset_name] = current_prompt
        save_presets_to_file(self.presets)

        self.preset_menu.configure(values=list(self.presets.keys()))
        self.preset_menu.set(preset_name)
        self.new_preset_entry.delete(0, "end")
        messagebox.showinfo("Success", f"Custom preset '{preset_name}' successfully built.")

    def generate_scaled_preview(self, filepath, max_w=340, max_h=620):
        with Image.open(filepath) as raw_img:
            original_w, original_h = raw_img.size
            ratio = min(max_w / original_w, max_h / original_h)
            new_w = max(1, int(original_w * ratio))
            new_h = max(1, int(original_h * ratio))

            pil_resized = raw_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            return ctk.CTkImage(
                light_image=pil_resized,
                dark_image=pil_resized,
                size=(new_w, new_h),
            )

    def load_image(self, index):
        path = filedialog.askopenfilename(
            filetypes=[
                ("Image Files", "*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff *.heic"),
                ("All Files", "*.*"),
            ]
        )
        if path:
            try:
                preview_ctk = self.generate_scaled_preview(path)

                if index == 1:
                    self.img1_path = path
                    self.preview_img1 = preview_ctk
                    self.lbl_img1_preview.configure(image=self.preview_img1, text="")
                else:
                    self.img2_path = path
                    self.preview_img2 = preview_ctk
                    self.lbl_img2_preview.configure(image=self.preview_img2, text="")
            except Exception as exc:
                messagebox.showerror("Preview Error", f"Could not draw visual thumbnail matrix: {str(exc)}")

    def start_analysis(self):
        if self.is_running:
            return

        provider = self.provider_menu.get()
        api_key, key_source = self.get_provider_key(provider)
        model_name = self.get_selected_model(provider)
        active_prompt = self.prompt_textbox.get("1.0", "end-1c").strip()

        if not api_key:
            self.set_output(
                "Error: Missing API key. Paste a key, save it locally, or set OPENAI_API_KEY / GOOGLE_API_KEY."
            )
            return
        if not self.img1_path or not self.img2_path:
            self.set_output("Error: Please select both Image 1 and Image 2 before processing.")
            return

        self.is_running = True
        self.process_btn.configure(state="disabled", text="PROCESSING...")
        self.set_output(f"PROCESSING\nCalling {provider} with {model_name}.\n")

        worker_thread = threading.Thread(
            target=self.async_process_worker,
            args=(provider, api_key, key_source, model_name, active_prompt, self.img1_path, self.img2_path),
            daemon=True,
        )
        worker_thread.start()

    def async_process_worker(self, provider, api_key, key_source, model_name, active_prompt, img1_path, img2_path):
        try:
            analysis_result = call_ai_engine(
                provider=provider,
                api_key=api_key,
                model_name=model_name,
                prompt=active_prompt,
                img1_path=img1_path,
                img2_path=img2_path,
            )
            self.safe_ui_update(analysis_result)
        except Exception as err:
            auth_failed = looks_like_auth_error(err)
            self.safe_ui_update(
                f"Engine error encountered:\n\n{str(err)}",
                is_error=True,
                provider=provider if auth_failed and key_source == "saved" else None,
            )

    def safe_ui_update(self, text, is_error=False, provider=None):
        self.after(0, lambda: self._ui_update_main_thread(text, is_error, provider))

    def _ui_update_main_thread(self, text, is_error, provider):
        self.set_output(text)
        self.process_btn.configure(state="normal", text=RUN_BUTTON_TEXT)
        self.is_running = False
        if provider:
            self.clear_provider_key_after_auth_failure(provider)
        elif is_error:
            messagebox.showerror("Execution Fault", "The target engine raised a runtime exception.")
        else:
            self.open_output_in_notepad(text)

    def set_output(self, text):
        self.output_textbox.delete("1.0", "end")
        self.output_textbox.insert("end", text)

    def open_output_in_notepad(self, text):
        if os.name != "nt":
            return
        try:
            output_file = Path(tempfile.gettempdir()) / "GradeMatch_latest_output.txt"
            output_file.write_text(text, encoding="utf-8")
            subprocess.Popen(["notepad.exe", str(output_file)], close_fds=True)
        except Exception as exc:
            self.key_status_label.configure(text=f"Could not open Notepad: {exc}", text_color=DANGER)


if __name__ == "__main__":
    app = ColorGradeAnalyzerApp()
    app.mainloop()
