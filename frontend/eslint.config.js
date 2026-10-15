import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { ignores: ['dist', 'playwright-report', 'test-results'] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ['src/**/*.{ts,tsx}', '*.ts'],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': [
        'warn',
        { allowConstantExport: true },
      ],
      // Past these, divide the function or file (docs/CODE_STYLE.md)
      complexity: ['error', 15],
      'max-lines': ['error', 400],
    },
  },
  {
    // A test scenario can be long.
    files: ['src/**/*.test.ts'],
    rules: { complexity: 'off', 'max-lines': 'off' },
  },
  {
    // Playwright end-to-end tests: Node, no React.
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ['e2e/**/*.ts'],
    languageOptions: {
      ecmaVersion: 2022,
      globals: { ...globals.node, ...globals.browser },
    },
    // Interception turned off mid-test loses a request the browser paused in
    // that moment (#275): a `times` route as it expires, or an unroute
    rules: {
      'no-restricted-syntax': ['error', {
        selector: "CallExpression[callee.property.name='route'] > ObjectExpression > "
          + ":matches(Property[key.name='times'], Property[key.value='times'])",
        message: "A route with `times` turns Playwright's interception off as it expires, and a request "
          + 'made in that moment never goes out (#275): keep one route for the test, route.fallback() once done.',
      }, {
        selector: "CallExpression[callee.property.name=/^unroute(All)?$/]",
        message: "An unroute turns Playwright's interception off, and a request made in that moment never "
          + 'goes out (#275): keep the route for the test, route.fallback() once done.',
      }],
    },
  },
)
