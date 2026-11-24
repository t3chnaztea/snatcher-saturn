"""Package the browser deltas from the US combined disc and five tested native builds."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "docs"
SECTOR = 2352
DATA = 2048

def sha(data):
    return hashlib.sha256(data).hexdigest()

def data_track(cue):
    text = cue.read_text()
    name, = re.findall(r'^FILE "([^"]+)" BINARY', text, re.M)
    minute, second, frame = map(int, re.search(r'TRACK 02 AUDIO\s+INDEX 00 (\d+):(\d+):(\d+)', text).groups())
    with (cue.parent/name).open('rb') as f:
        track = f.read(((minute*60+second)*75+frame)*SECTOR)
    return track, cue.parent/name

def iso(track):
    return b''.join(track[i+16:i+2064] for i in range(0,len(track),SECTOR))

def root_files(image):
    # ISO 9660 primary volume descriptor, then the root directory's records.
    root = 16*DATA+156
    def extent(at):
        return (int.from_bytes(image[at+2:at+6],'little')*DATA,
                int.from_bytes(image[at+10:at+14],'little'))
    start,length = extent(root)
    at=start
    files={}
    while at<start+length:
        if not image[at]:
            at=(at//DATA+1)*DATA
            continue
        name=bytes(image[at+33:at+33+image[at+32]]).split(b';')[0]
        files[name]=extent(at)
        at+=image[at]
    return files

def update_dates(image, expected, wanted):
    result=bytearray(image)
    files=root_files(result)
    for name in expected:
        off,length=files[name]
        assert result[off:off+length]==expected[name] and len(wanted[name])==length
        result[off:off+length]=wanted[name]
    return result

def patches(args, tmp):
    stock, stock_bin=data_track(args.stock)
    source,source_bin=data_track(args.source)
    if hashlib.sha1(source).hexdigest()!='1f4164205ed736a0d9a03eb7972868e9aa737d35':
        raise ValueError('Unsupported US Sega CD Track 1')
    source_iso=iso(source)
    voice=json.loads((ROOT/'tools/retail-extents.json').read_text())['PCMLD_01.BIN']
    offset=voice['lba']*DATA
    signed=bytes((i-128 if i>=128 else -i)%256 for i in range(256))
    dictionary=tmp/'retail.dict'
    dictionary.write_bytes(source_iso+source_iso[offset:offset+voice['size']].translate(signed))
    del source_iso
    orig=iso(stock)
    date_image=iso(data_track(args.dates)[0])
    def modules(image):
        files=root_files(image)
        return {n:image[o:o+k] for n in [b'SP04.BIN',b'SP05.BIN'] for o,k in [files[n]]}
    original_dates, restored_dates=modules(orig),modules(date_image)
    audio=json.loads((ROOT/'tools/retail-audio.json').read_text())
    result=dict(sourceSectors=len(source)//SECTOR,voiceOffset=offset,voiceBytes=voice['size'],
                audio=audio, variants={}, patches={})
    data_base=tmp/'stock.iso'
    data_base.write_bytes(orig)
    assets=SITE/'patches'
    assets.mkdir(parents=True,exist_ok=True)
    def delta(name, base, target):
        patch=tmp/(name+'.vcd')
        subprocess.run(['xdelta3','-e','-9','-A','-S','none','-B','268435456','-s',base,target,patch],check=True)
        packed=gzip.compress(patch.read_bytes(),compresslevel=9,mtime=0)
        (assets/(name+'.vcd.gz')).write_bytes(packed)
        result['patches'][name]=dict(bytes=len(packed),sha256=sha(packed))
    delta('retail',dictionary,data_base)
    with source_bin.open('rb') as f:
        f.seek(len(source));sounds=f.read()
    assert len(sounds)==sum((a['sectors']+a['pregap'])*SECTOR for a in audio.values())
    gap=audio['2']['pregap']*SECTOR
    pos=0
    for track in audio.values():
        first=pos+track['pregap']*SECTOR;end=first+track['sectors']*SECTOR
        assert sha(sounds[pos:first])==track['pregap_sha256'] and sha(sounds[first:end])==track['sha256']
        pos=end
    for art,cue in [('retail',args.stock),('lisa',args.lisa),('bar',args.bar),('both',args.all_options)]:
        raw,_=data_track(cue)
        native=iso(raw)
        base=update_dates(native,restored_dates,original_dates) if art=='both' else native
        for dates in (False,True):
            key=art+('-dates' if dates else '')
            image=update_dates(base,original_dates,restored_dates) if dates else base
            stage=tmp/'variant.iso';stage.write_bytes(image)
            if key!='retail':delta(key,data_base,stage)
            target=tmp/'variant.bin'
            subprocess.run([args.encoder,stage,target],check=True,stdout=subprocess.DEVNULL)
            data=target.read_bytes()
            if (art=='both')==dates:assert data==raw
            if key=='retail-dates':assert data==data_track(args.dates)[0]
            full=hashlib.sha256(data); silent=full.copy()
            full.update(sounds);silent.update(bytes(gap));silent.update(memoryview(sounds)[gap:])
            result['variants'][key]=dict(sectors=len(data)//SECTOR,dataHash=sha(data),isoHash=sha(image),
                                         fullHash=full.hexdigest(),silentGapHash=silent.hexdigest(),
                                         cueHash=sha(cue.read_bytes()))
            print(key, result['variants'][key]['fullHash'],flush=True)
    (SITE/'release.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','stock','dates','lisa','bar','all-options','encoder'):
        p.add_argument('--'+name,type=Path,required=True)
    with tempfile.TemporaryDirectory() as d:patches(p.parse_args(),Path(d))
