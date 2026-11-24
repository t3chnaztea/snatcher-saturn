importScripts('disc.js', 'vendor/BinFile.js', 'vendor/RomPatcher.format.vcdiff.js', 'vendor/sha256.umd.min.js');

const status = (message, progress) => postMessage({message, progress});
async function hash(data, algorithm = 'SHA-256') {
  const digest = new Uint8Array(await crypto.subtle.digest(algorithm, data));
  return Array.from(digest, n => n.toString(16).padStart(2, '0')).join('');
}
async function loadAsset(url, info, progress = 1) {
  for (let attempt = 1; attempt <= 3; attempt++) {
    const controller = new AbortController();
    let timer, permanent = false;
    function resetDeadline() {
      clearTimeout(timer);
      timer = setTimeout(() => controller.abort(), 15000);
    }
    try {
      resetDeadline();
      const response = await fetch(url, {
        signal: controller.signal,
        cache: attempt > 1 ? 'reload' : info ? 'default' : 'no-cache'
      });
      if (!response.ok) {
        permanent = response.status < 500 && ![408, 429].includes(response.status);
        throw Error('HTTP ' + response.status);
      }
      const reader = response.body.getReader();
      const chunks = [];
      let size = 0, lastPercent = -1;
      while (true) {
        const {value, done} = await reader.read();
        if (done) break;
        resetDeadline();
        chunks.push(value);
        size += value.length;
        if (info) {
          if (size > info.bytes) throw Error('Unexpected patch size');
          const percent = Math.floor(size * 100 / info.bytes);
          if (percent !== lastPercent) {
            status('Downloading patch… ' + percent + '%', progress + percent / 10);
            lastPercent = percent;
          }
        }
      }
      clearTimeout(timer);
      const blob = new Blob(chunks);
      if (!info) return JSON.parse(await blob.text());
      const bytes = await blob.arrayBuffer();
      if (size !== info.bytes || await hash(bytes) !== info.sha256) throw Error('Patch checksum mismatch');
      return bytes;
    } catch (error) {
      if (permanent || attempt === 3) {
        const reason = controller.signal.aborted ? 'download stalled' : error.message;
        throw Error('Could not load ' + url + ' (' + reason + '). Check your connection and try again.');
      }
      status('Retrying download (' + (attempt + 1) + ' of 3)…', progress);
    } finally {
      clearTimeout(timer);
      controller.abort();
    }
    await new Promise(resolve => setTimeout(resolve, 500 * attempt));
  }
}

async function applyPatch(source, name, release) {
  const progress = name === 'retail' ? 35 : 52;
  const packed = await loadAsset('patches/' + name + '.vcd.gz', release.patches[name], progress);
  status('Applying verified patch…', progress + 10);
  const stream = new Blob([packed]).stream().pipeThrough(new DecompressionStream('gzip'));
  const patch = new BinFile(await new Response(stream).arrayBuffer());
  return VCDIFF.fromFile(patch).apply(new BinFile(source), false)._u8array;
}

async function patchDisc(files, key) {
  if (!self.crypto?.subtle || !self.DecompressionStream) throw Error('Open the patcher in a current desktop browser over HTTPS.');
  const release = await loadAsset('release.json');
  const variant = release.variants[key];
  if (!variant) throw Error('Unknown restoration choices.');
  const cues = files.filter(f => /\.cue$/i.test(f.name));
  if (cues.length !== 1) throw Error('Select one CUE together with the BIN files it lists.');
  const tracks = readCue(await cues[0].text(), files.filter(f => f !== cues[0]));
  if (tracks[0].end !== release.sourceSectors) throw Error('This disc has the wrong data track size. Use the original US Sega CD release.');
  status('Verifying US retail data track…', 4);
  let raw = new Uint8Array(await tracks[0].file.slice(0, release.sourceSectors * RAW_SECTOR).arrayBuffer());
  if (await hash(raw, 'SHA-1') !== '1f4164205ed736a0d9a03eb7972868e9aa737d35') throw Error('Track 01 does not match the original US Sega CD disc.');
  const audio = [], cue = ['FILE "snatcher-saturn.bin" BINARY','  TRACK 01 MODE1/2352','    INDEX 01 00:00:00'];
  let pos = variant.sectors, silentFirstGap = false;
  for (const t of tracks.slice(1)) {
    status('Verifying audio track ' + t.number + ' of 21…', 6 + t.number);
    const ref = release.audio[t.number], gap = t.play - t.start;
    if (t.end - t.play !== ref.sectors || (gap && gap !== ref.pregap) ||
        (t.pregap !== undefined && t.pregap !== ref.pregap)) throw Error('Unexpected length or pregap on Track ' + t.number);
    const playable = t.file.slice(t.play * RAW_SECTOR, t.end * RAW_SECTOR);
    if (await hash(await playable.arrayBuffer()) !== ref.sha256) throw Error('Audio checksum mismatch on Track ' + t.number);
    let pregap;
    if (gap) {
      pregap = t.file.slice(t.start * RAW_SECTOR, t.play * RAW_SECTOR);
      if (await hash(await pregap.arrayBuffer()) !== ref.pregap_sha256) throw Error('Pregap checksum mismatch on Track ' + t.number);
    } else {
      pregap = new Blob([new Uint8Array(ref.pregap * RAW_SECTOR)]);
      if (t.number === 2) silentFirstGap = true;
    }
    audio.push(pregap, playable);
    cue.push('  TRACK ' + String(t.number).padStart(2,'0') + ' AUDIO',
             '    INDEX 00 ' + timecode(pos), '    INDEX 01 ' + timecode(pos + ref.pregap));
    pos += ref.sectors + ref.pregap;
  }
  status('Applying the Saturn port…', 35);
  let dict = makeDictionary(raw, release); raw = null;
  let iso = await applyPatch(dict, 'retail', release); dict = null;
  if (key !== 'retail') {
    status('Applying your restorations…', 52);
    iso = await applyPatch(iso, key, release);
  }
  if (await hash(iso) !== variant.isoHash) throw Error('Patched ISO verification failed.');
  status('Encoding Saturn data sectors…', 64);
  let encoded = encodeTrack(iso, fraction => status('Encoding Saturn data sectors… ' + Math.floor(fraction * 100) + '%', 64 + 12 * fraction)); iso = null;
  if (await hash(encoded) !== variant.dataHash) throw Error('Saturn data track verification failed.');
  const bin = new Blob([encoded, ...audio], {type:'application/octet-stream'}); encoded = null;
  const cueText = cue.join('\n') + '\n';
  if (await hash(new TextEncoder().encode(cueText)) !== variant.cueHash) throw Error('Output CUE verification failed.');
  const hasher = await hashwasm.createSHA256(); hasher.init();
  const chunk = 8 * 1024 * 1024;
  for (let at = 0; at < bin.size; at += chunk) {
    status('Checking the finished Saturn BIN…', 77 + Math.floor(22 * at / bin.size));
    hasher.update(new Uint8Array(await bin.slice(at, at + chunk).arrayBuffer()));
  }
  const binHash = hasher.digest();
  if (binHash !== (silentFirstGap ? variant.silentGapHash : variant.fullHash)) throw Error('Finished BIN verification failed.');
  return {bin, cue: new Blob([cueText], {type:'text/plain'}), binHash, cueHash:variant.cueHash};
}

self.onmessage = async ({data}) => {
  try { postMessage({result: await patchDisc(data.files, data.key)}); }
  catch (err) { postMessage({error: err.message || String(err)}); }
};
