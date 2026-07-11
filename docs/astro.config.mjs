// @ts-check
import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";

// https://astro.build/config
export default defineConfig({
  // Must exactly match docs/_config.yml's `url:`/`baseurl:` (Jekyll) so
  // absolute links keep working once the site is served from GitHub Pages.
  site: "https://anselmoo.github.io",
  base: "/repo-release-tools",
  outDir: "./dist",
  integrations: [
    starlight({
      title: "repo-release-tools",

      // Reto design-system token stylesheet (fonts/colors/spacing/effects)
      // ported in Task 2, plus the Starlight `--sl-*` -> `--reto-*` bridge
      // that re-skins the Starlight-native chrome we deliberately keep
      // (CodeBlock/Expressive Code, Pagefind search, table of contents,
      // theme select) without full component overrides.
      customCss: ["./src/styles/reto.css", "./src/styles/starlight-bridge.css"],

      // Sidebar top-level groups mirror docs/_layouts/default.html:38-45's
      // 8-link top nav (Action / CLI / Version / Health / Git / Setup /
      // MCP / Agents), but as real collapsible groups instead of a flat nav
      // bar. The CLI group collects the many individual `rrt <cmd>` pages
      // into a collapsed subgroup so they don't dominate the sidebar. Two
      // extra groups (CI & Automation, Design System) cover real pages that
      // exist under src/content/docs/ but had no top-nav slot in Jekyll.
      sidebar: [
        {
          label: "Action",
          link: "action",
        },
        {
          label: "CLI",
          items: [
            { label: "rrt CLI", link: "commands/rrt-cli" },
            {
              label: "Commands",
              collapsed: true,
              items: [
                { label: "rrt branch", link: "commands/branch" },
                { label: "rrt doctor", link: "commands/doctor" },
                { label: "rrt eol", link: "commands/eol_check" },
                { label: "rrt git", link: "commands/git_cmd" },
                { label: "rrt hooks", link: "commands/hooks" },
                { label: "rrt install", link: "commands/install" },
                { label: "rrt skill", link: "commands/skill" },
                { label: "rrt tree", link: "commands/tree" },
              ],
            },
          ],
        },
        {
          label: "Version & Release",
          link: "commands/version-release",
        },
        {
          label: "Repository Health",
          link: "commands/repo-health",
        },
        {
          label: "Git Workflow",
          link: "commands/git-workflow",
        },
        {
          label: "Setup & Tooling",
          link: "commands/setup-tooling",
        },
        {
          label: "CI & Automation",
          link: "commands/ci-automation",
        },
        {
          label: "MCP",
          link: "mcp-server",
        },
        {
          label: "Agent Instructions",
          link: "agent-instructions",
        },
        {
          label: "Design System",
          link: "design-system",
        },
        {
          label: "Internal Contracts",
          link: "reference/internal-contracts",
        },
      ],

      // Component overrides: Header/Sidebar use the native Task 2 `.astro`
      // components via a thin adapter (Starlight overrides receive no
      // props — they read `Astro.locals.starlightRoute` instead, so the
      // adapters translate that route data into the `links`/`groups` shape
      // the Task 2 components expect). ThemeSelect keeps Starlight's own
      // component (and its `data-theme` FOUC-safe script) and is re-skinned
      // purely via the `starlight-bridge.css` custom-property bridge above
      // — see design-system.mdx's ThemeToggle visual reference. Footer
      // wraps Starlight's own default footer and appends the two
      // disclaimer paragraphs ported verbatim from the old Jekyll layout.
      //
      // Deliberately NOT overridden (re-skinned via CSS only, per the
      // brief): TableOfContents, CodeBlock/Expressive Code, Search/Pagefind.
      components: {
        Header: "./src/components/overrides/Header.astro",
        Sidebar: "./src/components/overrides/Sidebar.astro",
        Footer: "./src/components/overrides/Footer.astro",
      },

      // Ported as-is from docs/_includes/custom-head.html (lines 1-3, 6):
      // Google Fonts CDN preconnects + stylesheet link (kept per the locked
      // no-@fontsource decision), and the Context7 chat widget script.
      // Line 4 (reto.css link) is superseded by `customCss` above; line 5
      // (theme-toggle.js) is dropped — Starlight's native ThemeSelect
      // replaces that cycle logic.
      head: [
        {
          tag: "link",
          attrs: { rel: "preconnect", href: "https://fonts.googleapis.com" },
        },
        {
          tag: "link",
          attrs: { rel: "preconnect", href: "https://fonts.gstatic.com", crossorigin: true },
        },
        {
          tag: "link",
          attrs: {
            rel: "stylesheet",
            href: "https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,400;0,500;0,600;1,400&family=JetBrains+Mono:ital,wght@0,400;0,500;1,400&family=Orbitron:wght@400;500;600;700;800;900&display=swap",
          },
        },
        {
          tag: "script",
          attrs: {
            async: true,
            src: "https://context7.com/widget.js",
            "data-library": "/anselmoo/repo-release-tools",
            "data-color": "#b65e13",
            "data-position": "bottom-right",
            "data-placeholder": "Ask about releases, docs, or workflows",
          },
        },
      ],

      // Replaces the hardcoded Jekyll footer GitHub link (pyproject.toml's
      // `source_repo_url` / `_layouts/default.html`'s footer anchor).
      social: [
        {
          icon: "github",
          label: "GitHub",
          href: "https://github.com/Anselmoo/repo-release-tools",
        },
      ],
    }),
  ],
});
