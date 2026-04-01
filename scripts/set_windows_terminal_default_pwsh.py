"""Set Windows Terminal defaultProfile to the PowerShell 7 profile (pwsh).
Backs up the existing settings.json before writing. Works on common Windows Terminal paths.
This script attempts to parse JSONC (removing // and /* */ comments and trailing commas)
and will add a pwsh profile if none exists.
"""
import os, json, re, shutil, time, uuid, sys

candidates = [
    os.path.join(os.environ.get('LOCALAPPDATA',''), 'Packages', 'Microsoft.WindowsTerminal_8wekyb3d8bbwe', 'LocalState', 'settings.json'),
    os.path.join(os.environ.get('LOCALAPPDATA',''), 'Microsoft', 'Windows Terminal', 'settings.json'),
    os.path.join(os.environ.get('LOCALAPPDATA',''), 'Packages', 'Microsoft.WindowsTerminalPreview_8wekyb3d8bbwe', 'LocalState', 'settings.json'),
]

settings_path = None
for p in candidates:
    if p and os.path.exists(p):
        settings_path = p
        break

if not settings_path:
    print('No Windows Terminal settings.json found. Checked candidates:')
    for p in candidates:
        print('  ', p)
    sys.exit(1)

bak = settings_path + '.bak.' + time.strftime('%Y%m%d%H%M%S')
shutil.copy2(settings_path, bak)
print('Backed up settings to', bak)

s = open(settings_path, 'r', encoding='utf-8').read()
# Remove // line comments and /* */ block comments
s2 = re.sub(r'//.*?$','', s, flags=re.MULTILINE)
s2 = re.sub(r'/\*.*?\*/','', s2, flags=re.DOTALL)
# Remove trailing commas in objects/arrays
s2 = re.sub(r',\s*([}\]])', r'\1', s2)

try:
    j = json.loads(s2)
except Exception as e:
    print('Failed to parse settings.json after cleaning:', e)
    sys.exit(2)

profiles = j.get('profiles', {})
plist = profiles.get('list', [])

pwsh_guid = None
pwsh_path = r'C:\Program Files\PowerShell\7\pwsh.exe'
for p in plist:
    cmd = (p.get('commandline') or '').lower()
    name = (p.get('name') or '').lower()
    if 'pwsh.exe' in cmd or ('powershell' in name and '7' in cmd):
        pwsh_guid = p.get('guid')
        break
# fallback: search for pwsh anywhere
if not pwsh_guid:
    for p in plist:
        if 'pwsh' in json.dumps(p).lower():
            pwsh_guid = p.get('guid')
            break

if not pwsh_guid:
    # create a new profile entry for pwsh
    new_guid = '{' + str(uuid.uuid4()) + '}'
    new_profile = {
        'guid': new_guid,
        'name': 'PowerShell 7',
        'commandline': pwsh_path,
        'hidden': False
    }
    plist.append(new_profile)
    pwsh_guid = new_guid
    print('Added new pwsh profile with guid', pwsh_guid)
else:
    print('Found existing pwsh profile guid', pwsh_guid)

# Write updated defaultProfile
j['defaultProfile'] = pwsh_guid
# ensure profiles->list updated
j.setdefault('profiles', {})['list'] = plist

# Write back as pretty JSON (this will remove comments)
open(settings_path, 'w', encoding='utf-8').write(json.dumps(j, indent=2))
print('Updated settings.json defaultProfile to', pwsh_guid)
print('Done')
