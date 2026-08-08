/// <reference types="vite/client" />

// Vite's client types are what declare the asset modules, so that importing a
// PNG (the header badge in App.tsx) resolves to its fingerprinted URL instead
// of failing type checking. Without this the import is a TS2307 and the build
// stops, which is the point: a missing icon should break the build rather than
// render as a broken image in front of the user.
