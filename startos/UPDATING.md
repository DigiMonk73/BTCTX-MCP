# Updating

## Determining the upstream version

The upstream is the BitcoinTX app, released from DigiMonk73/BTCTX-MCP as
`vX.Y.Z` together with its image `ghcr.io/digimonk73/btctx-mcp:vX.Y.Z`:

```sh
gh release list -R DigiMonk73/BTCTX-MCP --exclude-pre-releases --limit 5
```

Take the newest `vX.Y.Z`: never a pre-release (`vX.Y.Z-alpha.N`,
`-beta.N`), and a `vX.Y.Z-N` is a package-only revision of app `X.Y.Z`.

The current pin is `images.main.source.dockerTag` in
`startos/manifest/index.ts` (`ghcr.io/digimonk73/btctx-mcp:v<version>`).

## Applying the bump

The bump rides in each app release's version pull request into BTCTX-MCP's
`develop`:

- Bump `dockerTag` in `startos/manifest/index.ts` to
  `ghcr.io/digimonk73/btctx-mcp:v<new version>`.
- Bump the package version to `<new version>:0` as Start9's
  [Versions](https://docs.start9.com/packaging/versions.html) page says:
  its `<upstream>` is always the app's `VERSION`, so the two move together
  (BTCTX-MCP's `docs/STARTOS-PACKAGE.md`, "The package version").
