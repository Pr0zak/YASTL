import js from '@eslint/js';
import pluginVue from 'eslint-plugin-vue';

export default [
  js.configs.recommended,
  ...pluginVue.configs['flat/recommended'],
  {
    rules: {
      // Relax rules for codebase style
      'vue/multi-word-component-names': 'off',
      'vue/no-v-html': 'off', // We use v-html for SVG icons
      'no-unused-vars': ['warn', {
        argsIgnorePattern: '^_',
        caughtErrorsIgnorePattern: '^_|^e$|^err$',
      }],
      'vue/require-default-prop': 'off',
      'vue/require-prop-types': 'off',
      'vue/max-attributes-per-line': 'off',
      'vue/singleline-html-element-content-newline': 'off',
      'vue/html-self-closing': 'off',
      // Formatting rules — project uses 4-space indent and camelCase props/events
      'vue/html-indent': 'off',
      'vue/attribute-hyphenation': 'off',
      'vue/v-on-event-hyphenation': 'off',
      'vue/attributes-order': 'off',
      'vue/first-attribute-linebreak': 'off',
      'vue/html-closing-bracket-newline': 'off',
      'vue/html-closing-bracket-spacing': 'off',
      'vue/multiline-html-element-content-newline': 'off',
      'vue/prop-name-casing': 'off',
    },
  },
  {
    ignores: ['dist/'],
  },
];
