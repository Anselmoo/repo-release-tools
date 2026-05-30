Icons and typography guidance for repo-release-tools docs

Overview
- This folder contains placeholder guidance for language icons used across README and docs.
- SVG assets are not fetched automatically (user opted out). Use the Simple-Icons repository to manually fetch icons: https://github.com/simple-icons/simple-icons/tree/develop/icons

Requested icons
- zsh
- ts (TypeScript)
- rust
- python
- nuget
- go
- markdown
- rst
- txt
- js (JavaScript)
- java

Procurement
- Clone or browse the simple-icons repo and copy the desired `*.svg` files into this folder with kebab-case names (e.g. `simpleicon-python.svg` → `python.svg`).
- Prefer optimized SVGs (remove metadata and inline styles) and keep each icon at viewBox `0 0 24 24`.

Typography / "Repo Tool" style (Azure-DevOps-inspired)
- Font stack: `Segoe UI, Roboto, Helvetica, Arial, sans-serif`
- Badge shape: circular background token with centered 2-letter uppercase abbreviation (e.g., `JV` for Java). Circle radius: 11 (viewBox 24x24)
- Sizes: badge height 20px (display inline-block tile), icon inside scaled to fit with 2px padding.
- Color tokens (examples):
  - Java: #E76F51
  - Python: #3776AB
  - Rust: #DEA584
  - TypeScript: #3178C6
  - Go: #00ADD8
  - JavaScript: #F7DF1E (use dark text on light background)
  - NuGet: #512BD4

SVG emblem example (pseudo):

<!-- Background circle -->
<circle cx="12" cy="12" r="11" fill="#E76F51" />
<!-- Text abbreviation -->
<text x="12" y="15.5" font-family="Segoe UI, Helvetica, Arial, sans-serif" font-size="10" font-weight="bold" fill="#FFFFFF" text-anchor="middle">JV</text>

Usage notes
- Add badges to README and site header as small inline images (shields.io for live badges, local SVGs for custom icons).
- If automation is desired later, write a small script to pull icons from simple-icons and normalise coloring and file names.
