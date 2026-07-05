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
    }),
  ],
});
