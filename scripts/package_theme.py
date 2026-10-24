"""Package this standalone VS Code theme using only the Python standard library."""

import argparse
import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parent.parent
VSIX_NS = 'http://schemas.microsoft.com/developer/vsx-schema/2011'


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def package_theme(output_dir):
    manifest = read_json(ROOT / 'package.json')
    name = manifest['name']
    version = manifest['version']
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]*', name):
        raise ValueError('Invalid extension name')
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?', version):
        raise ValueError('Invalid extension version')
    if manifest.get('extensionDependencies'):
        raise ValueError('The theme must remain independent of other extensions')

    files = {ROOT / 'package.json', ROOT / 'README.md', ROOT / 'ThirdPartyNotices.txt'}
    if not manifest.get('contributes', {}).get('themes'):
        raise ValueError('No color theme is registered')
    for contribution in manifest['contributes']['themes']:
        path = (ROOT / contribution['path']).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file():
            raise ValueError('Theme file must exist inside this project')
        theme = read_json(path)
        if 'include' in theme:
            raise ValueError('Theme colors must be flattened into the theme file')
        if not theme.get('colors') or not theme.get('tokenColors'):
            raise ValueError('The theme needs UI colors and syntax token rules')
        files.add(path)

    ET.register_namespace('', VSIX_NS)
    package = ET.Element(f'{{{VSIX_NS}}}PackageManifest', Version='2.0.0')

    def element(parent, tag, value=None, **attributes):
        child = ET.SubElement(parent, f'{{{VSIX_NS}}}{tag}', attributes)
        if value is not None:
            child.text = value
        return child

    metadata = element(package, 'Metadata')
    element(metadata, 'Identity', Language='en-US', Id=name,
            Version=version, Publisher=manifest['publisher'])
    element(metadata, 'DisplayName', manifest['displayName'])
    element(metadata, 'Description', manifest['description'])
    element(metadata, 'Categories', ','.join(manifest['categories']))
    element(metadata, 'GalleryFlags')
    properties = element(metadata, 'Properties')
    for key, value in {
        'Microsoft.VisualStudio.Code.Engine': manifest['engines']['vscode'],
        'Microsoft.VisualStudio.Code.ExtensionDependencies': '',
        'Microsoft.VisualStudio.Code.ExtensionPack': '',
        'Microsoft.VisualStudio.Code.LocalizedLanguages': '',
        'Microsoft.VisualStudio.Code.ExecutesCode': 'false',
    }.items():
        element(properties, 'Property', Id=key, Value=value)
    installation = element(package, 'Installation')
    element(installation, 'InstallationTarget', Id='Microsoft.VisualStudio.Code')
    element(package, 'Dependencies')
    assets = element(package, 'Assets')
    element(assets, 'Asset', Type='Microsoft.VisualStudio.Code.Manifest',
            Path='extension/package.json', Addressable='true')
    element(assets, 'Asset', Type='Microsoft.VisualStudio.Services.Content.Details',
            Path='extension/README.md', Addressable='true')
    content_types = '''<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="json" ContentType="application/json"/>
  <Default Extension="md" ContentType="text/markdown"/>
  <Default Extension="txt" ContentType="text/plain"/>
  <Default Extension="vsixmanifest" ContentType="text/xml"/>
</Types>
'''

    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f'{name}-{version}.vsix'
    with ZipFile(target, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('extension.vsixmanifest',
                         ET.tostring(package, encoding='utf-8', xml_declaration=True))
        archive.writestr('[Content_Types].xml', content_types)
        for path in sorted(files):
            archive.write(path, 'extension/' + path.relative_to(ROOT).as_posix())
    with ZipFile(target) as archive:
        if archive.testzip() is not None:
            raise ValueError('Package archive is corrupt')
        if json.loads(archive.read('extension/package.json')) != manifest:
            raise ValueError('Packaged extension metadata differs from source')
        ET.fromstring(archive.read('extension.vsixmanifest'))
        for contribution in manifest['contributes']['themes']:
            relative_path = Path(contribution['path']).as_posix().removeprefix('./')
            if json.loads(archive.read('extension/' + relative_path)) != read_json(ROOT / relative_path):
                raise ValueError('Packaged theme differs from source')
    print(f'Built {target} ({target.stat().st_size} bytes)')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'dist')
    options = parser.parse_args()
    package_theme(options.output_dir.resolve())
