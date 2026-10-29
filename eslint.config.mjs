import js from "@eslint/js";
import tseslint from "typescript-eslint";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";

export default tseslint.config(
  { ignores: ["**/dist/**", "**/target/**", ".venv/**", ".cache/**"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  { files: ["**/*.{ts,tsx}"], languageOptions: { globals: globals.browser } },
  // Only the classic hook rules; the plugin's React Compiler rules are a separate decision.
  // Older views deliberately depend on single fields and bump request counters in
  // cleanups, so missing dependencies there are warnings; the new view layer is strict.
  {
    files: ["**/*.{ts,tsx}"],
    plugins: { "react-hooks": reactHooks },
    rules: { "react-hooks/rules-of-hooks": "error", "react-hooks/exhaustive-deps": "warn" },
  },
  {
    files: ["apps/web/src/world/**/*.{ts,tsx}", "apps/web/src/WorldShelf.tsx", "apps/web/src/WorldArchivePage.tsx",
      "apps/web/src/ChatTranscript.tsx", "apps/web/src/GroupChat.tsx", "apps/web/src/StreamingReplyBubble.tsx"],
    rules: { "react-hooks/exhaustive-deps": "error" },
  },
  { files: ["**/*.mjs"], languageOptions: { globals: globals.node } },
);
