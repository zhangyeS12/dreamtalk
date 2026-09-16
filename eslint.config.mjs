import js from "@eslint/js";
import tseslint from "typescript-eslint";
import globals from "globals";

export default tseslint.config(
  { ignores: ["**/dist/**", "**/target/**", ".venv/**", ".cache/**"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  { files: ["**/*.{ts,tsx}"], languageOptions: { globals: globals.browser } },
  { files: ["**/*.mjs"], languageOptions: { globals: globals.node } },
);
