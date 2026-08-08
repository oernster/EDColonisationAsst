/**
 * Flat ESLint configuration for the front end.
 *
 * There was no ESLint configuration here at all until this file. `npm run
 * lint` was defined in package.json and had failed since ESLint 9 made flat
 * config the only format, so the front end appeared in no lint report because
 * nothing had ever checked it, not because it was clean.
 *
 * Composed only from the plugins already in devDependencies. In particular it
 * does NOT pull in `@eslint/js`, which is present in node_modules only as an
 * ESLint transitive: importing it would mean declaring a new dependency and
 * relocking. The handful of core rules worth having are listed explicitly at
 * the bottom instead, each with a reason.
 *
 * Linting is deliberately NOT type-aware. `tsc --noEmit` already runs strict
 * over the same files and is the better tool for anything needing types; a
 * type-aware ESLint pass would also choke on the test files, which
 * tsconfig.json excludes from the program.
 */

import tsPlugin from '@typescript-eslint/eslint-plugin'
import tsParser from '@typescript-eslint/parser'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'

export default [
  {
    ignores: [
      'dist/**',
      'coverage/**',
      'node_modules/**',
      // A standalone GameGlass shard payload: plain browser JS served as a
      // static asset, outside the React build and outside tsconfig's program.
      'src/gameglass/**',
    ],
  },

  ...tsPlugin.configs['flat/recommended'],

  {
    name: 'edca/typescript-react',
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      parser: tsParser,
      ecmaVersion: 2022,
      sourceType: 'module',
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs['recommended-latest'].rules,

      // Vite's fast refresh only holds if a module exports components and
      // nothing else. Constant exports are allowed because several components
      // export a companion constant beside themselves.
      'react-refresh/only-export-components': [
        'warn',
        { allowConstantExport: true },
      ],

      // An unused argument named with a leading underscore is a deliberate
      // signature filler, which this codebase already writes that way.
      '@typescript-eslint/no-unused-vars': [
        'error',
        {
          argsIgnorePattern: '^_',
          varsIgnorePattern: '^_',
          caughtErrorsIgnorePattern: '^_',
        },
      ],

      // Core rules that TypeScript cannot see, chosen rather than inherited:
      //
      // A comparison that is always true or always false is the failure this
      // codebase is most exposed to, because a wrong one reads as working.
      'no-constant-binary-expression': 'error',
      'no-self-compare': 'error',
      // A loop that cannot run more than once is almost always an editing
      // accident.
      'no-unreachable-loop': 'error',
      //
      // `no-unmodified-loop-condition` was tried here and removed. It cannot
      // see a cancellation flag set from an effect's cleanup closure, which
      // is the standard way a React polling loop is stopped and is what
      // useLiveUpdates does. The rule fired on that one correct loop and on
      // nothing else, so keeping it would mean carrying a suppression
      // wherever the codebase uses its own normal pattern. Do not re-add it.
      // Returning from a promise executor is silently ignored, so the value
      // goes nowhere and the promise never settles as the author intended.
      'no-promise-executor-return': 'error',
      // '${x}' in a plain quoted string is a missed backtick.
      'no-template-curly-in-string': 'error',
      // Loose equality against null is idiomatic; everywhere else it hides
      // coercion the strict TypeScript config is otherwise preventing.
      eqeqeq: ['error', 'always', { null: 'ignore' }],
      'prefer-const': 'error',
      'no-var': 'error',
    },
  },
]
