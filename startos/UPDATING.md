# Updating

This file is the upstream bump recipe, as Start9's guide asks. How the
package is released, built and kept up with Start9 is BTCTX-MCP's
[`docs/STARTOS-PACKAGE.md`](https://github.com/DigiMonk73/BTCTX-MCP/blob/develop/docs/STARTOS-PACKAGE.md).

## Determining the upstream version

The upstream is the BitcoinTX app, released from DigiMonk73/BTCTX-MCP as
`vX.Y.Z` together with its image `ghcr.io/digimonk73/btctx-mcp:vX.Y.Z`:

```sh
gh release list -R DigiMonk73/BTCTX-MCP --exclude-pre-releases --limit 5
```

Take the newest `vX.Y.Z` from the list, not GitHub's "Latest" (Start9's
`maintaining-a-package.md`, "Skip prereleases, and don't trust
'Latest'"): never a pre-release (`vX.Y.Z-alpha.N`, `-beta.N`), and a
`vX.Y.Z-N` is a package-only revision of app `X.Y.Z`.

The current pin is `images.main.source.dockerTag` in
`startos/manifest/index.ts` (`ghcr.io/digimonk73/btctx-mcp:v<version>`).

## Applying the bump

Upstream releases bring their own package changes, so a bump normally arrives
as a pull request from DigiMonk73/BTCTX-StartOS. By hand:

- Bump `dockerTag` in `startos/manifest/index.ts` to
  `ghcr.io/digimonk73/btctx-mcp:v<new version>`.
- Bump the package version to `<new version>:0` as Start9's
  [Versions](https://docs.start9.com/packaging/versions.html) page says:
  its `<upstream>` is always the app's `VERSION`, so the two move together
  (BTCTX-MCP's `docs/STARTOS-PACKAGE.md`, "The package version").
