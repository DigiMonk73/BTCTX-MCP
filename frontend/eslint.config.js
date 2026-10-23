import js from '@eslint/js'
import { defineConfig, globalIgnores } from 'eslint/config'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'

// An account is asked of the account book, never by its number (2.0 spec 5.4,
// 5.16): 1 to 4 are only the first bank, wallet and exchange, which can be
// renamed, hidden and joined by others. External (99) and the fee accounts
// (5, 6) stay fixed ids. An account id is a name with "account" in it, `id`,
// or one ending in `Id` or `_id`; Literal's `raw`, since esquery matches a
// pattern only against text.
const ACCOUNT_ID = '/[Aa]ccount|^id$|Id$|_id$/'
const ONE_TO_FOUR = "[raw=/^[1-4]$/]"
const NAMED = (side) => `:matches([${side}.name=${ACCOUNT_ID}], [${side}.property.name=${ACCOUNT_ID}])`
const BY_NUMBER = 'An account id compared with 1, 2, 3 or 4: ask the account book instead '
  + '(src/utils/accounts.ts: accountKind, isBtcAccount, accountCurrency…), 2.0 spec 5.4.'
const NO_ACCOUNT_BY_NUMBER = [
  { selector: `BinaryExpression[operator=/^[!=]==?$/][right.type='Literal'][right.raw=/^[1-4]$/]${NAMED('left')}`,
    message: BY_NUMBER },
  { selector: `BinaryExpression[operator=/^[!=]==?$/][left.type='Literal'][left.raw=/^[1-4]$/]${NAMED('right')}`,
    message: BY_NUMBER },
  { selector: `SwitchStatement${NAMED('discriminant')} > SwitchCase > Literal.test${ONE_TO_FOUR}`,
    message: BY_NUMBER },
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
      // 2.0's reworked screens, not a version upgrade (#425; the React 19
      // upgrade kept it off too, since the fix changes how the screens
      // behave); the other new checks stay on.
      'react-hooks/set-state-in-effect': 'off',
      'react-refresh/only-export-components': [
        'warn',
        { allowConstantExport: true },
      ],
      // Past these, divide the function or file (docs/CODE_STYLE.md)
      complexity: ['error', 15],
      'max-lines': ['error', 400],
      'no-restricted-syntax': ['error', ...NO_ACCOUNT_BY_NUMBER],
    },
  },
  {
    // A test scenario can be long, and its account books are numbered.
    files: ['src/**/*.test.ts'],
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
