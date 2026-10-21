import js from '@eslint/js'
import { defineConfig, globalIgnores } from 'eslint/config'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'

// Spec 5.4: an account is found by its id from the book, never by a fixed number;
// and its name is the owner's nickname, shown, never compared (Rick, 2026-10-20)
const ACCOUNT_ID = '/^(id|.*(account_id|AccountId|accountId))$/'
const COMPARED = 'BinaryExpression[operator=/^[!=]==?$/]'
const ONE_TO_FOUR = (side) => `:matches([${side}.value=1], [${side}.value=2], [${side}.value=3], [${side}.value=4])`
const AN_ID = (side) => `:matches([${side}.name=${ACCOUNT_ID}], [${side}.property.name=${ACCOUNT_ID}])`
const NO_FIXED_ID = 'An account is found by its id from the book (utils/accounts.ts), never by a fixed number (spec 5.4).'
const NO_NAME = "An account's name is the owner's nickname: show it, never compare it (Rick, 2026-10-20)."
const ACCOUNT_RULES = [
  { selector: `${COMPARED}${AN_ID('left')}[right.type='Literal']${ONE_TO_FOUR('right')}`, message: NO_FIXED_ID },
  { selector: `${COMPARED}${AN_ID('right')}[left.type='Literal']${ONE_TO_FOUR('left')}`, message: NO_FIXED_ID },
  {
    selector: `SwitchStatement${AN_ID('discriminant')} > SwitchCase[test.type='Literal']${ONE_TO_FOUR('test')}`,
    message: NO_FIXED_ID,
  },
  { selector: `${COMPARED}[left.property.name='name'][right.type='Literal'][right.raw=/^["']/]`, message: NO_NAME },
  { selector: `${COMPARED}[right.property.name='name'][left.type='Literal'][left.raw=/^["']/]`, message: NO_NAME },
]

export default defineConfig(
  globalIgnores(['dist', 'playwright-report', 'test-results']),
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
      // One of react-hooks 7's React Compiler checks, off: the screens set
      // state from an effect, to load their data and to reset or derive
      // state when something changes (nine places). Rewriting that is for
      // 2.0's screens with React 19 (docs/MAINTENANCE.md, "Deferred
      // upgrades"), not a tools upgrade (#425); the other new checks stay on.
      'react-hooks/set-state-in-effect': 'off',
      'react-refresh/only-export-components': [
        'warn',
        { allowConstantExport: true },
      ],
      // Past these, divide the function or file (docs/CODE_STYLE.md)
      complexity: ['error', 15],
      'max-lines': ['error', 400],
      'no-restricted-syntax': ['error', ...ACCOUNT_RULES],
    },
  },
  {
    // A test scenario can be long, and so can the helpers that mount one (src/test).
    // Their fixtures name accounts by id on purpose (the shared books), so 5.4's rule is the app's only.
    files: ['src/**/*.test.ts', 'src/**/*.test.tsx', 'src/test/**'],
    rules: { complexity: 'off', 'max-lines': 'off', 'no-restricted-syntax': 'off' },
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
