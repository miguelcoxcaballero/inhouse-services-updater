#!/usr/bin/env python3
"""Sync the canonical updater into every app. Never hand-edit generated copies.

Automatic application releases go to A + tiny changelog. B requires an explicit user request.
A includes all A and B releases; B includes only B. The publisher mirrors each B into A
and keeps the highest global versionCode as latest, without requiring a new client APK.
Run this for ALL five consumers whenever updater code changes. Runtime changes require
tested app builds published to A; publication-tool or documentation changes need source sync only.
"""
import argparse, hashlib, json, shutil, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APPS = {
    'youtube': ('youtube-calma', 'Inhouse YouTube'),
    'instagram': ('ig-calma', 'Inhouse Instagram'),
    'notes': ('inhousenotes', 'Inhouse Notes'),
    'photos': ('Inhouse-Photos', 'Inhouse Photos'),
    'read': ('inhouse-read', 'Inhouse Read'),
}
POLICY = '''# Inhouse services updater — mandatory shared updater policy

Canonical repository: https://github.com/miguelcoxcaballero/inhouse-services-updater

Every AI/developer working in this app must read this section even without opening the updater repository:

- **B is the default update channel.** A requires an English development warning, explicit acknowledgement and slide confirmation. Legacy implicit A preferences migrate to B; choosing B clears A consent. This does not authorize publishing or promoting a B release.
- New changes and automatic releases go to **A** unless the user explicitly requests B.
- **A receives all A and B releases; B receives only B releases.** The highest global Android versionCode wins: a newer B supersedes an older A for A users, while an older B never displaces a newer A.
- **B** (reviewed releases) requires the user's **explicit request**. Tests passing is not permission to publish or promote. B may promote an existing A release or publish a new verified APK directly; a previous A publication is not required.
- Every release needs a tiny changelog: preferably 2–10 words, maximum 120 characters.
- Never independently edit updater copies. Change the canonical repository first, test, commit, and sync the SAME revision into YouTube, Instagram, Notes, Photos and Read using its `tools/sync.py`.
- Commit `inhouse-updater.lock.json` and shared files together. Build checks must reject drift. App identity and host integration are the only permitted differences.
- Updates are optional. Later snoozes automatic prompts for 14 days; manual updates remain available in settings. The popup and settings both expose A/B selection.
- Keep APK package and signing key; increment Android versionCode globally across A/B. Switching channels never downgrades or deletes user data.
- Publish each exact verified signed APK before its matching channel catalog. Never replace a published binary or its immutable metadata. Use `updates/A.json` and `updates/B.json`.
- The publisher mirrors every B release and its exact metadata into A, preserving a newer A as latest. Existing clients therefore receive B releases through A without an APK update. B never falls back to A; neither channel uses generic GitHub latest. B initially has no releases until explicitly requested.
- See the central `AGENTS.md`, `docs/PROTOCOL.md` and `tools/catalog.py` before changing publication logic.

This section supersedes older instructions that mandate blocking update gates, independently copied updaters, unconditional latest/stable publication, disjoint A/B catalogs, or publication in A before an explicitly requested B release. Existing signature and integrity requirements remain in force.
'''

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def sync(app, destination):
    slug, name = APPS[app]; dest = Path(destination).resolve()
    subprocess.run(['git','diff','--exit-code','HEAD','--','web','android','tools','docs','AGENTS.md','README.md'],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    copies = {}
    def copy(source, target):
        path = dest / target; path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / source, path); copies[target] = {'source': source, 'sha256': digest(path)}
    for folder in ('web', 'android'):
        for source in sorted((ROOT / folder).glob('*')):
            if source.is_file(): copy(source.relative_to(ROOT).as_posix(), 'vendor/inhouse-services-updater/' + source.relative_to(ROOT).as_posix())
    copy('tools/verify.py', 'vendor/inhouse-services-updater/verify.py')
    copy('tools/catalog.py', 'vendor/inhouse-services-updater/catalog.py')
    copy('tools/register_android.py', 'vendor/inhouse-services-updater/register_android.py')
    copy('tests/browser.py', 'vendor/inhouse-services-updater/tests/browser.py')
    for document in ('AGENTS.md', 'README.md', 'docs/PROTOCOL.md', 'docs/PROVENANCE.md'):
        copy(document, 'vendor/inhouse-services-updater/' + document)
    if app in ('youtube', 'instagram', 'photos'):
        assets = 'mobile/android/app/src/main/assets/updates' if app == 'photos' else 'app/assets/updates'
        for source in sorted((ROOT / 'web').glob('*')):
            copy(source.relative_to(ROOT).as_posix(), assets + '/' + source.name)
        config = {'appId': app, 'appName': name, 'repository': 'miguelcoxcaballero/' + slug}
        if app in ('youtube','instagram'):
            manifest = dest / ('native/android-update.json' if app == 'instagram' else 'android-update.json')
            import re
            build = dest / ('native/src/es/calma/instagram/nativeapp/CalmaBuild.java' if app == 'instagram' else 'src/es/calma/youtube/nativeapp/CalmaBuild.java')
            config['installedVersion'] = re.search(r'VERSION = "([^"]+)"', build.read_text())[1]
            config['activityClass'] = 'es.calma.' + ('instagram' if app == 'instagram' else 'youtube') + '.UpdateActivity'
        (dest / assets / 'config.json').write_text(json.dumps(config, indent=2) + '\n')
    else:
        assets = 'src/vendor/inhouse-services-updater' if app == 'read' else 'shared/inhouse-services-updater'
        for file in ('updater.js', 'updater.css'): copy('web/' + file, assets + '/' + file)
    if app == 'photos':
        for source in sorted((ROOT / 'android').glob('*')):
            copy(source.relative_to(ROOT).as_posix(), 'mobile/android/app/src/main/java/com/inhouse/services/updater/' + source.name)
    lock = {'repository': 'miguelcoxcaballero/inhouse-services-updater', 'revision': revision, 'version': '1.2.2', 'appId': app, 'files': copies}
    (dest / 'inhouse-updater.lock.json').write_text(json.dumps(lock, indent=2) + '\n')
    (dest / 'UPDATER.md').write_text(POLICY)
    agents = dest / 'AGENTS.md'; current = agents.read_text() if agents.exists() else ''
    marker = '# Inhouse services updater — mandatory shared updater policy'
    before, _, after = current.partition(marker)
    # Preserve app-specific sections appended after our generated policy.
    extra = after[after.find('\n# '):] if '\n# ' in after else ''
    current = (before + extra).rstrip()
    agents.write_text(current + '\n\n' + POLICY)
    print(f'Synced {app} at {revision}: {len(copies)} identical files')

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('app',choices=APPS);p.add_argument('destination',type=Path);a=p.parse_args();sync(a.app,a.destination)
