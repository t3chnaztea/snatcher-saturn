"""Verify browser downloads using user-owned US disc files and Chrome via Playwright."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from playwright.sync_api import sync_playwright


def cue_files(cue):
    names = re.findall(r'^\s*FILE\s+"([^"]+)"\s+BINARY\s*$', cue.read_text(encoding='utf-8-sig'), re.M | re.I)
    return [cue, *(cue.parent / name for name in names)]


def run(args):
    site = Path(__file__).resolve().parents[1] / 'docs'
    variants = json.loads((site / 'release.json').read_text())['variants']
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='chrome')
        page = browser.new_page(accept_downloads=True)
        page.set_default_timeout(240000)
        page.goto(args.url)
        page.locator('#files').set_input_files([args.source])
        page.locator('#create').click()
        page.locator('#status.error').wait_for()
        assert not page.locator('#downloads').is_visible()
        for name in args.variant or variants:
            cue = args.source
            omitted = False
            if name in ('lisa', 'both-dates') and args.split:
                cue = args.split
            if name in ('retail-dates', 'bar-dates') and args.split_without_gaps:
                cue = args.split_without_gaps
                omitted = True
            page.locator('#files').set_input_files(cue_files(cue))
            art = name.split('-')[0]
            page.locator('#bar').set_checked(art in ('bar', 'both'))
            page.locator('#lisa').set_checked(art in ('lisa', 'both'))
            page.locator('#dates').set_checked(name.endswith('-dates'))
            page.locator('#create').click()
            page.locator('#downloads:not([hidden]), #status.error').first.wait_for()
            if not page.locator('#downloads').is_visible():
                raise RuntimeError(page.locator('#status').inner_text())
            result = variants[name]
            hashes = {'bin': result['silentGapHash' if omitted else 'fullHash'], 'cue': result['cueHash']}
            for ext, expected in hashes.items():
                with page.expect_download() as event:
                    page.locator('#' + ext).click()
                download = event.value
                assert download.suggested_filename == 'snatcher-saturn.' + ext
                with download.path().open('rb') as f:
                    assert hashlib.file_digest(f, 'sha256').hexdigest() == expected
                download.delete()
            print(name, hashes['bin'], flush=True)
        browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url')
    parser.add_argument('source', type=Path, help='US retail combined BIN/CUE, stored pregaps')
    parser.add_argument('--split', type=Path, help='Optional split BIN/CUE with stored pregaps')
    parser.add_argument('--split-without-gaps', type=Path, help='Optional split BIN/CUE without stored pregaps')
    parser.add_argument('--variant', action='append', help='Run only this release variant (repeatable)')
    run(parser.parse_args())
