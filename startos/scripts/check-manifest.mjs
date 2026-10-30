#!/usr/bin/env node
// Sanity checks on the bundled manifest (run after `make javascript/index.js`), for CI
// and the pre-push hook: the things that would break existing installs or
// ship the wrong image if they drifted.
import { existsSync, readFileSync } from 'node:fs'
import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)
const { ExtendedVersion, VersionRange } = require('@start9labs/start-sdk')
const { manifest: m } = require('../javascript/index.js')

const errors = []
const check = (ok, msg) => ok || errors.push(msg)

check(m.id === 'btctx', `package id must stay "btctx" (existing installs), got ${m.id}`)
check(m.license === 'MIT', `license should be the SPDX id "MIT", got ${m.license}`)

const [upstream, revision] = m.version.split(':')
// A 2.0 pre-release is <x.y.z>-alpha.<n>:0 or <x.y.z>-beta.<n>:0 (Start9's
// ExVer for an upstream alpha or beta, versions.md), on the 2.0 branch only:
// never a package revision, a fix is the next pre-release (2.0 plan 7.4,
// B10a; #251's decision 28)
const pre = /^\d+\.\d+\.\d+-(alpha|beta)\.[1-9]\d*$/.test(upstream)
check(
  (/^\d+\.\d+\.\d+$/.test(upstream) && /^\d+$/.test(revision ?? '')) || (pre && revision === '0'),
  `version ${m.version} is not <x.y.z>:<n>, <x.y.z>-alpha.<n>:0 or <x.y.z>-beta.<n>:0`,
)
// In the BTCTX-MCP monorepo the package must match the app's VERSION.
const versionFile = new URL('../../VERSION', import.meta.url)
if (existsSync(versionFile)) {
  const appVersion = readFileSync(versionFile, 'utf8').trim()
  check(upstream === appVersion, `package version ${m.version} doesn't match VERSION ${appVersion}`)
}
const tag = m.images?.main?.source?.dockerTag
check(tag === `ghcr.io/digimonk73/btctx-mcp:v${upstream}`, `image ${tag} is not v${upstream}`)
check(
  JSON.stringify([...(m.images?.main?.arch ?? [])].sort()) === '["aarch64","x86_64"]',
  `arch must be x86_64 + aarch64, got ${m.images?.main?.arch}`,
)
check(m.volumes.includes('main') && m.volumes.includes('startos'), `volumes must include main and startos`)
check(!('alerts' in m), 'alerts was removed in start-sdk 2.0')

// Every earlier release must be able to update to this one, and none to go back.
const from = VersionRange.parse(m.canMigrateFrom)
for (const v of ['0.3.0:0', '0.7.0:0', '0.8.0:0', '0.8.0:1']) {
  check(ExtendedVersion.parse(v).satisfies(from), `${v} can't update to ${m.version} (canMigrateFrom ${m.canMigrateFrom})`)
}
check(m.canMigrateTo === `=${m.version}`, `downgrades must be impossible, canMigrateTo is ${m.canMigrateTo}`)

// The question before a 1.x install downloads 2.0 (Start9's manifest.md, "Pre-download
// alerts"). StartOS shows it only from a registry, never on a sideload, so nothing shows
// it before users meet it: its range is checked here. A pre-release sorts below its
// release, and a tester's StartOS backup brings back that pre-release, not 1.x, so the
// range stops below every alpha and beta (2.0 plan 5.16).
const alert = m.preDownloadAlert
check(alert, 'the backups asked for before a 1.x install downloads 2.0: preDownloadAlert is missing')
if (alert) {
  const source = VersionRange.parse(alert.when.sourceVersion)
  for (const v of ['0.8.0:1', '1.2.9:0', '1.2.10:0', '1.2.10:1']) {
    check(ExtendedVersion.parse(v).satisfies(source), `${v} sees no backup alert (sourceVersion ${alert.when.sourceVersion})`)
  }
  for (const v of ['2.0.0-alpha.1:0', '2.0.0-beta.2:0', '2.0.0:0', '2.0.1:0']) {
    check(!ExtendedVersion.parse(v).satisfies(source), `${v} sees the backup alert for 1.x (sourceVersion ${alert.when.sourceVersion})`)
  }
  for (const locale of ['en_US', 'es_ES', 'de_DE', 'pl_PL', 'fr_FR']) {
    check(alert.message[locale]?.includes('Settings, Backup & Restore'), `the backup alert's ${locale} text doesn't name Settings, Backup & Restore`)
  }
}

if (errors.length) {
  console.error(`manifest check failed:\n - ${errors.join('\n - ')}`)
  process.exit(1)
}
console.log(`manifest ok: ${m.id} ${m.version} (${tag})`)
