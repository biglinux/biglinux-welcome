<h1 align="center">BigLinux Welcome</h1>

<p align="center">
  <em>In search of the perfect system!</em>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#installation">Installation</a> •
  <a href="#project-structure">Project Structure</a> •
  <a href="#translations">Translations</a> •
  <a href="#contributing">Contributing</a> •
  <a href="#license">License</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/GTK-4-blue?logo=gnome&logoColor=white" alt="GTK4">
  <img src="https://img.shields.io/badge/Python-3.10%2B-yellow?logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/Adwaita-libadwaita-purple" alt="Adwaita">
  <img src="https://img.shields.io/badge/license-GPL-green" alt="License GPL">
  <img src="https://img.shields.io/badge/translations-28_languages-orange" alt="28 Languages">
</p>

---

## About

**BigLinux Welcome** is a guided setup and feature discovery application for [BigLinux](https://www.biglinux.com.br). It launches on the first login to help users configure their new system, choose a default browser, discover built-in tools, and connect with the community — all through a clean, modern GTK4/libadwaita interface.

## Features

- **Step-by-step guided setup** — walks the user through essential configuration pages
- **Browser selection & install** — choose from 10 supported browsers; install missing ones with real-time progress
- **KDE Connect integration** — QR codes for quick mobile pairing (Android & iOS)
- **Driver & hardware tools** — quick access to driver manager, kernel manager, and hardware info
- **Feature discovery** — introduces BigLinux-exclusive tools (Big Store, WebApps, Noise Reduction, OCR, and more)
- **Community & donation links** — forum, YouTube, Telegram, and donation page
- **Autostart control** — checkbox to enable/disable the app on login via systemd user service
- **Keyboard & screen reader accessible** — `:focus-visible` indicators and ARIA roles for Orca compatibility
- **YAML-driven pages** — add, remove, or reorder pages by editing a single `pages.yaml` file
- **Internationalized** — 28 languages with automated translation pipeline via GitHub Actions

## Installation

### From BigLinux repositories (recommended)

```bash
sudo pacman -S biglinux-welcome
```

### Manual build (Arch-based distros)

```bash
cd pkgbuild
makepkg -si
```

### Dependencies

| Package        | Purpose                    |
|----------------|----------------------------|
| `gtk4`         | UI toolkit                 |
| `python`       | Runtime (≥ 3.10)           |
| `python-yaml`  | YAML page configuration    |
| `python-gobject`| GTK4 Python bindings      |
| `polkit`       | Privilege elevation        |
| `zenity`       | Auxiliary dialogs          |

## Project Structure

```
biglinux-welcome/
├── usr/
│   ├── bin/
│   │   └── biglinux-welcome              # launcher script
│   ├── lib/systemd/user/
│   │   └── biglinux-welcome.service      # autostart unit
│   └── share/
│       ├── applications/
│       │   └── org.biglinux.welcome.desktop
│       ├── biglinux/welcome/
│       │   ├── main.py                   # entry point
│       │   ├── app.py                    # Adw.Application + CSS
│       │   ├── window.py                 # main window & navigation
│       │   ├── widgets.py                # custom GTK4 widgets
│       │   ├── utils.py                  # shared utilities
│       │   ├── style.css                 # Adwaita-based styles
│       │   ├── pages.yaml                # page definitions
│       │   ├── translatable_strings.py   # auto-generated for gettext
│       │   ├── scripts/                  # shell helpers
│       │   └── image/                    # SVG icons per category
│       ├── icons/hicolor/scalable/apps/
│       │   └── biglinux-welcome.svg
│       └── locale/                       # compiled .mo translations
├── locale/                               # source .po translation files
├── pkgbuild/
│   ├── PKGBUILD                          # Arch package build
│   └── biglinux-welcome.install          # post-install hooks
├── generate_strings.py                   # extracts translatable strings from YAML
├── tests/                                # unit tests (pytest)
└── .github/workflows/
    └── translate-and-build-package.yml   # CI: auto-translate & build
```

## Translations

The project supports **28 languages** with an automated translation pipeline:

1. Translatable strings are extracted from `pages.yaml` → `translatable_strings.py`
2. Source strings are collected into `locale/biglinux-welcome.pot`
3. A GitHub Actions workflow auto-translates into all target languages
4. Compiled `.mo` files are deployed under `usr/share/locale/`

**Supported languages:** Bulgarian, Czech, Danish, German, Greek, English, Spanish, Estonian, Finnish, French, Hebrew, Croatian, Hungarian, Icelandic, Italian, Japanese, Korean, Dutch, Norwegian, Polish, Portuguese, Romanian, Russian, Slovak, Swedish, Turkish, Ukrainian, Chinese.

### Adding a new language

1. Create a new `.po` file in `locale/` (e.g., `locale/vi.po`)
2. The CI pipeline will handle translation and compilation automatically

## Development

### Running locally

```bash
cd usr/share/biglinux/welcome
python main.py
```

### Running tests

```bash
pip install pytest
python -m pytest tests/ -v
```

### Code quality

```bash
pip install ruff
ruff check usr/share/biglinux/welcome/
ruff format usr/share/biglinux/welcome/
```

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make your changes
4. Run the tests (`python -m pytest tests/ -v`)
5. Commit and push
6. Open a Pull Request

## Community

- 🌐 **Website:** [biglinux.com.br](https://www.biglinux.com.br)
- 💬 **Forum:** [forum.biglinux.com.br](https://forum.biglinux.com.br)
- 📺 **YouTube:** [@BigLinuxx](https://www.youtube.com/@BigLinuxx)
- ✈️ **Telegram:** [t.me/biglinux](https://t.me/biglinux)
- ❤️ **Donate:** [biglinux.com.br/doacao-financeira](https://www.biglinux.com.br/doacao-financeira/)

## License

This project is licensed under the **GPL** license. See the [PKGBUILD](pkgbuild/PKGBUILD) for details.
